"""Deterministic and deliberately scope-limited verification utilities.

This module NEVER claims to establish an external mathematical theorem.
No dynamic evaluation, network access, or external command execution.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import date
from fractions import Fraction
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

VERSION = "0.1"
VERIFIER_ID = "amvo-stdlib-exact-v0.1.1"
ID_PATTERN = re.compile(r"^amvo-[a-z0-9]+(?:-[a-z0-9]+)*$")
FRACTION_PATTERN = re.compile(r"^-?[0-9]{1,80}(?:/[0-9]{1,80})?$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ARXIV_VERSION_PATTERN = re.compile(r"^[0-9]{4}\.[0-9]{4,5}v[1-9][0-9]*$")
PIN_KINDS = frozenset({"git_commit", "arxiv_version", "sha256"})
CHECK_TYPES = frozenset({"rational_sum", "polynomial_coefficients", "file_sha256"})
REVIEW_STATUSES = frozenset({"unreviewed", "under_review", "needs_revision", "withdrawn"})
RIGHTS_MODES = frozenset({"metadata_only", "redistribution_cleared"})
CASE_TYPES = frozenset({"public_source_intake", "claim", "synthetic_fixture"})
MAX_CASE_BYTES = 1_000_000
MAX_EVIDENCE_BYTES = 4_000_000
MAX_CHECKS = 64
MAX_TERMS = 128


class RecordError(ValueError):
    """Invalid or inadmissible public record."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecordError(message)


def _is_nonempty(value: object, *, limit: int = 4000) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def _fraction(value: object) -> Fraction:
    _require(isinstance(value, str) and FRACTION_PATTERN.fullmatch(value) is not None,
             "fraction must be a bounded decimal integer or a/b string")
    try:
        return Fraction(value)
    except (ZeroDivisionError, ValueError) as exc:
        raise RecordError("invalid rational value") from exc


def _fractions(values: object) -> list[Fraction]:
    _require(isinstance(values, list) and 0 < len(values) <= MAX_TERMS,
             "expected a nonempty bounded list of rational strings")
    return [_fraction(v) for v in values]


def _verify_url(url: object) -> None:
    _require(_is_nonempty(url, limit=1200), "source.url is required")
    _require(not re.search(r"[\\x00-\\x20\\x7f]", url),
             "source URL contains whitespace or control characters")
    try:
        p = urlsplit(url)
        host = p.hostname
        _ = p.port
    except ValueError as exc:
        raise RecordError("malformed source URL") from exc
    _require(p.scheme == "https" and bool(host), "only HTTPS source URLs are allowed")
    _require(not p.username and not p.password and not p.query and not p.fragment,
             "source URL cannot contain userinfo, query parameters, or fragments")
    _require(host not in {"localhost"} and not host.endswith((".localhost", ".local", ".internal")),
             "local hostname is not a public source")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        _require(ip.is_global, "local or non-global IP address is not a public source")


def _validate_pin(pin: object) -> None:
    _require(isinstance(pin, dict) and set(pin) == {"kind", "value"},
             "source.pin must contain only kind and value")
    kind, value = pin["kind"], pin["value"]
    _require(isinstance(kind, str) and kind in PIN_KINDS, "unsupported source.pin kind")
    _require(_is_nonempty(value, limit=128), "source.pin value is required")
    if kind == "git_commit":
        _require(GIT_COMMIT_PATTERN.fullmatch(value) is not None,
                 "source.pin git_commit must be a 40 or 64 hex digest")
    elif kind == "arxiv_version":
        _require(ARXIV_VERSION_PATTERN.fullmatch(value) is not None,
                 "source.pin arxiv_version must contain a pinned vN suffix")
    else:
        _require(HASH_PATTERN.fullmatch(value) is not None,
                 "source.pin sha256 must be a 64 hex digest")


def _is_safe_evidence_path(path: object) -> bool:
    if not isinstance(path, str) or "\\" in path or "\x00" in path:
        return False
    if any(segment in {"", ".", ".."} for segment in path.split("/")):
        return False
    p = PurePosixPath(path)
    return (
        len(p.parts) >= 2
        and p.parts[0] == "evidence"
        and ".." not in p.parts
        and "." not in p.parts
        and not p.is_absolute()
        and not path.endswith("/")
    )


def validate_record(record: object) -> dict:
    _require(isinstance(record, dict), "record must be a JSON object")
    required = {"schema_version", "id", "type", "title", "source", "claim",
                "rights", "review", "checks"}
    _require(required.issubset(record), f"missing required fields: {sorted(required - set(record))}")
    _require(set(record).issubset(required), "unknown top-level fields are not permitted")
    _require(record["schema_version"] == VERSION, "unsupported schema version")
    _require(isinstance(record["id"], str) and ID_PATTERN.fullmatch(record["id"]) is not None,
             "invalid case id")
    _require(isinstance(record["type"], str) and record["type"] in CASE_TYPES, "unknown case type")
    _require(_is_nonempty(record["title"], limit=240), "title is required")

    source = record["source"]
    _require(isinstance(source, dict), "source must be an object")
    _require(set(source).issubset({"publisher", "title", "authors", "url", "version", "captured_at", "public", "pin"}), "unknown source fields")
    for field in ("publisher", "title", "url", "version", "captured_at"):
        _require(_is_nonempty(source.get(field), limit=1200), f"source.{field} is required")
    _verify_url(source["url"])
    try:
        date.fromisoformat(source["captured_at"])
    except ValueError as exc:
        raise RecordError("invalid source.captured_at date") from exc
    _require(isinstance(source.get("authors"), list)
             and all(_is_nonempty(name, limit=200) for name in source["authors"]),
             "source.authors must be a string list")
    _require(source.get("public") is True, "only public source metadata is allowed")
    _require(bool(source["authors"]), "source.authors must contain at least one attribution")
    if "pin" in source:
        _validate_pin(source["pin"])
    _require(record["type"] != "claim" or "pin" in source,
             "mathematical claim records require a declared immutable source.pin")

    rights = record["rights"]
    _require(isinstance(rights, dict) and isinstance(rights.get("mode"), str)
             and rights.get("mode") in RIGHTS_MODES,
             "rights.mode must be metadata_only or redistribution_cleared")
    _require(_is_nonempty(rights.get("note"), limit=1200), "rights.note required")
    _require(set(rights).issubset({"mode", "note"}), "unknown rights fields")

    claim = record["claim"]
    _require(isinstance(claim, dict)
             and _is_nonempty(claim.get("statement"))
             and _is_nonempty(claim.get("scope")), "claim statement and scope required")
    _require(set(claim).issubset({"statement", "scope"}), "unknown claim fields")

    review = record["review"]
    _require(isinstance(review, dict) and isinstance(review.get("status"), str)
             and review.get("status") in REVIEW_STATUSES,
             "invalid manual review status")
    _require(set(review).issubset({"status"}), "unknown review fields")

    checks = record["checks"]
    _require(isinstance(checks, list) and len(checks) <= MAX_CHECKS, "invalid checks list")
    _require(record["type"] != "public_source_intake" or not checks,
             "source intake cannot contain computed checks")
    seen = set()
    for check in checks:
        _require(isinstance(check, dict), "check must be an object")
        check_id = check.get("id")
        _require(_is_nonempty(check_id, limit=80) and check_id not in seen,
                 "duplicate or invalid check id")
        seen.add(check_id)
        kind = check.get("kind")
        _require(isinstance(kind, str) and kind in CHECK_TYPES, f"unsupported check kind: {kind}")
        if kind == "rational_sum":
            allowed = {"id", "kind", "lhs", "rhs"}
        elif kind == "polynomial_coefficients":
            allowed = {"id", "kind", "lhs_coefficients", "rhs_coefficients"}
        else:
            allowed = {"id", "kind", "path", "sha256"}
        _require(set(check).issubset(allowed), "unknown check fields")
        if kind == "rational_sum":
            _fractions(check.get("lhs"))
            _fractions(check.get("rhs"))
        elif kind == "polynomial_coefficients":
            _fractions(check.get("lhs_coefficients"))
            _fractions(check.get("rhs_coefficients"))
        else:
            _require(_is_safe_evidence_path(check.get("path")), "unsafe evidence path")
            _require(isinstance(check.get("sha256"), str)
                     and HASH_PATTERN.fullmatch(check["sha256"]) is not None,
                     "file_sha256 requires a hex SHA-256 digest")
    return record


def load_record(path: Path) -> dict:
    _require(path.is_file() and not path.is_symlink(), f"not a regular case file: {path.name}")
    _require(path.stat().st_size <= MAX_CASE_BYTES, "case exceeds maximum size")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RecordError(f"invalid UTF-8 JSON: {path.name}") from exc
    validate_record(record)
    _require(path.name == record["id"] + ".json",
             f"filename and record id differ: {path.name}")
    return record


def list_records(cases_dir: Path) -> list[dict]:
    _require(cases_dir.is_dir(), f"case directory missing: {cases_dir}")
    results = []
    ids = set()
    for path in sorted(cases_dir.glob("*.json")):
        rec = load_record(path)
        _require(rec["id"] not in ids, "duplicate record id")
        ids.add(rec["id"])
        results.append(rec)
    return results


def _trim_zeros(coeffs: list[Fraction]) -> list[Fraction]:
    while len(coeffs) > 1 and coeffs[-1] == 0:
        coeffs.pop()
    return coeffs


def check_one(check: dict, root: Path) -> dict:
    kind = check["kind"]
    details = "exact, scope-bounded verification"
    if kind == "rational_sum":
        ok = sum(_fractions(check["lhs"]), Fraction(0)) == sum(
            _fractions(check["rhs"]), Fraction(0))
    elif kind == "polynomial_coefficients":
        ok = _trim_zeros(_fractions(check["lhs_coefficients"])) == _trim_zeros(
            _fractions(check["rhs_coefficients"]))
    else:
        candidate = root / check["path"]
        evidence_root = (root / "evidence").resolve()
        _require(candidate.resolve().is_relative_to(evidence_root), "evidence path escaped root")
        _require(candidate.is_file() and not candidate.is_symlink(), "missing or unsafe evidence")
        _require(candidate.stat().st_size <= MAX_EVIDENCE_BYTES, "evidence too large")
        ok = sha256(candidate.read_bytes()) == check["sha256"]
        details = "artifact integrity only; not semantic or mathematical validity"
    return {"id": check["id"], "kind": kind,
            "result": "pass" if ok else "fail", "scope": details}


def verify_record(record: dict, project_root: Path) -> dict:
    validate_record(record)
    outcomes = []
    for check in record["checks"]:
        try:
            outcomes.append(check_one(check, project_root))
        except (RecordError, OSError) as exc:
            outcomes.append({"id": check["id"], "kind": check["kind"],
                             "result": "error", "scope": str(exc)})
    if not outcomes:
        outcome = "not_checked"
    elif all(x["result"] == "pass" for x in outcomes):
        outcome = "bounded_checks_pass"
    else:
        outcome = "checks_not_passed"
    return {
        "id": record["id"],
        "source_url": record["source"]["url"],
        "source_version": record["source"]["version"],
        "source_pin": record["source"].get("pin"),
        "source_pin_verified": False,
        "record_sha256": sha256(canonical_bytes(record)),
        "engine": VERIFIER_ID,
        "outcome": outcome,
        "checks": outcomes,
        "formal_kernel": "not_run",
        "semantic_alignment": "not_assessed",
        "independent_theorem_review": "not_assessed",
        "theorem_proved": False,
        "warning": "A passing bounded check is not a proof of an external theorem."
    }


def report(records: list[dict], project_root: Path) -> dict:
    return {
        "report_schema": VERSION,
        "engine": VERIFIER_ID,
        "cases": [verify_record(rec, project_root) for rec in records],
        "disclaimer": "No external theorem or remotely declared source pin receives independent certification in AMVO v0.1.1."
    }


def audit_public(records: list[dict]) -> list[str]:
    """Conservative source-intake disclosure gate. No raw secret values in findings."""
    suspicious = re.compile(
        r"(?i)(?:sk-proj-|ghp_[a-z0-9]{12}|github_pat_[a-z0-9]{12}|"
        r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|"
        r"(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*['\"]?[a-z0-9/+_-]{12})"
    )
    findings = []
    for rec in records:
        # Flag any apparent credential material before permitting external publication.
        if suspicious.search(json.dumps(rec, ensure_ascii=False)):
            findings.append(f"{rec['id']}: suspicious credential pattern")
        if rec["rights"]["mode"] == "redistribution_cleared":
            findings.append(f"{rec['id']}: redistribution license needs human review")
        if rec["source"]["url"].startswith("https://example.org/") and rec["type"] != "synthetic_fixture":
            findings.append(f"{rec['id']}: placeholder URL in non-synthetic record")
    return findings
