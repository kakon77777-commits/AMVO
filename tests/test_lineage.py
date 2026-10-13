"""P1-B: append-only correction / withdrawal events, tested on synthetic records only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from amvo.cli import main
from amvo.core import RecordError, audit_public, canonical_bytes, report
from amvo.lineage import (GENESIS, event_sha256, ledger_head, lineage, load_events, next_event,
                          write_event)

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "cases" / "amvo-synthetic-fraction.json").read_text("utf-8"))
T = ["2026-10-13T10:00:00Z", "2026-10-13T11:00:00Z", "2026-10-13T12:00:00Z", "2026-10-13T13:00:00Z",
     "2026-10-13T14:00:00Z", "2026-10-13T15:00:00Z"]
NOTICE = "https://arxiv.org/abs/2610.12345v3"


def rec(rid, statement="1/3 + 1/6 = 1/2"):
    r = copy.deepcopy(BASE)
    r["id"], r["title"] = rid, f"Synthetic version {rid}"
    r["claim"]["statement"] = statement
    return r


A, B, C = rec("amvo-syn-a"), rec("amvo-syn-b", "1/2 + 1/4 = 3/4"), rec("amvo-syn-c", "1/5 + 1/5 = 2/5")
B["checks"][0].update(lhs=["1/2", "1/4"], rhs=["3/4"])
C["checks"][0].update(lhs=["1/5", "1/5"], rhs=["2/5"])
RECORDS = [A, B, C]


def ledger(*steps, records=RECORDS):
    """steps: (type, target, extra) applied in order through next_event"""
    events = []
    for i, (kind, target, extra) in enumerate(steps):
        kw = {"source_url": NOTICE} if kind != "supersedes" else {}
        kw.update(extra)
        events.append(next_event(records, events, kind, target, rationale=f"synthetic {kind}",
                                 recorded_by="AMVO maintainers", recorded_at=T[i], **kw))
    return events


def project(td, records=RECORDS, events=()):
    root = Path(td)
    (root / "cases").mkdir()
    for r in records:
        (root / "cases" / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False), "utf-8")
    for ev in events:
        write_event(root / "events", ev)
    return root


class LineageTests(unittest.TestCase):
    def test_withdrawal_keeps_outcome_and_marks_state(self):        # S10
        events = ledger(("withdraws", "amvo-syn-a", {}))
        lin = lineage(RECORDS, events)
        self.assertEqual((lin["amvo-syn-a"]["state"], lin["amvo-syn-a"]["withdrawn_by"]), ("withdrawn", "ev-000001"))
        self.assertEqual(lin["amvo-syn-b"]["state"], "current")
        result = report(RECORDS, ROOT, None, lin, ledger_head(events))
        a = result["cases"][0]
        self.assertEqual(a["outcome"], "bounded_checks_pass")       # the verdict is not rewritten
        self.assertEqual(a["lineage"]["state"], "withdrawn")
        self.assertEqual(result["event_ledger"], {"events": 1, "head_sha256": event_sha256(events[0])})

    def test_supersede_keeps_old_version_and_its_objections(self):   # S11
        events = ledger(("rebuttal", "amvo-syn-a", {}), ("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}),
                        ("corrects", "amvo-syn-b", {}))
        lin = lineage(RECORDS, events)
        self.assertEqual(lin["amvo-syn-a"]["state"], "superseded")
        self.assertEqual(lin["amvo-syn-a"]["superseded_by"], "amvo-syn-b")
        self.assertEqual(lin["amvo-syn-a"]["objections"], ["ev-000001"])
        self.assertEqual(lin["amvo-syn-b"]["supersedes"], ["amvo-syn-a"])
        self.assertEqual(lin["amvo-syn-b"]["corrections"], ["ev-000003"])
        self.assertEqual(lin["amvo-syn-b"]["state"], "current")
        self.assertEqual(lin["amvo-syn-b"]["events"], ["ev-000002", "ev-000003"])

    def test_withdrawn_wins_over_superseded(self):
        events = ledger(("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}), ("withdraws", "amvo-syn-a", {}))
        self.assertEqual(lineage(RECORDS, events)["amvo-syn-a"]["state"], "withdrawn")

    def test_editing_a_referenced_record_is_detected(self):
        events = ledger(("corrects", "amvo-syn-a", {}))
        edited = copy.deepcopy(RECORDS)
        edited[0]["claim"]["statement"] = "1/3 + 1/6 = 1/2 (quietly reworded)"
        with self.assertRaisesRegex(RecordError, "changed after this event"):
            lineage(edited, events)
        newer = copy.deepcopy(RECORDS)
        newer[1]["title"] = "edited newer version"
        events = ledger(("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}))
        with self.assertRaisesRegex(RecordError, "changed after this event"):
            lineage(newer, events)

    def test_removing_a_referenced_record_is_detected(self):
        events = ledger(("withdraws", "amvo-syn-c", {}))
        with self.assertRaisesRegex(RecordError, "does not exist"):
            lineage(RECORDS[:2], events)

    def test_conflicting_events_refused(self):
        bad = [
            [("withdraws", "amvo-syn-a", {}), ("withdraws", "amvo-syn-a", {})],
            [("supersedes", "amvo-syn-a", {"by": "amvo-syn-a"})],
            [("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}), ("supersedes", "amvo-syn-a", {"by": "amvo-syn-c"})],
            [("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}), ("supersedes", "amvo-syn-b", {"by": "amvo-syn-a"})],
            [("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}), ("supersedes", "amvo-syn-b", {"by": "amvo-syn-c"}),
             ("supersedes", "amvo-syn-c", {"by": "amvo-syn-a"})],
            [("supersedes", "amvo-syn-a", {"by": "amvo-syn-missing"})],
            [("supersedes", "amvo-syn-a", {})],
            [("withdraws", "amvo-syn-a", {"by": "amvo-syn-b"})],
            [("withdraws", "amvo-syn-missing", {})],
        ]
        for steps in bad:
            with self.subTest(steps=steps), self.assertRaises(RecordError):
                ledger(*steps)


class LedgerFileTests(unittest.TestCase):
    def events_on_disk(self, td, steps):
        root = project(td, events=ledger(*steps))
        return root, root / "events"

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root, evdir = self.events_on_disk(td, [("rebuttal", "amvo-syn-a", {}), ("withdraws", "amvo-syn-a", {})])
            events = load_events(evdir)
            self.assertEqual([e["event_id"] for e in events], ["ev-000001", "ev-000002"])
            self.assertEqual(events[0]["prev_sha256"], GENESIS)
            self.assertEqual(events[1]["prev_sha256"], event_sha256(events[0]))

    def test_editing_an_earlier_event_breaks_the_chain(self):
        with tempfile.TemporaryDirectory() as td:
            root, evdir = self.events_on_disk(td, [("rebuttal", "amvo-syn-a", {}), ("corrects", "amvo-syn-b", {})])
            first = evdir / "ev-000001.json"
            ev = json.loads(first.read_text("utf-8"))
            ev["rationale"] = "rewritten later"
            first.write_bytes(canonical_bytes(ev))
            with self.assertRaisesRegex(RecordError, "prev_sha256"):
                load_events(evdir)

    def test_removing_or_renumbering_an_event_detected(self):
        steps = [("rebuttal", "amvo-syn-a", {}), ("corrects", "amvo-syn-b", {}), ("withdraws", "amvo-syn-c", {})]
        with tempfile.TemporaryDirectory() as td:
            root, evdir = self.events_on_disk(td, steps)
            (evdir / "ev-000002.json").unlink()
            with self.assertRaisesRegex(RecordError, "gap"):
                load_events(evdir)
        with tempfile.TemporaryDirectory() as td:
            root, evdir = self.events_on_disk(td, steps)
            (evdir / "ev-000003.json").rename(evdir / "ev-000004.json")
            with self.assertRaisesRegex(RecordError, "filename and seq"):
                load_events(evdir)

    def test_backdating_and_shape_errors_refused(self):
        events = ledger(("rebuttal", "amvo-syn-a", {}), ("corrects", "amvo-syn-a", {}))
        mutations = {
            "earlier time": lambda e: e[1].update(recorded_at="2026-10-12T00:00:00Z"),
            "local time": lambda e: e[0].update(recorded_at="2026-10-13 10:00:00"),
            "unknown field": lambda e: e[0].update(note="extra"),
            "missing source": lambda e: e[0].pop("source_url"),
            "private source": lambda e: e[0].update(source_url="https://127.0.0.1/notice"),
            "non-https source": lambda e: e[0].update(source_url="http://arxiv.org/abs/2610.12345v3"),
            "bool seq": lambda e: e[0].update(seq=True),
            "wrong id": lambda e: e[0].update(event_id="ev-1"),
            "blank rationale": lambda e: e[0].update(rationale="  "),
            "unknown type": lambda e: e[0].update(type="retracts"),
            "short hash": lambda e: e[0].update(target_sha256="abc"),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as td:
                evs = copy.deepcopy(events)
                mutate(evs)
                if name not in ("earlier time",):
                    evs[1]["prev_sha256"] = event_sha256(evs[0])      # keep the chain itself consistent
                evdir = Path(td) / "events"
                evdir.mkdir()
                for i, ev in enumerate(evs, start=1):
                    (evdir / f"ev-{i:06d}.json").write_bytes(canonical_bytes(ev))
                with self.assertRaises(RecordError):
                    lineage(RECORDS, load_events(evdir))

    def test_stray_file_and_overwrite_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root, evdir = self.events_on_disk(td, [("rebuttal", "amvo-syn-a", {})])
            ev = load_events(evdir)[0]
            with self.assertRaises(FileExistsError):
                write_event(evdir, ev)                                  # never overwrite
            (evdir / "notes.txt").write_text("x", "utf-8")
            with self.assertRaisesRegex(RecordError, "unexpected file"):
                load_events(evdir)

    def test_audit_screens_event_text(self):
        events = ledger(("rebuttal", "amvo-syn-a", {}))
        events[0]["rationale"] = "see api_key=abcdefghijklmnop"
        self.assertEqual(audit_public(RECORDS, events), ["ev-000001: suspicious credential pattern"])


class EventCommandTests(unittest.TestCase):
    def run_cli(self, root, *args):
        return main([args[0], "--cases", str(root / "cases"), "--root", str(root), *args[1:]])

    def test_record_event_then_report_and_site(self):
        with tempfile.TemporaryDirectory() as td:
            root = project(td)
            self.assertEqual(self.run_cli(root, "record-event", "--type", "withdraws", "--target", "amvo-syn-a",
                                          "--source-url", NOTICE, "--rationale", "withdrawn by its authors",
                                          "--recorded-by", "AMVO maintainers"), 0)
            self.assertEqual(self.run_cli(root, "record-event", "--type", "supersedes", "--target", "amvo-syn-b",
                                          "--by", "amvo-syn-c", "--rationale", "a newer version",
                                          "--recorded-by", "AMVO maintainers"), 0)
            self.assertEqual(sorted(p.name for p in (root / "events").iterdir()), ["ev-000001.json", "ev-000002.json"])
            self.assertEqual(self.run_cli(root, "validate"), 0)
            out = root / "report.json"
            self.assertEqual(self.run_cli(root, "verify", "--output", str(out)), 0)
            cases = {c["id"]: c for c in json.loads(out.read_text("utf-8"))["cases"]}
            self.assertEqual(cases["amvo-syn-a"]["lineage"]["state"], "withdrawn")
            self.assertEqual(cases["amvo-syn-b"]["lineage"]["superseded_by"], "amvo-syn-c")
            site = root / "site"
            self.assertEqual(self.run_cli(root, "build-site", "--output", str(site)), 0)
            data = json.loads((site / "data" / "index.json").read_text("utf-8"))
            self.assertEqual([e["event_id"] for e in data["events"]], ["ev-000001", "ev-000002"])

    def test_record_event_refusals_write_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = project(td)
            self.assertEqual(self.run_cli(root, "record-event", "--type", "withdraws", "--target", "amvo-syn-a"), 2)
            self.assertEqual(self.run_cli(root, "record-event", "--type", "withdraws", "--target", "amvo-syn-x",
                                          "--source-url", NOTICE, "--rationale", "r", "--recorded-by", "m"), 2)
            self.assertEqual(self.run_cli(root, "record-event", "--type", "withdraws", "--target", "amvo-syn-a",
                                          "--rationale", "no public notice", "--recorded-by", "m"), 2)
            self.assertFalse((root / "events").exists())

    def test_a_changed_record_fails_every_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = project(td, events=ledger(("corrects", "amvo-syn-a", {})))
            edited = copy.deepcopy(A)
            edited["title"] = "quietly retitled"
            (root / "cases" / "amvo-syn-a.json").write_text(json.dumps(edited), "utf-8")
            for command in ("validate", "audit-public", "verify"):
                with self.subTest(command=command):
                    self.assertEqual(self.run_cli(root, command, "--output", str(root / "r.json"))
                                     if command == "verify" else self.run_cli(root, command), 2)


if __name__ == "__main__":
    unittest.main()
