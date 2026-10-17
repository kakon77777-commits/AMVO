"""P1-C: the layered v0.2 registry — layering rules, duplicates, migration, honest counts."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_schema_consistency import schema_errors                 # noqa: E402
from _sandbox import small_registry                               # noqa: E402

from amvo.cli import main                                         # noqa: E402
from amvo.core import RecordError, canonical_bytes, list_records, sha256   # noqa: E402
from amvo.lineage import lineage, next_event                      # noqa: E402
from amvo.provenance import pin_state                             # noqa: E402
from amvo.registry import (LAYERS, STATUSES, canonical_url, check_registry, load_registry, locate,  # noqa: E402
                           migrate, object_sha256, ref, registry_report, validate_object, write_object)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "registry.schema.json").read_text("utf-8"))
CASE_SCHEMA = json.loads((ROOT / "schemas" / "case.schema.json").read_text("utf-8"))
RECORDS = list_records(ROOT / "cases")
URL = "https://arxiv.org/abs/2610.12345"


def o(kind, oid, **fields):
    return dict({"object_schema": "0.2", "kind": kind, "id": oid}, **fields)


def source(oid="amvo-src-paper", url=URL, origin="preprint"):
    return o("source", oid, title="A synthetic paper", publisher="Example Lab", authors=["A. Author"],
             canonical_url=url, origin_type=origin, public=True,
             rights={"mode": "metadata_only", "note": "metadata only"}, retrieved_at="2026-10-13")


def revision(src, oid="amvo-rev-paper-v2", value="2610.12345v2"):
    return o("revision", oid, source=ref(src), version_label=value,
             pin={"kind": "arxiv_version", "value": value}, captured_at="2026-10-13")


def claim(rev, oid, statement, claim_type="theorem"):
    return o("claim", oid, revision=ref(rev), claim_type=claim_type, statement=statement, scope="as stated")


def evidence(clm, oid, check):
    return o("evidence", oid, claim=ref(clm), check=check, bounded_claim="only the computed identity")


RATIONAL = {"id": "r", "kind": "rational_sum", "lhs": ["1/3", "1/6"], "rhs": ["1/2"]}
WRONG = {"id": "w", "kind": "rational_sum", "lhs": ["1/3", "1/3"], "rhs": ["1/2"]}


def paper():
    """one source, one revision, three claims of different types, evidence on one of them"""
    s = source()
    r = revision(s)
    t = claim(r, "amvo-clm-paper-thm-1", "Every widget is a gadget.")
    lm = claim(r, "amvo-clm-paper-lem-2", "A widget has two ends.", "lemma")
    cj = claim(r, "amvo-clm-paper-conj-3", "Every gadget is a widget.", "conjecture")
    e = evidence(lm, "amvo-evd-paper-lem-2-r", RATIONAL)
    return {x["id"]: x for x in (s, r, t, lm, cj, e)}


def fail_with(objects, message):
    def run(self):
        with self.assertRaisesRegex(RecordError, message):
            for obj in objects.values():
                validate_object(obj)
            check_registry(objects)
    return run


class LayeringTests(unittest.TestCase):
    def test_well_formed_registry_passes(self):
        index = check_registry(paper())
        self.assertEqual(len(index["claim"]), 3)

    def test_editing_a_referenced_object_is_detected(self):
        objs = paper()
        objs["amvo-clm-paper-lem-2"]["statement"] = "A widget has three ends."   # evidence still points at the old text
        with self.assertRaisesRegex(RecordError, "changed after it was referenced"):
            check_registry(objs)
        objs = paper()
        del objs["amvo-rev-paper-v2"]
        with self.assertRaisesRegex(RecordError, "not registered"):
            check_registry(objs)

    def test_layers_cannot_carry_each_others_fields(self):
        objs = paper()
        for oid, extra in (("amvo-clm-paper-thm-1", {"status": "verified"}),
                           ("amvo-evd-paper-lem-2-r", {"result": "pass"}),
                           ("amvo-evd-paper-lem-2-r", {"statement": "rewritten by evidence"})):
            with self.subTest(field=extra), self.assertRaisesRegex(RecordError, "unknown"):
                validate_object(dict(objs[oid], **extra))
        review = o("review", "amvo-rvw-x", claim=ref(objs["amvo-clm-paper-thm-1"]), reviewer_class="amvo_maintainer",
                   independence="i", conflicts="none declared", scope="s", audit_state="in_progress", references=[])
        with self.assertRaisesRegex(RecordError, "unknown"):
            validate_object(dict(review, canonical_url=URL))       # a review cannot touch the source
        with self.assertRaisesRegex(RecordError, "must name a evidence"):
            validate_object(o("publication", "amvo-pub-x", title="t", claims=[ref(objs["amvo-clm-paper-thm-1"])],
                              evidence=[ref(objs["amvo-clm-paper-thm-1"])], editorial_note="n",
                              license_review="pending"))           # a claim cannot stand in for evidence

    def test_cross_layer_rules(self):
        objs = paper()
        thm, lem = objs["amvo-clm-paper-thm-1"], objs["amvo-clm-paper-lem-2"]
        fmt = o("formal_target", "amvo-fmt-thm-1", claim=ref(thm), language="lean4", theorem_name="widget_gadget",
                exact_statement="theorem widget_gadget : True", code_pin={"kind": "git_commit", "value": "a" * 40},
                toolchain="lean 4.x (synthetic)", axiom_policy="standard axioms only", correspondence="direct")
        wrong = evidence(lem, "amvo-evd-lem-with-thm-target", {"id": "q", "kind": "rational_sum", "lhs": ["1"], "rhs": ["1"]})
        wrong["formal_target"] = ref(fmt)
        with self.assertRaisesRegex(RecordError, "formal target belongs to another claim"):
            check_registry(dict(objs, **{fmt["id"]: fmt, wrong["id"]: wrong}))
        pub = o("publication", "amvo-pub-x", title="t", claims=[ref(thm)], evidence=[ref(objs["amvo-evd-paper-lem-2-r"])],
                editorial_note="n", license_review="pending")
        with self.assertRaisesRegex(RecordError, "cites evidence of a claim it does not report"):
            check_registry(dict(objs, **{pub["id"]: pub}))

    def test_claims_rest_on_pinned_revisions(self):                     # T06
        s = source()
        loose = o("revision", "amvo-rev-paper-rolling", source=ref(s), version_label="latest", pin=None,
                  captured_at="2026-10-13")
        with self.assertRaisesRegex(RecordError, "needs an immutable pin"):
            check_registry({s["id"]: s, loose["id"]: loose})
        syn = source("amvo-src-syn", "https://example.org/syn", "synthetic")
        syn_rev = o("revision", "amvo-rev-syn-v1", source=ref(syn), version_label="v1", pin=None, captured_at="2026-10-13")
        c = claim(syn_rev, "amvo-clm-syn", "1/3 + 1/6 = 1/2", "computation")
        check_registry({x["id"]: x for x in (syn, syn_rev, c)})       # a synthetic fixture may be unpinned

    def test_duplicates_are_refused(self):
        objs = paper()
        for spelling in (URL + "/", "https://www.arxiv.org/abs/2610.12345", URL):
            with self.subTest(url=spelling):
                twin = source("amvo-src-paper-again", canonical_url(spelling))
                with self.assertRaisesRegex(RecordError, "duplicate source URL"):
                    check_registry(dict(objs, **{twin["id"]: twin}))
        s = objs["amvo-src-paper"]
        cases = {
            "revision": revision(s, "amvo-rev-paper-v2-again"),
            "claim": claim(objs["amvo-rev-paper-v2"], "amvo-clm-again", "Every   widget is a\ngadget."),
            "evidence": evidence(objs["amvo-clm-paper-lem-2"], "amvo-evd-again", dict(RATIONAL, id="other-id")),
        }
        for what, twin in cases.items():
            with self.subTest(duplicate=what), self.assertRaisesRegex(RecordError, "duplicate"):
                check_registry(dict(objs, **{twin["id"]: twin}))
        v3 = revision(s, "amvo-rev-paper-v3", "2610.12345v3")         # S11: a new version is a new revision
        check_registry(dict(objs, **{v3["id"]: v3}))

    def test_source_urls_are_written_canonically(self):
        self.assertEqual(canonical_url("https://arxiv.org/abs/2610.12345v2"), URL)
        self.assertEqual(canonical_url("https://arxiv.org/pdf/2610.12345v2.pdf"), URL)
        self.assertEqual(canonical_url("https://github.com/OpenAI/Math.git"), "https://github.com/openai/math")
        self.assertEqual(canonical_url("https://github.com/openai/math/tree/main/x"), "https://github.com/openai/math")
        with self.assertRaisesRegex(RecordError, "canonical_url must be written"):
            validate_object(source(url="https://arxiv.org/abs/2610.12345v2"))  # versions belong in revisions

    def test_shape_refusals(self):
        objs = paper()
        bad = {
            "id prefix": dict(objs["amvo-clm-paper-thm-1"], id="amvo-rev-not-a-claim"),
            "independent review without references": o(
                "review", "amvo-rvw-x", claim=ref(objs["amvo-clm-paper-thm-1"]), reviewer_class="independent_mathematician",
                independence="i", conflicts="none", scope="s", audit_state="no_objection_in_scope", references=[]),
            "formal code pinned to arXiv": o(
                "formal_target", "amvo-fmt-x", claim=ref(objs["amvo-clm-paper-thm-1"]), language="lean4",
                theorem_name="t", exact_statement="s", code_pin={"kind": "arxiv_version", "value": "2610.12345v2"},
                toolchain="t", axiom_policy="a", correspondence="c"),
            "private host": source(url="https://10.0.0.1/paper"),
            "blank statement": dict(objs["amvo-clm-paper-thm-1"], statement="   "),
            "bad date": dict(objs["amvo-src-paper"], retrieved_at="2026-02-30"),
            "non-public": dict(objs["amvo-src-paper"], public=False),
        }
        for name, obj in bad.items():
            with self.subTest(case=name), self.assertRaises(RecordError):
                validate_object(obj)


class ReportTests(unittest.TestCase):
    def report(self, objs, root=ROOT, events=(), records=(), manifests=None):
        records = list(records)
        lin = lineage(records + list(objs.values()), list(events))
        return registry_report(objs, manifests or {}, root, lineages=lin, pin_lookup=pin_state)

    def test_a_paper_is_not_a_count_of_proved_theorems(self):          # P06, T01, T03
        r = self.report(paper())
        c = r["counts"]
        self.assertEqual((c["sources"], c["claims"], c["current_claims_bounded_pass"], c["current_claims_not_checked"]),
                         (1, 3, 1, 2))
        self.assertEqual(c["claims_by_type"], {"theorem": 1, "lemma": 1, "conjecture": 1})
        self.assertEqual((c["theorems_proved"], c["formal_kernel_runs"]), (0, 0))
        for cl in r["claims"]:
            self.assertFalse(cl["theorem_proved"])
            self.assertTrue(set(cl["statuses"]) <= set(STATUSES))
            self.assertFalse(any("VERIFIED" in s or "PROVED" in s for s in cl["statuses"]))
        by = {cl["id"]: cl["statuses"] for cl in r["claims"]}
        self.assertEqual(by["amvo-clm-paper-lem-2"], ["BOUNDED_PASS", "INDEPENDENT_REPLICATION_PENDING"])
        self.assertEqual(by["amvo-clm-paper-thm-1"], ["NOT_CHECKED", "INDEPENDENT_REPLICATION_PENDING"])

    def test_hash_only_evidence_is_reproducibility_not_a_pass(self):    # T02
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "evidence").mkdir()
            (root / "evidence" / "a.txt").write_bytes(b"artifact")
            objs = paper()
            e = evidence(objs["amvo-clm-paper-thm-1"], "amvo-evd-thm-hash",
                         {"id": "h", "kind": "file_sha256", "path": "evidence/a.txt", "sha256": sha256(b"artifact")})
            r = self.report(dict(objs, **{e["id"]: e}), root)
            st = {cl["id"]: cl["statuses"] for cl in r["claims"]}["amvo-clm-paper-thm-1"]
            self.assertIn("REPRODUCIBILITY_ONLY", st)
            self.assertNotIn("BOUNDED_PASS", st)

    def test_failing_check_formal_target_review_and_publication(self):
        objs = paper()
        thm = objs["amvo-clm-paper-thm-1"]
        bad = evidence(thm, "amvo-evd-thm-wrong", WRONG)                # V02
        fmt = o("formal_target", "amvo-fmt-thm-1", claim=ref(thm), language="lean4", theorem_name="widget_gadget",
                exact_statement="theorem widget_gadget : True", code_pin={"kind": "git_commit", "value": "a" * 40},
                toolchain="lean 4.x (synthetic)", axiom_policy="standard axioms only", correspondence="direct")
        objection = o("review", "amvo-rvw-thm-1", claim=ref(thm), reviewer_class="independent_mathematician",
                      independence="not an author", conflicts="none declared", scope="the main theorem",
                      audit_state="objection_raised", references=["https://example.org/review"])
        pub = o("publication", "amvo-pub-thm", title="t", claims=[ref(thm)], evidence=[ref(bad)],
                editorial_note="reports the failing check", license_review="metadata_only")
        r = self.report(dict(objs, **{x["id"]: x for x in (bad, fmt, objection, pub)}))
        cl = {c["id"]: c for c in r["claims"]}["amvo-clm-paper-thm-1"]
        self.assertEqual(cl["statuses"], ["CHECKS_NOT_PASSED", "SEMANTIC_ALIGNMENT_PENDING", "OBJECTION_OPEN",
                                          "INDEPENDENT_REPLICATION_PENDING", "PUBLISHED_REPORT"])
        self.assertEqual(cl["formal_kernel"], "not_run")                 # T04: no kernel ran
        self.assertEqual(r["counts"]["current_claims_checks_not_passed"], 1)

    def test_events_and_withdrawn_revisions_reach_claims(self):         # S10, T07
        objs = paper()
        records = [objs[k] for k in sorted(objs)]
        events = []
        events.append(next_event(records, events, "rebuttal", "amvo-clm-paper-lem-2", rationale="counterexample posted",
                                 recorded_by="AMVO maintainers", recorded_at="2026-10-13T10:00:00Z",
                                 source_url="https://example.org/counterexample"))
        events.append(next_event(records, events, "withdraws", "amvo-rev-paper-v2", rationale="withdrawn on arXiv",
                                 recorded_by="AMVO maintainers", recorded_at="2026-10-13T11:00:00Z",
                                 source_url="https://arxiv.org/abs/2610.12345v3"))
        r = self.report(objs, events=events)
        for cl in r["claims"]:
            self.assertEqual(cl["lineage"]["state"], "withdrawn")
            self.assertIn("WITHDRAWN", cl["statuses"])
        lem = {c["id"]: c for c in r["claims"]}["amvo-clm-paper-lem-2"]
        self.assertIn("OBJECTION_OPEN", lem["statuses"])
        self.assertIn("BOUNDED_PASS", lem["statuses"])                   # the computed result is kept, not erased
        self.assertEqual((r["counts"]["claims"], r["counts"]["claims_current"],
                          r["counts"]["current_claims_bounded_pass"]), (3, 0, 0))


class MigrationTests(unittest.TestCase):
    def test_repository_registry_holds_exactly_the_migration_of_the_cases(self):
        """every migrated object is what migrating the cases gives today; anything else in the
        registry was registered directly (it has no manifest) and must still validate"""
        objects, manifests = load_registry(ROOT / "registry")
        fresh_objects, fresh_manifests = migrate(RECORDS, {}, {})
        self.assertEqual(manifests, {m["case_id"]: m for m in fresh_manifests})
        migrated = {item["id"] for m in manifests.values() for item in m["objects"]}
        self.assertEqual({k: objects[k] for k in migrated}, {x["id"]: x for x in fresh_objects})
        check_registry(objects, manifests, RECORDS)

    def test_migration_is_deterministic_idempotent_and_keeps_the_cases(self):
        before = {p.name: p.read_bytes() for p in (ROOT / "cases").glob("*.json")}
        a = migrate(RECORDS, {}, {})
        b = migrate(copy.deepcopy(RECORDS), {}, {})
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))
        objects = {x["id"]: x for x in a[0]}
        manifests = {m["case_id"]: m for m in a[1]}
        self.assertEqual(migrate(RECORDS, objects, manifests), ([], []))
        self.assertEqual(before, {p.name: p.read_bytes() for p in (ROOT / "cases").glob("*.json")})
        for rec in RECORDS:
            self.assertEqual(manifests[rec["id"]]["record_sha256"], object_sha256(rec))

    def test_migration_maps_layers_honestly(self):
        objects, manifests = (lambda a: ({x["id"]: x for x in a[0]}, {m["case_id"]: m for m in a[1]}))(
            migrate(RECORDS, {}, {}))
        kinds = sorted(x["kind"] for x in objects.values())
        self.assertEqual(kinds.count("claim"), 1)                       # intake placeholders are not claims
        self.assertEqual(kinds.count("source"), 2)                      # two openai/math records, one source
        snap = manifests["amvo-openai-math-snapshot-1581d4c"]
        self.assertEqual(snap["reused"], ["amvo-src-github-com-openai-math"])
        self.assertTrue(any("differs in: rights" in n for n in snap["not_carried"]))
        r = registry_report(objects, manifests, ROOT, lineages=lineage(RECORDS + list(objects.values()), []),
                            pin_lookup=pin_state)
        rev = {v["id"]: v for v in r["revisions"]}["amvo-rev-github-com-openai-math-1581d4cbdd69a0fa"]
        self.assertEqual((rev["pin_status"], rev["pin_verified"]), ("verified", True))   # via the v0.1 capture
        self.assertEqual(r["counts"]["claims"], 1)

    def test_changed_or_removed_v01_record_is_detected(self):
        objects, manifests = (lambda a: ({x["id"]: x for x in a[0]}, {m["case_id"]: m for m in a[1]}))(
            migrate(RECORDS, {}, {}))
        edited = copy.deepcopy(RECORDS)
        edited[0]["title"] = "quietly retitled"
        with self.assertRaisesRegex(RecordError, "changed after migration"):
            check_registry(objects, manifests, edited)
        with self.assertRaisesRegex(RecordError, "record is gone"):
            check_registry(objects, manifests, RECORDS[1:])
        twin = copy.deepcopy(RECORDS)
        twin[0]["id"] = "amvo-src-github-com-openai-math"
        with self.assertRaisesRegex(RecordError, "share an id"):
            check_registry(objects, {}, twin)

    def test_objects_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            obj = source()
            self.assertTrue(write_object(Path(td), obj)[1])
            self.assertFalse(write_object(Path(td), obj)[1])               # identical: fine
            with self.assertRaisesRegex(RecordError, "never overwritten"):
                write_object(Path(td), dict(obj, title="changed"))


class LocateAndRegisterTests(unittest.TestCase):
    def test_locate_says_where_a_result_lives(self):
        objs = paper()
        for q in (URL, URL + "v2", "https://arxiv.org/pdf/2610.12345v2.pdf", "2610.12345v2", "amvo-clm-paper-thm-1",
                  "amvo-evd-paper-lem-2-r"):
            with self.subTest(query=q):
                found = locate(objs, q)
                self.assertEqual(found["sources"], ["amvo-src-paper"])
                self.assertEqual(found["revisions"], ["amvo-rev-paper-v2"])
                self.assertEqual(len(found["claims"]), 3)
        new = locate(objs, "https://arxiv.org/abs/2611.00001v1")
        self.assertEqual((new["sources"], new["suggested_source_id"], new["canonical_url"]),
                         ([], "amvo-src-arxiv-org-abs-2611-00001", "https://arxiv.org/abs/2611.00001"))

    def test_register_from_drafts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "cases", root / "cases")
            small_registry(root / "registry")
            shutil.copytree(ROOT / "evidence", root / "evidence")
            base = registry_report(*load_registry(root / "registry"), root)["counts"]   # before anything is added

            def run(*args):
                return main([args[0], "--cases", str(root / "cases"), "--root", str(root), *args[1:]])

            def draft(name, payload):
                path = root / name
                path.write_text(json.dumps(payload), "utf-8")
                return str(path)
            s = {k: v for k, v in source().items() if k not in ("object_schema", "id")}
            s["canonical_url"] = URL + "v2"                               # normalised on registration
            self.assertEqual(run("register", "--draft", draft("s.json", s)), 0)
            self.assertTrue((root / "registry" / "sources" / "amvo-src-arxiv-org-abs-2610-12345.json").exists())
            self.assertEqual(run("register", "--draft", draft("s2.json", dict(s, canonical_url=URL + "/"),
                                                              )), 0)       # same object again: unchanged
            twin = dict(s, id="amvo-src-another-name")
            self.assertEqual(run("register", "--draft", draft("s3.json", twin)), 2)
            self.assertFalse((root / "registry" / "sources" / "amvo-src-another-name.json").exists())
            r = {"kind": "revision", "source": "amvo-src-arxiv-org-abs-2610-12345", "version_label": "v2",
                 "pin": {"kind": "arxiv_version", "value": "2610.12345v2"}, "captured_at": "2026-10-13"}
            self.assertEqual(run("register", "--draft", draft("r.json", r)), 0)
            c = {"kind": "claim", "id": "amvo-clm-arxiv-2610-12345-thm-1", "revision": "amvo-rev-arxiv-org-abs-2610-12345-2610-12345v2",
                 "claim_type": "theorem", "statement": "Every widget is a gadget.", "scope": "as stated",
                 "location": "Theorem 1"}
            self.assertEqual(run("register", "--draft", draft("c.json", c)), 0)
            self.assertEqual(run("register", "--draft", draft("c2.json", dict(c, revision="amvo-rev-missing"))), 2)
            self.assertEqual(run("validate"), 0)
            self.assertEqual(run("record-event", "--type", "corrects", "--target", "amvo-clm-arxiv-2610-12345-thm-1",
                                 "--source-url", "https://arxiv.org/abs/2610.12345v3", "--rationale", "an erratum",
                                 "--recorded-by", "AMVO maintainers"), 0)   # events may name registry objects
            self.assertEqual(run("validate"), 0)
            self.assertEqual(run("locate", "--query", "https://arxiv.org/abs/2610.12345v2"), 0)
            out = root / "layered.json"
            self.assertEqual(run("registry-report", "--output", str(out)), 0)
            counts = json.loads(out.read_text("utf-8"))["counts"]
            self.assertEqual((counts["sources"], counts["claims"], counts["current_claims_not_checked"]),
                             (base["sources"] + 1, base["claims"] + 1, base["current_claims_not_checked"] + 1))


class RegistrySchemaConsistency(unittest.TestCase):
    """every object the schema rejects, the runtime rejects; the schema shares the case schema's parts"""
    RUNTIME_ONLY = {"canonical spelling", "public host", "calendar date", "blank text", "duplicate", "unresolved"}

    def cases(self):
        objs = paper()
        thm = objs["amvo-clm-paper-thm-1"]
        good_fmt = o("formal_target", "amvo-fmt-thm-1", claim=ref(thm), language="lean4", theorem_name="t",
                     exact_statement="s", code_pin={"kind": "git_commit", "value": "a" * 40}, toolchain="t",
                     axiom_policy="a", correspondence="c")
        good_rvw = o("review", "amvo-rvw-thm-1", claim=ref(thm), reviewer_class="independent_mathematician",
                     independence="i", conflicts="none", scope="s", audit_state="in_progress",
                     references=["https://example.org/r"])
        good_pub = o("publication", "amvo-pub-thm", title="t", claims=[ref(thm)], evidence=[], editorial_note="n",
                     license_review="pending")
        extra = {x["id"]: x for x in (good_fmt, good_rvw, good_pub)}
        base = dict(objs, **extra)

        def mut(oid, fn, rule=None):
            m = copy.deepcopy(base)
            fn(m[oid])
            return m, oid, rule
        put = lambda k, v: (lambda x: x.update({k: v}))
        drop = lambda k: (lambda x: x.pop(k))
        return {
            "valid": (base, None, "valid"),
            "schema version": mut("amvo-src-paper", put("object_schema", "0.1")),
            "kind": mut("amvo-src-paper", put("kind", "paper")),
            "id pattern": mut("amvo-src-paper", put("id", "amvo-src-UPPER")),
            "extra field": mut("amvo-clm-paper-thm-1", put("verdict", "pass")),
            "missing field": mut("amvo-clm-paper-thm-1", drop("scope")),
            "origin": mut("amvo-src-paper", put("origin_type", "blog")),
            "public false": mut("amvo-src-paper", put("public", False)),
            "authors empty": mut("amvo-src-paper", put("authors", [])),
            "http url": mut("amvo-src-paper", put("canonical_url", "http://arxiv.org/abs/2610.12345")),
            "versioned arxiv url": mut("amvo-src-paper", put("canonical_url", URL + "v2"), "canonical spelling"),
            "private url": mut("amvo-src-paper", put("canonical_url", "https://192.168.1.2/p"), "public host"),
            "date shape": mut("amvo-src-paper", put("retrieved_at", "13/10/2026")),
            "date calendar": mut("amvo-src-paper", put("retrieved_at", "2026-02-30"), "calendar date"),
            "rights mode": mut("amvo-src-paper", put("rights", {"mode": "public_domain", "note": "n"})),
            "pin shape": mut("amvo-rev-paper-v2", put("pin", {"kind": "arxiv_version", "value": "2610.12345"})),
            "ref shape": mut("amvo-rev-paper-v2", put("source", {"id": "amvo-src-paper"})),
            "ref kind": mut("amvo-clm-paper-thm-1", put("revision", ref(objs["amvo-src-paper"]))),
            "ref hash": mut("amvo-clm-paper-thm-1", put("revision", {"id": "amvo-rev-paper-v2", "sha256": "f" * 64}),
                            "unresolved"),
            "claim type": mut("amvo-clm-paper-thm-1", put("claim_type", "fact")),
            "blank statement": mut("amvo-clm-paper-thm-1", put("statement", "  "), "blank text"),
            "long statement": mut("amvo-clm-paper-thm-1", put("statement", "x" * 4001)),
            "duplicate statement": mut("amvo-clm-paper-thm-1", put("statement", "A widget has two ends."), "duplicate"),
            "check kind": mut("amvo-evd-paper-lem-2-r", put("check", {"id": "x", "kind": "lean_kernel"})),
            "check fraction": mut("amvo-evd-paper-lem-2-r", put("check", dict(RATIONAL, lhs=["one"]))),
            "code pin arxiv": mut("amvo-fmt-thm-1", put("code_pin", {"kind": "arxiv_version", "value": "2610.12345v2"})),
            "language": mut("amvo-fmt-thm-1", put("language", "agda")),
            "reviewer class": mut("amvo-rvw-thm-1", put("reviewer_class", "famous_person")),
            "independent without refs": mut("amvo-rvw-thm-1", put("references", [])),
            "audit state": mut("amvo-rvw-thm-1", put("audit_state", "proved")),
            "publication no claims": mut("amvo-pub-thm", put("claims", [])),
            "publication repeats": mut("amvo-pub-thm", put("claims", [ref(thm), ref(thm)])),
            "license review": mut("amvo-pub-thm", put("license_review", "assumed")),
        }

    def test_schema_rejection_implies_runtime_rejection(self):
        seen = set()
        for name, (objs, changed, rule) in self.cases().items():
            with self.subTest(case=name):
                s_rej = any(schema_errors(x, SCHEMA, root=SCHEMA) for x in objs.values())
                try:
                    for x in objs.values():
                        validate_object(x)
                    check_registry(objs)
                    r_rej = False
                except RecordError:
                    r_rej = True
                if s_rej:
                    self.assertTrue(r_rej, f"schema rejects but runtime accepts: {name}")
                if r_rej and not s_rej:
                    self.assertIn(rule, self.RUNTIME_ONLY, f"undocumented runtime-only rule: {name}")
                    seen.add(rule)
                if rule == "valid":
                    self.assertFalse(s_rej or r_rej, f"valid registry rejected: {name}")
        self.assertEqual(seen, self.RUNTIME_ONLY)

    def test_repository_objects_and_manifests_are_schema_valid(self):
        objects, manifests = load_registry(ROOT / "registry")
        self.assertTrue(objects and manifests)
        for x in objects.values():
            self.assertEqual(schema_errors(x, SCHEMA, root=SCHEMA), [], x["id"])
        for m in manifests.values():
            self.assertEqual(schema_errors(m, SCHEMA["$defs"]["manifest"], root=SCHEMA), [], m["case_id"])

    def test_shared_parts_match_the_case_schema_and_runtime(self):
        d = SCHEMA["$defs"]
        self.assertEqual(d["check"], CASE_SCHEMA["properties"]["checks"]["items"])
        self.assertEqual(d["fractions"], CASE_SCHEMA["$defs"]["fractions"])
        self.assertEqual(d["pin"], CASE_SCHEMA["properties"]["source"]["properties"]["pin"])
        self.assertEqual(d["rights"], CASE_SCHEMA["properties"]["rights"])
        for kind, (folder, prefix) in LAYERS.items():
            self.assertIn(f"^amvo-{prefix}-", d[kind]["properties"]["id"]["pattern"])
            from amvo.registry import COMMON, FIELDS
            req, opt = FIELDS[kind]
            self.assertEqual(set(d[kind]["required"]), req | COMMON, kind)
            self.assertEqual(set(d[kind]["properties"]), req | opt | COMMON, kind)
        from amvo import registry
        self.assertEqual(d["source"]["properties"]["origin_type"]["enum"], list(registry.ORIGIN_TYPES))
        self.assertEqual(d["claim"]["properties"]["claim_type"]["enum"], list(registry.CLAIM_TYPES))
        self.assertEqual(d["review"]["properties"]["reviewer_class"]["enum"], list(registry.REVIEWER_CLASSES))
        self.assertEqual(d["review"]["properties"]["audit_state"]["enum"], list(registry.AUDIT_STATES))
        self.assertEqual(d["publication"]["properties"]["license_review"]["enum"], list(registry.LICENSE_REVIEW))
        self.assertEqual(d["formal_target"]["properties"]["language"]["enum"], list(registry.FORMAL_LANGUAGES))
        from amvo.core import ENGINE_VERSION
        self.assertIn(ENGINE_VERSION, SCHEMA["title"])


if __name__ == "__main__":
    unittest.main()
