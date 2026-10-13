"""P0: the JSON Schema and the Python runtime agree.

The runtime is the authority; the schema is the published contract. They may differ in one
direction only: every record the schema rejects, the runtime rejects too, and every rule the
runtime adds is one of the documented runtime-only rules below (semantics a JSON Schema
cannot state, such as a calendar-valid date, a zero denominator or a public host).

A small validator for the subset of JSON Schema 2020-12 the contract uses is included so the
test needs nothing outside the standard library.
"""
import copy
import json
import re
import tomllib
import unittest
from pathlib import Path

import amvo
from amvo import core
from amvo.core import RecordError, validate_record

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "case.schema.json").read_text(encoding="utf-8"))


def _resolve(schema, ref):
    assert ref.startswith("#/")
    node = SCHEMA
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def schema_errors(value, schema, path="$"):
    """errors of `value` against the supported subset of JSON Schema; [] means valid"""
    if "$ref" in schema:
        return schema_errors(value, _resolve(SCHEMA, schema["$ref"]), path)
    errs = []
    t = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str, "integer": int}
    if t is not None and (not isinstance(value, kinds[t]) or (t == "integer" and isinstance(value, bool))):
        return [f"{path}: not {t}"]
    if t == "integer" and value < schema.get("minimum", value):
        return [f"{path}: minimum"]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: const")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: enum")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 10 ** 9):
            errs.append(f"{path}: length")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errs.append(f"{path}: pattern")
        # "format" is an annotation, not an assertion, by default in 2020-12 - so a calendar-
        # invalid date is a runtime-only rejection, as most published validators would treat it
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10 ** 9):
            errs.append(f"{path}: items count")
        if "items" in schema:
            for i, item in enumerate(value):
                errs += schema_errors(item, schema["items"], f"{path}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}: missing {key}")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                errs += schema_errors(value[key], sub, f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            errs += [f"{path}: extra {k}" for k in value if k not in props]
    if "oneOf" in schema:
        if sum(1 for sub in schema["oneOf"] if not schema_errors(value, sub, path)) != 1:
            errs.append(f"{path}: oneOf")
    if "not" in schema and not schema_errors(value, schema["not"], path):
        errs.append(f"{path}: not")
    for sub in schema.get("allOf", []):
        if "if" in sub:
            if not schema_errors(value, sub["if"], path):
                errs += schema_errors(value, sub["then"], path)
        else:
            errs += schema_errors(value, sub, path)
    return errs


def runtime_rejects(record):
    try:
        validate_record(record)
    except RecordError:
        return True
    return False


SYNTH = json.loads((ROOT / "cases" / "amvo-synthetic-fraction.json").read_text("utf-8"))


def claim():
    rec = copy.deepcopy(SYNTH)
    rec["type"] = "claim"
    rec["source"]["url"] = "https://github.com/example/public-math"
    rec["source"]["pin"] = {"kind": "git_commit", "value": "a" * 40}
    return rec


def mutation(name, fn, base=claim):
    rec = base()
    fn(rec)
    return name, rec


def setp(path, value):
    def fn(rec):
        node = rec
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
    return fn


def delp(path):
    def fn(rec):
        node = rec
        for k in path[:-1]:
            node = node[k]
        del node[path[-1]]
    return fn


# rules the runtime enforces that the schema does not, by design (name -> reason)
RUNTIME_ONLY = {
    "calendar date": "format: date is advisory in JSON Schema validators",
    "zero denominator": "a/0 matches the fraction pattern",
    "public host": "local, private, numeric or single-label hosts need resolution semantics",
    "url characters": "whitespace and control characters inside a URL",
    "duplicate check id": "uniqueness of a property across array items",
    "blank text": "whitespace-only strings pass minLength",
}

CASES = [
    ("valid claim", claim(), None),
    ("valid fixture", copy.deepcopy(SYNTH), None),
    mutation("bad schema version", setp(["schema_version"], "0.2")) + (None,),
    mutation("bad id", setp(["id"], "AMVO-x")) + (None,),
    mutation("unknown type", setp(["type"], "theorem")) + (None,),
    mutation("type not string", setp(["type"], ["claim"])) + (None,),
    mutation("empty title", setp(["title"], "")) + (None,),
    mutation("long title", setp(["title"], "x" * 241)) + (None,),
    mutation("extra top field", setp(["notes"], "x")) + (None,),
    mutation("missing review", delp(["review"])) + (None,),
    mutation("private source", setp(["source", "public"], False)) + (None,),
    mutation("no authors", setp(["source", "authors"], [])) + (None,),
    mutation("long author", setp(["source", "authors"], ["a" * 201])) + (None,),
    mutation("extra source field", setp(["source", "internal"], "x")) + (None,),
    mutation("http url", setp(["source", "url"], "http://example.org/a")) + (None,),
    mutation("query url", setp(["source", "url"], "https://example.org/a?token=1")) + (None,),
    mutation("fragment url", setp(["source", "url"], "https://example.org/a#x")) + (None,),
    mutation("localhost url", setp(["source", "url"], "https://localhost/a"), ) + ("public host",),
    mutation("numeric host", setp(["source", "url"], "https://127.1/a")) + ("public host",),
    mutation("hex host", setp(["source", "url"], "https://0x7f000001/a")) + ("public host",),
    mutation("decimal host", setp(["source", "url"], "https://2130706433/a")) + ("public host",),
    mutation("dotted localhost", setp(["source", "url"], "https://localhost./a")) + ("public host",),
    mutation("single label", setp(["source", "url"], "https://intranet/a")) + ("public host",),
    mutation("private v4", setp(["source", "url"], "https://10.0.0.1/a")) + ("public host",),
    mutation("metadata ip", setp(["source", "url"], "https://169.254.169.254/a")) + ("public host",),
    mutation("v6 loopback", setp(["source", "url"], "https://[::1]/a")) + ("public host",),
    mutation("v6 ula", setp(["source", "url"], "https://[fd00::1]/a")) + ("public host",),
    mutation("space in url", setp(["source", "url"], "https://example.org/a b")) + ("url characters",),
    mutation("bad date", setp(["source", "captured_at"], "2026-02-30")) + ("calendar date",),
    mutation("claim without pin", delp(["source", "pin"])) + (None,),
    mutation("branch pin", setp(["source", "pin"], {"kind": "git_commit", "value": "main"})) + (None,),
    mutation("unversioned arxiv", setp(["source", "pin"], {"kind": "arxiv_version", "value": "2610.12345"})) + (None,),
    mutation("upper hex sha", setp(["source", "pin"], {"kind": "sha256", "value": "A" * 64})) + (None,),
    mutation("pin extra", setp(["source", "pin"], {"kind": "sha256", "value": "a" * 64, "x": 1})) + (None,),
    mutation("bad rights", setp(["rights", "mode"], "public_domain")) + (None,),
    mutation("blank rights note", setp(["rights", "note"], "   ")) + ("blank text",),
    mutation("bad review", setp(["review", "status"], "verified")) + (None,),
    mutation("claim extra", setp(["claim", "proof"], "trust me")) + (None,),
    mutation("zero denominator", setp(["checks", 0, "rhs"], ["1/0"])) + ("zero denominator",),
    mutation("81 digits", setp(["checks", 0, "rhs"], ["1" * 81])) + (None,),
    mutation("decimal point", setp(["checks", 0, "rhs"], ["0.5"])) + (None,),
    mutation("empty terms", setp(["checks", 0, "lhs"], [])) + (None,),
    mutation("unknown check kind", setp(["checks", 0, "kind"], "lean_kernel")) + (None,),
    mutation("check extra", setp(["checks", 0, "extra"], 1)) + (None,),
    mutation("duplicate check id", lambda r: r["checks"].append(copy.deepcopy(r["checks"][0]))) + ("duplicate check id",),
    mutation("traversal evidence", setp(["checks"], [{"id": "h", "kind": "file_sha256", "path": "evidence/../x", "sha256": "a" * 64}])) + (None,),
    mutation("dot evidence", setp(["checks"], [{"id": "h", "kind": "file_sha256", "path": "evidence/./x", "sha256": "a" * 64}])) + (None,),
    mutation("empty segment", setp(["checks"], [{"id": "h", "kind": "file_sha256", "path": "evidence//x", "sha256": "a" * 64}])) + (None,),
    mutation("backslash evidence", setp(["checks"], [{"id": "h", "kind": "file_sha256", "path": "evidence\\x", "sha256": "a" * 64}])) + (None,),
    mutation("outside evidence", setp(["checks"], [{"id": "h", "kind": "file_sha256", "path": "cases/x.json", "sha256": "a" * 64}])) + (None,),
    mutation("good evidence", setp(["checks"], [{"id": "h", "kind": "file_sha256", "path": "evidence/a/b.json", "sha256": "a" * 64}])) + ("valid",),
    mutation("intake with checks", setp(["type"], "public_source_intake")) + (None,),
]


class SchemaRuntimeConsistency(unittest.TestCase):
    def test_fixtures_are_schema_valid(self):
        for path in sorted((ROOT / "cases").glob("*.json")):
            with self.subTest(case=path.name):
                self.assertEqual(schema_errors(json.loads(path.read_text("utf-8")), SCHEMA), [])

    def test_schema_rejection_implies_runtime_rejection(self):
        runtime_only_seen = set()
        for name, rec, rule in CASES:
            with self.subTest(case=name):
                s_rej = bool(schema_errors(rec, SCHEMA))
                r_rej = runtime_rejects(rec)
                if s_rej:
                    self.assertTrue(r_rej, f"schema rejects but runtime accepts: {name}")
                if r_rej and not s_rej:
                    self.assertIn(rule, RUNTIME_ONLY, f"undocumented runtime-only rule: {name}")
                    runtime_only_seen.add(rule)
                if rule == "valid" or name.startswith("valid"):
                    self.assertFalse(s_rej or r_rej, f"valid record rejected: {name}")
        # every documented runtime-only rule is exercised at least once
        self.assertEqual(runtime_only_seen, set(RUNTIME_ONLY))

    def test_enums_and_patterns_mirror_the_runtime(self):
        props = SCHEMA["properties"]
        self.assertEqual(set(props["type"]["enum"]), core.CASE_TYPES)
        self.assertEqual(set(props["rights"]["properties"]["mode"]["enum"]), core.RIGHTS_MODES)
        self.assertEqual(set(props["review"]["properties"]["status"]["enum"]), core.REVIEW_STATUSES)
        kinds = {c["properties"]["kind"]["const"] for c in props["checks"]["items"]["oneOf"]}
        self.assertEqual(kinds, core.CHECK_TYPES)
        pins = {p["properties"]["kind"]["const"]: p["properties"]["value"]["pattern"]
                for p in props["source"]["properties"]["pin"]["oneOf"]}
        self.assertEqual(set(pins), core.PIN_KINDS)
        norm = lambda r: r.replace("(?:", "(")
        self.assertEqual(norm(pins["git_commit"]), norm(core.GIT_COMMIT_PATTERN.pattern))
        self.assertEqual(norm(pins["arxiv_version"]), norm(core.ARXIV_VERSION_PATTERN.pattern))
        self.assertEqual(norm(pins["sha256"]), norm(core.HASH_PATTERN.pattern))
        self.assertEqual(norm(props["id"]["pattern"]), norm(core.ID_PATTERN.pattern))
        self.assertEqual(norm(SCHEMA["$defs"]["fractions"]["items"]["pattern"]), norm(core.FRACTION_PATTERN.pattern))
        self.assertEqual(SCHEMA["$defs"]["fractions"]["maxItems"], core.MAX_TERMS)
        self.assertEqual(props["checks"]["maxItems"], core.MAX_CHECKS)
        self.assertEqual(props["schema_version"]["const"], core.VERSION)

    def test_versions_agree(self):
        meta = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        self.assertEqual(meta["project"]["version"], core.ENGINE_VERSION)
        self.assertEqual(amvo.__version__, core.ENGINE_VERSION)
        self.assertTrue(core.VERIFIER_ID.endswith("v" + core.ENGINE_VERSION))
        self.assertIn(core.ENGINE_VERSION, SCHEMA["title"])


if __name__ == "__main__":
    unittest.main()
