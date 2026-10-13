"""P1-A: declared pins replayed against their origin; captures append-only; fetch safety.

Everything here is offline. The live path is exercised with a fake resolver and a fake
connection, so the code that a real `--network` run uses is the code under test.
"""
import copy
import json
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from amvo.cli import main
from amvo.core import canonical_bytes, sha256, verify_record
from amvo.provenance import (FetchError, FixtureFetcher, LiveFetcher, pin_state, replay_pin,
                             write_capture)

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "cases" / "amvo-synthetic-fraction.json").read_text("utf-8"))
SHA = "0123456789abcdef0123456789abcdef01234567"
T0 = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)


def record(kind="git_commit", value=SHA, url="https://github.com/example/public-math"):
    rec = copy.deepcopy(BASE)
    rec["type"] = "claim"
    rec["source"]["url"] = url
    rec["source"]["pin"] = {"kind": kind, "value": value}
    return rec


def commit_json(sha=SHA):
    return json.dumps({"sha": sha, "html_url": f"https://github.com/example/public-math/commit/{sha}",
                       "commit": {"tree": {"sha": "f" * 40}, "committer": {"date": "2026-10-01T00:00:00Z"}},
                       "parents": [{"sha": "e" * 40}]}).encode()


ATOM_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2610.12345v2</id><title>A synthetic
  title</title><published>2026-10-01T00:00:00Z</published><updated>2026-10-05T00:00:00Z</updated>
</entry></feed>"""


class FakeResponse:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self, n):
        return self._body[:n]


def fake_connection(routes):
    """a connection class that serves `routes` {path: (status, body)} and records what it saw"""
    seen = []

    class Conn:
        def __init__(self, host, address, timeout):
            self.host, self.address = host, address
            seen.append((host, address))

        def request(self, method, path, headers):
            self.path = path
            assert "Authorization" not in headers and "Cookie" not in headers

        def getresponse(self):
            status, body = routes.get(self.path, (404, b""))
            return FakeResponse(status, body)

        def close(self):
            pass
    return Conn, seen


def resolver(*addresses):
    return lambda host, port, type=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]


def live(routes, addresses=("140.82.112.6",), **kw):
    conn, seen = fake_connection(routes)
    return LiveFetcher(resolver=resolver(*addresses), connection=conn, **kw), seen


def fixtures(td, entries):
    d = Path(td) / "fx"
    d.mkdir()
    index = {}
    for i, (url, status, body) in enumerate(entries):
        if isinstance(status, str):
            index[url] = {"error": status}
            continue
        (d / f"r{i}").write_bytes(body)
        index[url] = {"status": status, "file": f"r{i}"}
    (d / "index.json").write_text(json.dumps(index), "utf-8")
    return d


API = f"/repos/example/public-math/commits/{SHA}"


class ReplayTests(unittest.TestCase):
    def test_live_git_commit_verified_and_reported(self):
        fetch, seen = live({API: (200, commit_json())})
        cap = replay_pin(record(), fetch, T0)
        self.assertEqual(cap["status"], "verified")
        self.assertEqual(cap["observed"]["commit"], SHA)
        self.assertEqual(cap["network"], "live")
        self.assertEqual(seen, [("api.github.com", "140.82.112.6")])   # TLS to the checked address
        with tempfile.TemporaryDirectory() as td:
            write_capture(Path(td), cap)
            st = pin_state(record(), Path(td))
            self.assertEqual((st["status"], st["verified"]), ("verified", True))
            result = verify_record(record(), Path(td), st)
            self.assertTrue(result["source_pin_verified"])
            self.assertFalse(result["theorem_proved"])          # a real version is not a proof

    def test_fixture_capture_never_counts_as_remote_verification(self):
        with tempfile.TemporaryDirectory() as td:
            d = fixtures(td, [(f"https://api.github.com{API}", 200, commit_json())])
            cap = replay_pin(record(), FixtureFetcher(d), T0)
            self.assertEqual(cap["status"], "verified")
            write_capture(Path(td), cap)
            st = pin_state(record(), Path(td))
            self.assertEqual((st["status"], st["verified"]), ("fixture_only", False))

    def test_git_commit_not_found_mismatch_and_unsupported(self):
        fetch, _ = live({API: (404, b"{}")})
        self.assertEqual(replay_pin(record(), fetch, T0)["status"], "not_found")
        fetch, _ = live({API: (200, commit_json("9" * 40))})
        self.assertEqual(replay_pin(record(), fetch, T0)["status"], "mismatch")
        fetch, _ = live({})
        self.assertEqual(replay_pin(record(value="a" * 64), fetch, T0)["status"], "unsupported")   # S02
        fetch, _ = live({})
        self.assertEqual(replay_pin(record(url="https://gitlab.com/x/y"), fetch, T0)["status"], "unsupported")

    def test_arxiv_version(self):
        route = "/api/query?id_list=2610.12345v2"
        fetch, _ = live({route: (200, ATOM_OK)}, addresses=("128.84.21.199",))
        cap = replay_pin(record("arxiv_version", "2610.12345v2", "https://arxiv.org/abs/2610.12345v2"), fetch, T0)
        self.assertEqual(cap["status"], "verified")
        self.assertEqual(cap["observed"]["title"], "A synthetic title")
        other = ATOM_OK.replace(b"2610.12345v2", b"2610.12345v1")
        fetch, _ = live({route: (200, other)})
        self.assertEqual(replay_pin(record("arxiv_version", "2610.12345v2", "https://arxiv.org/abs/2610.12345v2"),
                                   fetch, T0)["status"], "not_found")
        fetch, _ = live({route: (200, b"<feed><unclosed>")})
        self.assertEqual(replay_pin(record("arxiv_version", "2610.12345v2", "https://arxiv.org/abs/2610.12345v2"),
                                   fetch, T0)["status"], "unavailable")

    def test_sha256_pin(self):
        body = b"public artifact bytes"
        url = "https://raw.githubusercontent.com/example/public-math/" + SHA + "/a.txt"
        fetch, _ = live({"/example/public-math/" + SHA + "/a.txt": (200, body)})
        cap = replay_pin(record("sha256", sha256(body), url), fetch, T0)
        self.assertEqual((cap["status"], cap["observed"]["bytes"]), ("verified", len(body)))
        self.assertNotIn(body.decode(), json.dumps(cap))          # the body itself is not kept
        fetch, _ = live({"/example/public-math/" + SHA + "/a.txt": (200, body + b"!")})
        self.assertEqual(replay_pin(record("sha256", sha256(body), url), fetch, T0)["status"], "mismatch")
        fetch, _ = live({})
        self.assertEqual(replay_pin(record("sha256", sha256(body), "https://example.org/a.txt"), fetch, T0)["status"],
                         "unsupported")


class FetchSafetyTests(unittest.TestCase):
    def test_host_not_on_allowlist_refused(self):
        fetch, seen = live({})
        with self.assertRaises(FetchError):
            fetch.get("https://example.org/x")
        with self.assertRaises(FetchError):
            fetch.get("http://api.github.com/x")
        with self.assertRaises(FetchError):
            fetch.get("https://api.github.com:8443/x")
        self.assertEqual(seen, [])

    def test_resolution_to_private_address_refused(self):
        for addrs in (("10.0.0.5",), ("140.82.112.6", "127.0.0.1"), ("169.254.169.254",), ("::1",)):
            with self.subTest(addresses=addrs):
                fetch, seen = live({API: (200, commit_json())}, addresses=addrs)
                cap = replay_pin(record(), fetch, T0)
                self.assertEqual(cap["status"], "unavailable")
                self.assertEqual(seen, [])                       # no connection was opened

    def test_redirect_oversize_and_resolver_failure(self):
        fetch, _ = live({API: (302, b"")})
        self.assertEqual(replay_pin(record(), fetch, T0)["status"], "unavailable")
        fetch, _ = live({API: (200, b"x" * 100)}, max_bytes=50)
        self.assertEqual(replay_pin(record(), fetch, T0)["status"], "unavailable")

        def broken(*a, **k):
            raise socket.gaierror("no route")
        conn, _ = fake_connection({})
        fetch = LiveFetcher(resolver=broken, connection=conn)
        cap = replay_pin(record(), fetch, T0)                    # S12: unreachable is not PASS
        self.assertEqual(cap["status"], "unavailable")
        with tempfile.TemporaryDirectory() as td:
            write_capture(Path(td), cap)
            st = pin_state(record(), Path(td))
            self.assertEqual((st["status"], st["verified"]), ("unavailable", False))


class LedgerTests(unittest.TestCase):
    def test_captures_are_append_only_and_latest_wins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ok, _ = live({API: (200, commit_json())})
            down, _ = live({}, addresses=("10.0.0.1",))
            first = write_capture(root, replay_pin(record(), ok, T0))
            again = write_capture(root, replay_pin(record(), ok, T0))       # same second
            self.assertNotEqual(first, again)
            later = datetime(2026, 10, 14, tzinfo=timezone.utc)
            write_capture(root, replay_pin(record(), down, later))
            st = pin_state(record(), root)
            self.assertEqual(st["status"], "unavailable")       # a later failure is not hidden
            self.assertEqual(len(list(first.parent.glob("*.json"))), 3)

    def test_tampered_capture_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ok, _ = live({API: (200, commit_json())})
            path = write_capture(root, replay_pin(record(), ok, T0))
            cap = json.loads(path.read_text("utf-8"))
            cap["observed"]["commit"] = "1" * 40
            path.write_bytes(canonical_bytes(cap))
            self.assertEqual(pin_state(record(), root)["status"], "capture_invalid")

    def test_self_inconsistent_capture_detected(self):
        """a hand-edited capture that recomputes observed_sha256 is still caught when it contradicts itself"""
        ok, _ = live({API: (200, commit_json())})
        good = replay_pin(record(), ok, T0)
        edits = [
            lambda c: c.update(observed=dict(c["observed"], commit="1" * 40)),   # 'verified' a different commit
            lambda c: c.pop("network"),
            lambda c: c.update(network="cached"),
            lambda c: c.update(captured_at="yesterday"),
            lambda c: c.update(observed=["not", "a", "mapping"]),
        ]
        for i, edit in enumerate(edits):
            with self.subTest(edit=i), tempfile.TemporaryDirectory() as td:
                cap = copy.deepcopy(good)
                edit(cap)
                if isinstance(cap.get("observed"), dict):
                    cap["observed_sha256"] = sha256(canonical_bytes(cap["observed"]))
                path = write_capture(Path(td), dict(cap, captured_at=good["captured_at"]))
                path.write_bytes(canonical_bytes(cap))
                st = pin_state(record(), Path(td))
                self.assertEqual((st["status"], st["verified"]), ("capture_invalid", False))

    def test_capture_of_an_earlier_pin_is_history_not_current(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ok, _ = live({API: (200, commit_json())})
            write_capture(root, replay_pin(record(), ok, T0))
            newer = record(value="b" * 40)                     # S11: the record moved to a new pin
            st = pin_state(newer, root)
            self.assertEqual((st["status"], st["verified"]), ("declared_only", False))

    def test_declared_pin_without_capture_is_declared_only(self):        # S01, S04, S06
        for rec in (record(), record("arxiv_version", "2610.12345v2"), record("sha256", "c" * 64)):
            with tempfile.TemporaryDirectory() as td:
                result = verify_record(rec, Path(td))
                self.assertEqual(result["source_pin_status"], "declared_only")
                self.assertFalse(result["source_pin_verified"])


class ReplayCommandTests(unittest.TestCase):
    def test_replay_needs_exactly_one_mode(self):
        self.assertEqual(main(["replay-pins"]), 2)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(main(["replay-pins", "--network", "--fixtures", td]), 2)

    def test_replay_with_fixtures_writes_a_capture(self):
        rec = record()
        rec["id"] = "amvo-fixture-commit"
        with tempfile.TemporaryDirectory() as td:
            cases = Path(td) / "cases"
            cases.mkdir()
            (cases / "amvo-fixture-commit.json").write_text(json.dumps(rec), "utf-8")
            d = fixtures(td, [(f"https://api.github.com{API}", 200, commit_json())])
            code = main(["replay-pins", "--fixtures", str(d), "--cases", str(cases), "--root", td])
            self.assertEqual(code, 0)
            caps = list((Path(td) / "evidence" / "provenance" / "amvo-fixture-commit").glob("*.json"))
            self.assertEqual(len(caps), 1)
            report = Path(td) / "report.json"
            self.assertEqual(main(["verify", "--cases", str(cases), "--root", td, "--output", str(report)]), 0)
            case = json.loads(report.read_text("utf-8"))["cases"][0]
            self.assertEqual((case["source_pin_status"], case["source_pin_verified"]), ("fixture_only", False))


if __name__ == "__main__":
    unittest.main()
