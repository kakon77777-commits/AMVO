"""P1-B: the event JSON Schema and the runtime agree, in the same one-way sense as the case schema."""
import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lineage import RECORDS, ledger                          # noqa: E402
from test_schema_consistency import schema_errors                 # noqa: E402

from amvo import core, lineage as lin                             # noqa: E402
from amvo.core import RecordError, canonical_bytes                # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVENT_SCHEMA = json.loads((ROOT / "schemas" / "event.schema.json").read_text("utf-8"))

# rules the runtime enforces that a JSON Schema cannot state
RUNTIME_ONLY = {"calendar time", "blank text", "public host", "event id matches seq", "hash chain",
                "record exists and is unchanged"}

GOOD = ledger(("rebuttal", "amvo-syn-a", {}), ("supersedes", "amvo-syn-a", {"by": "amvo-syn-b"}))


def mutate(index, fn, rule):
    def build():
        evs = copy.deepcopy(GOOD)
        fn(evs[index])
        if index == 0 and rule != "hash chain":
            evs[1]["prev_sha256"] = lin.event_sha256(evs[0])
        return evs
    return build, rule


def put(key, value):
    return lambda ev: ev.update({key: value})


def drop(key):
    return lambda ev: ev.pop(key)


CASES = {
    "valid": (lambda: copy.deepcopy(GOOD), "valid"),
    "valid supersedes with source": mutate(1, put("source_url", "https://arxiv.org/abs/2610.12345v3"), "valid"),
    "schema version": mutate(0, put("event_schema", "0.2"), None),
    "seq zero": mutate(0, put("seq", 0), None),
    "seq string": mutate(0, put("seq", "1"), None),
    "seq bool": mutate(0, put("seq", True), None),
    "event id shape": mutate(0, put("event_id", "ev-1"), None),
    "event id other seq": mutate(0, put("event_id", "ev-000009"), "event id matches seq"),
    "type": mutate(0, put("type", "retracts"), None),
    "target id": mutate(0, put("target", "Not An Id"), None),
    "target hash shape": mutate(0, put("target_sha256", "ABC"), None),
    "target hash other": mutate(0, put("target_sha256", "e" * 64), "record exists and is unchanged"),
    "target unknown": mutate(0, put("target", "amvo-syn-unknown"), "record exists and is unchanged"),
    "prev hash shape": mutate(1, put("prev_sha256", "0"), None),
    "prev hash other": mutate(1, put("prev_sha256", "d" * 64), "hash chain"),
    "source http": mutate(0, put("source_url", "http://arxiv.org/abs/2610.12345v3"), None),
    "source localhost": mutate(0, put("source_url", "https://localhost/notice"), "public host"),
    "source missing": mutate(0, drop("source_url"), None),
    "rationale missing": mutate(0, drop("rationale"), None),
    "rationale empty": mutate(0, put("rationale", ""), None),
    "rationale blank": mutate(0, put("rationale", "   "), "blank text"),
    "rationale too long": mutate(0, put("rationale", "x" * 1201), None),
    "recorded_by too long": mutate(0, put("recorded_by", "x" * 201), None),
    "recorded_at shape": mutate(0, put("recorded_at", "2026-10-13"), None),
    "recorded_at calendar": mutate(0, put("recorded_at", "2026-02-30T10:00:00Z"), "calendar time"),
    "extra field": mutate(0, put("note", "x"), None),
    "by on rebuttal": mutate(0, put("by", "amvo-syn-b"), None),
    "supersedes without by": mutate(1, drop("by"), None),
    "supersedes without by hash": mutate(1, drop("by_sha256"), None),
    "by id": mutate(1, put("by", "B"), None),
}


def runtime_rejects(events):
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for i, ev in enumerate(events, start=1):
            (d / f"ev-{i:06d}.json").write_bytes(canonical_bytes(ev))
        try:
            lin.lineage(RECORDS, lin.load_events(d))
        except RecordError:
            return True
    return False


class EventSchemaConsistency(unittest.TestCase):
    def test_schema_rejection_implies_runtime_rejection(self):
        seen = set()
        for name, (build, rule) in CASES.items():
            with self.subTest(case=name):
                events = build()
                s_rej = any(schema_errors(ev, EVENT_SCHEMA) for ev in events)
                r_rej = runtime_rejects(events)
                if s_rej:
                    self.assertTrue(r_rej, f"schema rejects but runtime accepts: {name}")
                if r_rej and not s_rej:
                    self.assertIn(rule, RUNTIME_ONLY, f"undocumented runtime-only rule: {name}")
                    seen.add(rule)
                if rule == "valid":
                    self.assertFalse(s_rej or r_rej, f"valid events rejected: {name}")
        self.assertEqual(seen, RUNTIME_ONLY)

    def test_schema_mirrors_runtime_constants(self):
        props = EVENT_SCHEMA["properties"]
        norm = lambda r: r.replace("(?:", "(")
        self.assertEqual(tuple(props["type"]["enum"]), lin.EVENT_TYPES)
        self.assertEqual(props["event_schema"]["const"], lin.EVENT_SCHEMA)
        self.assertEqual(norm(props["target"]["pattern"]), norm(core.ID_PATTERN.pattern))
        self.assertEqual(norm(props["by"]["pattern"]), norm(core.ID_PATTERN.pattern))
        self.assertEqual(props["recorded_at"]["pattern"], "^" + lin.RECORDED_AT.pattern + "$")
        self.assertEqual(set(EVENT_SCHEMA["required"]), lin.COMMON)
        self.assertEqual(set(props), set().union(*lin.FIELDS.values()))
        self.assertIn(core.ENGINE_VERSION, EVENT_SCHEMA["title"])
        self.assertIsNotNone(re.fullmatch(props["event_id"]["pattern"].strip("^$"), lin.event_id(1)))


if __name__ == "__main__":
    unittest.main()
