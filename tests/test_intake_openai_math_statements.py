"""Cloud pilot: statements inside the pilot manuscripts and the Lean formal targets, checked offline."""
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from amvo.core import RecordError
from amvo.lineage import lineage, load_events
from amvo.registry import load_registry, registry_report
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sandbox import small_registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "intake" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = _load("openai_math_statements")
fm = _load("openai_math_formal")

FAMILY1 = "preprints/Milnes-rationality-conjecture-for-abelian-varieties-October-7-2026/paper.pdf"
TEXT = ("A synthetic paper\nTheorem 1.1 (Widgets). Every widget\nis a gadget.\nProof. Omitted.\n1\n\f"
        "Proposition 2.1. Every gadget is\na widget. More text follows here.\n2\n\fCorollary 2.2. No gadget is\n"
        "3\n\fa sprocket.\nProof. Clear.\n")


def candidate(label, statement, page, end_page=None, decision="register", name=None):
    kind = label.split()[0].lower()
    heading = label + (f" ({name})." if name else ".")
    c = {"label": label, "name": name, "claim_type": kind, "heading": heading, "page": page,
         "end_page": end_page or page, "statement": statement, "boundary": "test", "decision": decision}
    if decision == "hold":
        c["hold_reason"] = "the manuscript presents this as a result of other work"
    return c


def sandbox(td):
    root = Path(td) / "root"
    for sub in ("cases", "events"):
        shutil.copytree(ROOT / sub, root / sub)
    small_registry(root / "registry")
    return root


class StatementCheckTests(unittest.TestCase):
    def test_normalise_collapses_whitespace_and_keeps_offsets(self):
        norm, where = st.normalise("  a\n\fb  c ")
        self.assertEqual(norm, "a b c")
        self.assertEqual(where, [2, 5, 5, 8, 8])                         # a space maps to the next character

    def test_a_quote_is_found_on_its_pages_and_a_paraphrase_is_not(self):
        thm = candidate("Theorem 1.1", "Every widget is a gadget.", 1, name="Widgets")
        self.assertIsNone(st.check_candidate(TEXT, thm))
        self.assertIsNone(st.check_candidate(TEXT, candidate("Corollary 2.2", "No gadget is 3 a sprocket.", 3, 4)))
        self.assertEqual(st.locate(TEXT, "Proposition 2.1.", "Every gadget is a widget."), [(2, 2)])
        for bad in ("Each widget is a gadget.", "Every widget is a gadget. Omitted.", "Every widget is a gadget!"):
            self.assertIn("not found", st.check_candidate(TEXT, dict(thm, statement=bad)))
        # a quote cut short is still a real quote: the check proves it is real, where it ends is reviewed
        self.assertIsNone(st.check_candidate(TEXT, dict(thm, statement="Every widget is a")))
        self.assertIn("not found", st.check_candidate(TEXT, dict(thm, heading="Theorem 1.2 (Widgets).")))
        self.assertIn("not on PDF page", st.check_candidate(TEXT, dict(thm, page=2, end_page=2)))
        self.assertIn("not whitespace-normalised", st.check_candidate(TEXT, dict(thm, statement="Every  widget")))
        self.assertIn("not whitespace-normalised", st.check_candidate(TEXT, dict(thm, statement="")))

    def _data(self, td, candidates, text=TEXT):
        texts = Path(td) / "texts"
        path = texts / (FAMILY1.removesuffix(".pdf") + ".txt")
        path.parent.mkdir(parents=True)
        path.write_bytes(text.encode("utf-8"))
        data = {"commit": st.COMMIT, "extractor": {"tool": "pdftotext", "version": "24.02.0", "args": ["-raw"]},
                "manuscripts": [{"family": 1, "ms": 9, "title": "A synthetic paper", "path": FAMILY1,
                                 "pdf_sha256": "0" * 64, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                 "lemma_headings_not_taken": 0, "candidates": candidates}]}
        data_path = Path(td) / "data.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return texts, data_path

    def test_registers_found_quotes_only_and_rerunning_writes_nothing(self):
        cands = [candidate("Theorem 1.1", "Every widget is a gadget.", 1, name="Widgets"),
                 candidate("Proposition 2.1", "Every gadget is a widget, always.", 2),          # not verbatim
                 candidate("Corollary 2.2", "No gadget is 3 a sprocket.", 3, 4, decision="hold"),
                 candidate("Proposition 2.1", "Every gadget is a widget.", 2)]
        with tempfile.TemporaryDirectory() as td:
            root = sandbox(td)
            texts, data = self._data(td, cands)
            before = set(load_registry(root / "registry")[0])
            argv = ["--texts", str(texts), "--data", str(data), "--root", str(root)]
            self.assertEqual(st.main(argv + ["--dry-run"]), 0)
            self.assertEqual(set(load_registry(root / "registry")[0]), before)
            self.assertEqual(st.main(argv), 0)
            objects, manifests = load_registry(root / "registry")
            new = sorted(set(objects) - before)
            self.assertEqual(new, ["amvo-clm-openai-math-r001-ms9-prop-2-1", "amvo-clm-openai-math-r001-ms9-thm-1-1"])
            thm = objects["amvo-clm-openai-math-r001-ms9-thm-1-1"]
            self.assertEqual(thm["statement"], "Every widget is a gadget.")
            self.assertEqual(thm["parent_claims"][0]["id"], "amvo-clm-openai-math-r001")
            self.assertEqual(thm["location"], f"{FAMILY1}, Theorem 1.1, PDF page 1")
            self.assertIn("Theorem 1.1 (Widgets) of the manuscript", thm["scope"])
            self.assertIn("AMVO has checked nothing about this claim.", thm["scope"])
            report = registry_report(objects, manifests, root)
            for c in report["claims"]:
                if c["id"] in new:
                    self.assertEqual(c["statuses"], ["NOT_CHECKED", "INDEPENDENT_REPLICATION_PENDING"])
            self.assertEqual(st.main(argv), 0)                                   # unchanged, not a duplicate
            self.assertEqual(set(load_registry(root / "registry")[0]) - before, set(new))

    def test_duplicates_long_statements_and_foreign_texts_are_refused(self):
        long_text = "Theorem 3.1. " + "x " * 2100 + "\nProof.\n"
        long = candidate("Theorem 3.1", " ".join(["x"] * 2100), 1)
        with tempfile.TemporaryDirectory() as td:
            root = sandbox(td)
            texts, data = self._data(td, [long], long_text)
            before = set(load_registry(root / "registry")[0])
            self.assertEqual(st.main(["--texts", str(texts), "--data", str(data), "--root", str(root)]), 0)
            self.assertEqual(set(load_registry(root / "registry")[0]), before)  # over 4000 characters: rejected
        with tempfile.TemporaryDirectory() as td:
            root = sandbox(td)
            twice = TEXT + "Theorem 9.9. Every widget is a gadget.\n"
            cands = [candidate("Theorem 1.1", "Every widget is a gadget.", 1, name="Widgets"),
                     candidate("Theorem 9.9", "Every widget is a gadget.", 4)]
            texts, data = self._data(td, cands, twice)
            self.assertEqual(st.main(["--texts", str(texts), "--data", str(data), "--root", str(root)]), 0)
            added = set(load_registry(root / "registry")[0]) - set(load_registry(ROOT / "registry")[0])
            self.assertEqual(added, {"amvo-clm-openai-math-r001-ms9-thm-1-1"})          # the first is kept
            (texts / (FAMILY1.removesuffix(".pdf") + ".txt")).write_text(TEXT + " ", "utf-8")
            self.assertEqual(st.main(["--texts", str(texts), "--data", str(data), "--root", str(root)]), 2)

    def test_a_cited_result_is_credited_to_the_cited_work(self):
        cited = dict(candidate("Proposition 2.1", "Every gadget is a widget.", 2), decision="cited",
                     cited_by="More text follows here.", references=[])
        with tempfile.TemporaryDirectory() as td:
            root = sandbox(td)
            bad = dict(cited, label="Corollary 2.2", heading="Corollary 2.2.", claim_type="corollary",
                       statement="No gadget is 3 a sprocket.", page=3, end_page=4, cited_by="This is [9].")
            texts, data = self._data(td, [cited, bad])
            self.assertEqual(st.main(["--texts", str(texts), "--data", str(data), "--root", str(root)]), 0)
            added = set(load_registry(root / "registry")[0]) - set(load_registry(ROOT / "registry")[0])
            self.assertEqual(added, {"amvo-clm-openai-math-r001-ms9-prop-2-1"})     # a quote not in the text: refused
            claim = load_registry(root / "registry")[0]["amvo-clm-openai-math-r001-ms9-prop-2-1"]
            self.assertTrue(claim["attribution"].startswith("Credited to the work the manuscript cites, not to OpenAI"))
            self.assertIn("“More text follows here.”", claim["attribution"])
            self.assertIn("presents this as a result of other work", claim["scope"])

    def test_registered_statements_are_exactly_the_recorded_candidates(self):
        objects, manifests = load_registry(ROOT / "registry")
        revision = objects[st.REVISION]
        children = {k for k, o in objects.items() if o["kind"] == "claim" and o.get("parent_claims")
                    and o["parent_claims"][0]["id"].startswith("amvo-clm-openai-math-r")}
        expected, first = set(), {}
        for path in sorted(st.DATA.parent.glob("openai_math_statements*.json")):            # pilot, then batches
            data = json.loads(path.read_text(encoding="utf-8"))
            found, cited, held, too_long, kept = 0, 0, 0, 0, 0
            for ms in data["manuscripts"]:
                family = objects[f"amvo-clm-openai-math-r{ms['family']:03d}"]
                for c in ms["candidates"]:
                    found += 1
                    self.assertEqual(c["statement"], st.normalise(c["statement"])[0])
                    if c["decision"] == "hold":
                        held += 1
                        self.assertNotIn(st.claim_id(ms, c), objects)
                    elif len(c["statement"]) > st.MAX_STATEMENT:
                        too_long += 1
                        self.assertNotIn(st.claim_id(ms, c), objects)
                    elif first.get(c["statement"], st.claim_id(ms, c)) != st.claim_id(ms, c):
                        self.assertNotIn(st.claim_id(ms, c), objects)                # a duplicate: the first is kept
                    else:
                        first[c["statement"]] = st.claim_id(ms, c)
                        claim = st.claim_for(ms, c, data["extractor"], revision, family)
                        self.assertEqual(objects[claim["id"]], claim)                # byte-for-byte reproducible
                        expected.add(claim["id"])
                        kept += 1
                        cited += c["decision"] == "cited"
            if path == st.DATA:                                                  # the pilot, as logged
                self.assertEqual((len(data["manuscripts"]), found, kept, cited, held, too_long),
                                 (18, 264, 263, 15, 0, 1))
        self.assertEqual(children, expected)
        report = registry_report(objects, manifests, ROOT,
                                 lineages=lineage(list(objects.values()), load_events(ROOT / "events")))
        for c in report["claims"]:
            if c["id"] in expected:
                self.assertEqual(c["statuses"], ["NOT_CHECKED", "INDEPENDENT_REPLICATION_PENDING"])
                self.assertFalse(c["theorem_proved"])
        self.assertEqual(report["counts"]["theorems_proved"], 0)


LEAN = "import Mathlib\n\nnamespace OAI\n\ntheorem widget_gadget\n    (n : ℕ) : n = n := by\n  sorry\n\nend OAI\n"
DOC = ("# Widgets\n\n- [A synthetic paper](../../preprints/x/paper.pdf)\n\n## Scope\n\nThe formalization proves "
       "that widgets are gadgets.\n\n## Comparator links\n\n| Result | Comparator statement |\n| --- | --- |\n"
       "| Widget bound | [Widgets.lean](../ComparatorChallenges/Widgets.lean) |\n")
CONFIG = {"challenge_module": "ComparatorChallenges.Widgets", "solution_module": "OAI.Widgets.Main",
          "theorem_names": ["OAI.widget_gadget"], "definition_names": [],
          "permitted_axioms": ["propext", "Quot.sound", "Classical.choice"], "enable_nanoda": False}


class FormalTargetTests(unittest.TestCase):
    def _files(self, td, lean=LEAN, doc=DOC):
        files = {"lean/docs/003.md": doc, "lean/ComparatorChallenges/Widgets.lean": lean,
                 "lean/ComparatorChallenges/Widgets.json": json.dumps(CONFIG),
                 "lean/lean-toolchain": "leanprover/lean4:v4.34.1\n",
                 "lean/lake-manifest.json": json.dumps({"packages": [{"name": "mathlib", "rev": "a" * 40}]})}
        base = Path(td) / "src"
        recorded = {}
        for path, body in files.items():
            (base / path).parent.mkdir(parents=True, exist_ok=True)
            (base / path).write_bytes(body.encode("utf-8"))
            recorded[path] = {"sha256": hashlib.sha256(body.encode()).hexdigest(), "git_blob": fm.git_blob(body.encode())}
        target = {"family": 3, "doc": "lean/docs/003.md", "papers": ["A synthetic paper"], "result": "Widget bound",
                  "lean_file": "lean/ComparatorChallenges/Widgets.lean",
                  "config": "lean/ComparatorChallenges/Widgets.json", "theorem_name": "OAI.widget_gadget",
                  "exact_statement": "theorem widget_gadget\n    (n : ℕ) : n = n",
                  "solution_module": "OAI.Widgets.Main", "permitted_axioms": CONFIG["permitted_axioms"],
                  "enable_nanoda": False, "doc_quotes": ["The formalization proves that widgets are gadgets."],
                  "comparators_on_page": 1}
        data = {"commit": fm.COMMIT, "toolchain": {"lean_toolchain": "leanprover/lean4:v4.34.1", "mathlib_rev": "a" * 40},
                "files": recorded, "targets": [target]}
        data_path = Path(td) / "formal.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return base, data_path, data

    def test_the_declaration_must_be_whole_and_the_page_must_say_what_is_quoted(self):
        with tempfile.TemporaryDirectory() as td:
            base, _, data = self._files(td)
            t, tc = data["targets"][0], data["toolchain"]

            def read(path):
                return (base / path).read_bytes()
            fm.check_target(t, read, tc)
            with self.assertRaisesRegex(RecordError, "not the whole statement"):
                fm.check_target(dict(t, exact_statement="theorem widget_gadget\n    (n : ℕ)"), read, tc)
            with self.assertRaisesRegex(RecordError, "does not occur exactly once"):
                fm.check_target(dict(t, exact_statement="theorem widget_gadget (n : ℕ) : n = n"), read, tc)
            with self.assertRaisesRegex(RecordError, "declares"):
                fm.check_target(dict(t, theorem_name="OAI.other"), read, tc)
            with self.assertRaisesRegex(RecordError, "quoted text"):
                fm.check_target(dict(t, doc_quotes=["The formalization proves everything."]), read, tc)
            with self.assertRaisesRegex(RecordError, "does not list"):
                fm.check_target(dict(t, result="Another bound"), read, tc)
            with self.assertRaisesRegex(RecordError, "permitted_axioms"):
                fm.check_target(dict(t, permitted_axioms=["propext"]), read, tc)

    def test_a_declaration_ends_at_its_own_assignment_not_at_a_binding_inside_it(self):
        lean = ("-- a comment with := in it\ntheorem pair.{u} (α : Type u) :\n    let n := 2 -- := here too\n"
                "    letI := (⟨fun _ => 0⟩ : Inhabited α); /- also := -/ n = n ∧ (⟨1, 2⟩ : ℕ × ℕ) = { fst := 1, snd := 2 } := by\n"
                "  sorry\n")
        start = lean.index("theorem")
        end = fm.declaration_end(lean, start)
        self.assertTrue(lean[end:].startswith(":= by\n  sorry"))
        whole = lean[start:end].rstrip()
        cfg = dict(CONFIG, theorem_names=["OAI.pair"])
        files = {"lean/ComparatorChallenges/C.lean": lean.encode(), "lean/ComparatorChallenges/C.json": json.dumps(cfg).encode(),
                 "lean/docs/003.md": DOC.replace("Widgets.lean", "C.lean").encode(), "lean/lean-toolchain": b"t\n",
                 "lean/lake-manifest.json": json.dumps({"packages": [{"name": "mathlib", "rev": "m"}]}).encode()}
        t = {"lean_file": "lean/ComparatorChallenges/C.lean", "config": "lean/ComparatorChallenges/C.json",
             "theorem_name": "OAI.pair", "exact_statement": whole, "solution_module": "OAI.Widgets.Main",
             "permitted_axioms": CONFIG["permitted_axioms"], "enable_nanoda": False, "doc": "lean/docs/003.md",
             "result": "Widget bound", "papers": ["A synthetic paper"], "doc_quotes": []}
        tc = {"lean_toolchain": "t", "mathlib_rev": "m"}
        fm.check_target(t, files.__getitem__, tc)                                     # universe suffix, bindings, comments
        with self.assertRaisesRegex(RecordError, "stops at a := inside the statement"):
            fm.check_target(dict(t, exact_statement=whole[:whole.index(" := 2")]), files.__getitem__, tc)
        with self.assertRaisesRegex(RecordError, "enable_nanoda"):
            fm.check_target(dict(t, enable_nanoda=None), files.__getitem__, tc)
        files["lean/ComparatorChallenges/C.json"] = json.dumps({k: v for k, v in cfg.items() if k != "enable_nanoda"}).encode()
        fm.check_target(dict(t, enable_nanoda=None), files.__getitem__, tc)        # a configuration may leave it unset

    def test_registers_a_target_once_and_refuses_a_changed_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = sandbox(td)
            base, data_path, _ = self._files(td)
            argv = ["--lean", str(base), "--data", str(data_path), "--root", str(root)]
            self.assertEqual(fm.main(argv), 0)
            objects, manifests = load_registry(root / "registry")
            target = objects["amvo-fmt-openai-math-r003-widget-gadget"]
            self.assertEqual(target["code_pin"], {"kind": "git_commit", "value": fm.COMMIT})
            self.assertTrue(target["axiom_policy"].startswith("Declared, not checked"))
            self.assertIn("Quoted, not judged", target["correspondence"])
            self.assertEqual(fm.main(argv), 0)                                        # nothing new
            (base / "lean/ComparatorChallenges/Widgets.lean").write_text(LEAN.replace("n = n", "n = 0"), "utf-8")
            self.assertEqual(fm.main(argv), 2)

    def test_registered_targets_are_exactly_the_recorded_ones_and_nothing_is_proved(self):
        objects, manifests = load_registry(ROOT / "registry")
        targets = {k: o for k, o in objects.items() if o["kind"] == "formal_target"}
        built, docs = [], set()
        for path in sorted((ROOT / "tools" / "intake").glob("openai_math_formal_targets*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["commit"], fm.COMMIT)
            self.assertFalse(docs & {t["doc"] for t in data["targets"]})              # each Lean page in one file
            docs |= {t["doc"] for t in data["targets"]}
            built += [fm.target_for(t, data, objects[f"amvo-clm-openai-math-r{t['family']:03d}"]) for t in data["targets"]]
            if path == fm.DATA:
                pilot = {o["claim"]["id"] for o in built}
                self.assertEqual(len(built), 15)
                self.assertEqual(pilot, {f"amvo-clm-openai-math-r{n:03d}" for n in (3, 107, 160, 213, 266, 372)})
        self.assertEqual({o["id"]: o for o in built}, targets)
        self.assertEqual((len(targets), len(docs)), (536, 241))
        families = {o["claim"]["id"] for o in built}
        report = registry_report(objects, manifests, ROOT,
                                 lineages=lineage(list(objects.values()), load_events(ROOT / "events")))
        for c in report["claims"]:
            if c["id"] in families:
                self.assertIn("SEMANTIC_ALIGNMENT_PENDING", c["statuses"])
                self.assertIn("NOT_CHECKED", c["statuses"])
                self.assertEqual(c["formal_kernel"], "not_run")
        self.assertEqual((report["counts"]["formal_targets"], report["counts"]["formal_kernel_runs"],
                          report["counts"]["theorems_proved"]), (536, 0, 0))


if __name__ == "__main__":
    unittest.main()
