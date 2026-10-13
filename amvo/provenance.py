"""P1-A: replay a declared source pin against its public origin, and keep only what was observed.

Nothing here runs by default. A replay needs either `--network` (a live, allowlisted HTTPS
fetch) or `--fixtures DIR` (canned responses, for tests). Each replay writes one new capture
file under evidence/provenance/<case-id>/ and never rewrites an earlier one; the verification
report then reads the latest capture. Only a *live* capture whose observation matches the
declared pin counts as remote verification; a fixture capture never does.

What is kept is metadata and hashes: for a git commit, the commit's own identifiers; for an
arXiv version, the entry's id, title and dates; for a sha256 pin, the digest and byte count of
the fetched file. No paper, proof or file body is stored.

A live fetch is restricted to:
- HTTPS on port 443 to a fixed host allowlist (no user-supplied hosts);
- addresses that are all global after DNS resolution, with the TLS connection made to the
  address that was checked (no second lookup between check and connect);
- no redirects, no cookies, no credentials, a byte cap and a timeout.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from .core import ENGINE_VERSION, VERIFIER_ID, RecordError, canonical_bytes, sha256

CAPTURE_SCHEMA = "0.1"
ALLOWED_HOSTS = frozenset({"api.github.com", "export.arxiv.org", "raw.githubusercontent.com"})
MAX_FETCH_BYTES = 4_000_000
TIMEOUT_S = 20
USER_AGENT = f"AMVO/{ENGINE_VERSION} (+https://github.com/kakon77777-commits/AMVO)"
STATUSES = ("verified", "mismatch", "not_found", "unavailable", "unsupported")
GITHUB_REPO = re.compile(r"^https://github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})(?:/.*)?$")
ATOM = "{http://www.w3.org/2005/Atom}"


class FetchError(Exception):
    """The origin could not be reached or answered outside the rules; the pin stays unknown."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


# ---------------------------------------------------------------- fetchers

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """connects to one already-checked IP address while verifying TLS for the host name"""

    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class LiveFetcher:
    mode = "live"

    def __init__(self, resolver=socket.getaddrinfo, connection=_PinnedHTTPSConnection,
                 max_bytes: int = MAX_FETCH_BYTES, timeout: float = TIMEOUT_S):
        self._resolve, self._connection = resolver, connection
        self.max_bytes, self.timeout = max_bytes, timeout
        self.requested: list[str] = []

    def get(self, url: str) -> Response:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or host not in ALLOWED_HOSTS or parts.port not in (None, 443) \
                or parts.username or parts.password:
            raise FetchError("host is not on the fetch allowlist")
        try:
            infos = self._resolve(host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise FetchError("name resolution failed") from exc
        addresses = sorted({info[4][0] for info in infos})
        if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
            raise FetchError("host resolves to a non-global address")
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        self.requested.append(url)
        conn = self._connection(host, addresses[0], self.timeout)
        try:
            conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*",
                                               "Accept-Encoding": "identity"})
            resp = conn.getresponse()
            if 300 <= resp.status < 400:
                raise FetchError(f"redirect refused (HTTP {resp.status})")
            body = resp.read(self.max_bytes + 1)
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise FetchError(f"transport failure: {exc.__class__.__name__}") from exc
        finally:
            conn.close()
        if len(body) > self.max_bytes:
            raise FetchError("response exceeds the byte cap")
        return Response(resp.status, body)


class FixtureFetcher:
    """canned responses from DIR/index.json: {url: {"status": int, "file": name} | {"error": msg}}"""
    mode = "fixture"

    def __init__(self, directory: Path):
        self._dir = directory
        self._index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
        self.requested: list[str] = []

    def get(self, url: str) -> Response:
        self.requested.append(url)
        entry = self._index.get(url)
        if entry is None:
            raise FetchError("no fixture for this URL")
        if "error" in entry:
            raise FetchError(entry["error"])
        name = entry["file"]
        if "/" in name or "\\" in name or name.startswith("."):
            raise FetchError("unsafe fixture name")
        return Response(entry["status"], (self._dir / name).read_bytes())


# ---------------------------------------------------------------- replay

def _github_commit(record: dict, value: str, fetch) -> tuple[str, dict, int]:
    m = GITHUB_REPO.fullmatch(record["source"]["url"])
    if m is None:
        return "unsupported", {"reason": "git_commit pins are replayed only for github.com repositories"}, 0
    if len(value) != 40:
        return "unsupported", {"reason": "GitHub serves SHA-1 commits; a 64-hex pin cannot be replayed there"}, 0
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    resp = fetch.get(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/commits/{value}")
    if resp.status in (404, 422):
        return "not_found", {"repository": f"{owner}/{repo}", "http_status": resp.status}, len(resp.body)
    if resp.status != 200:
        raise FetchError(f"unexpected HTTP {resp.status}")
    try:
        data = json.loads(resp.body)
        observed = {
            "repository": f"{owner}/{repo}",
            "commit": data["sha"],
            "tree": data["commit"]["tree"]["sha"],
            "parents": [p["sha"] for p in data["parents"]],
            "committed_at": data["commit"]["committer"]["date"],
            "html_url": data["html_url"],
        }
    except (ValueError, KeyError, TypeError) as exc:
        raise FetchError("unparseable commit metadata") from exc
    return ("verified" if observed["commit"] == value else "mismatch"), observed, len(resp.body)


def _arxiv_version(value: str, fetch) -> tuple[str, dict, int]:
    resp = fetch.get(f"https://export.arxiv.org/api/query?id_list={value}")
    if resp.status != 200:
        raise FetchError(f"unexpected HTTP {resp.status}")
    try:
        root = ET.fromstring(resp.body)
    except ET.ParseError as exc:
        raise FetchError("unparseable arXiv response") from exc
    entries = [e for e in root.findall(f"{ATOM}entry")
               if (e.findtext(f"{ATOM}id") or "").rstrip("/").endswith("/abs/" + value)]
    if not entries:
        return "not_found", {"arxiv_id": value}, len(resp.body)
    e = entries[0]
    observed = {
        "arxiv_id": value,
        "entry_id": (e.findtext(f"{ATOM}id") or "").strip(),
        "title": " ".join((e.findtext(f"{ATOM}title") or "").split()),
        "published": (e.findtext(f"{ATOM}published") or "").strip(),
        "updated": (e.findtext(f"{ATOM}updated") or "").strip(),
    }
    return "verified", observed, len(resp.body)


def _file_sha256(record: dict, value: str, fetch) -> tuple[str, dict, int]:
    url = record["source"]["url"]
    if urlsplit(url).hostname not in ALLOWED_HOSTS:
        return "unsupported", {"reason": "sha256 pins are replayed only for allowlisted file hosts"}, 0
    resp = fetch.get(url)
    if resp.status == 404:
        return "not_found", {"http_status": 404}, len(resp.body)
    if resp.status != 200:
        raise FetchError(f"unexpected HTTP {resp.status}")
    digest = sha256(resp.body)
    observed = {"content_sha256": digest, "bytes": len(resp.body)}
    return ("verified" if digest == value else "mismatch"), observed, len(resp.body)


def replay_pin(record: dict, fetch, now: datetime | None = None) -> dict:
    """one capture for the record's declared pin; network failures become `unavailable`"""
    pin = record["source"].get("pin")
    if pin is None:
        raise RecordError(f"{record['id']}: no declared source.pin to replay")
    kind, value = pin["kind"], pin["value"]
    try:
        if kind == "git_commit":
            status, observed, nbytes = _github_commit(record, value, fetch)
        elif kind == "arxiv_version":
            status, observed, nbytes = _arxiv_version(value, fetch)
        else:
            status, observed, nbytes = _file_sha256(record, value, fetch)
    except FetchError as exc:
        status, observed, nbytes = "unavailable", {"reason": str(exc)}, 0
    when = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    return {
        "capture_schema": CAPTURE_SCHEMA,
        "case_id": record["id"],
        "record_sha256": sha256(canonical_bytes(record)),
        "pin": {"kind": kind, "value": value},
        "status": status,
        "observed": observed,
        "observed_sha256": sha256(canonical_bytes(observed)),
        "bytes_read": nbytes,
        "requested": list(fetch.requested),
        "network": fetch.mode,
        "captured_at": when.isoformat().replace("+00:00", "Z"),
        "engine": VERIFIER_ID,
    }


# ---------------------------------------------------------------- the capture ledger

def capture_dir(root: Path, case_id: str) -> Path:
    return root / "evidence" / "provenance" / case_id


def write_capture(root: Path, capture: dict) -> Path:
    """append-only: a new file per capture; an existing name is never overwritten"""
    folder = capture_dir(root, capture["case_id"])
    folder.mkdir(parents=True, exist_ok=True)
    stamp = capture["captured_at"].replace("-", "").replace(":", "")
    base = f"{stamp}-{capture['pin']['kind']}-{capture['pin']['value'][:12]}"
    for n in range(1000):
        path = folder / (base + (f"-{n}" if n else "") + ".json")
        try:
            with open(path, "xb") as f:
                f.write(canonical_bytes(capture) + b"\n")
            return path
        except FileExistsError:
            continue
    raise RecordError("too many captures with the same timestamp")


CAPTURED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
OBSERVED_PIN_FIELD = {"git_commit": "commit", "arxiv_version": "arxiv_id", "sha256": "content_sha256"}


def _valid_capture(capture: object, record: dict) -> bool:
    """self-consistency only: a capture is a recorded observation, not a signed attestation;
    anyone can re-check it by running replay-pins again"""
    if not isinstance(capture, dict) or capture.get("capture_schema") != CAPTURE_SCHEMA:
        return False
    if capture.get("case_id") != record["id"] or capture.get("status") not in STATUSES:
        return False
    if capture.get("pin") != record["source"].get("pin") or capture.get("network") not in ("live", "fixture"):
        return False
    if not isinstance(capture.get("captured_at"), str) or not CAPTURED_AT.fullmatch(capture["captured_at"]):
        return False
    observed = capture.get("observed")
    if not isinstance(observed, dict) or capture.get("observed_sha256") != sha256(canonical_bytes(observed)):
        return False
    pin = capture["pin"]
    return capture["status"] != "verified" or observed.get(OBSERVED_PIN_FIELD[pin["kind"]]) == pin["value"]


def pin_state(record: dict, root: Path) -> dict:
    """the declared pin's state for the report, from the latest capture on file"""
    pin = record["source"].get("pin")
    if pin is None:
        return {"status": "no_pin", "verified": False}
    folder = capture_dir(root, record["id"])
    captures = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                cap = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeError, ValueError):
                return {"status": "capture_invalid", "verified": False, "capture": path.name}
            if not _valid_capture(cap, record):
                if isinstance(cap, dict) and cap.get("pin") != pin and cap.get("case_id") == record["id"]:
                    continue                      # an earlier pin of this record: history, not current
                return {"status": "capture_invalid", "verified": False, "capture": path.name}
            captures.append((cap["captured_at"], path.name, cap))
    if not captures:
        return {"status": "declared_only", "verified": False}
    at, name, cap = max(captures)
    live = cap["network"] == "live"
    status = cap["status"] if live else "fixture_only"
    return {"status": status, "verified": live and cap["status"] == "verified", "capture": name,
            "captured_at": at, "network": cap["network"], "observed_sha256": cap["observed_sha256"]}
