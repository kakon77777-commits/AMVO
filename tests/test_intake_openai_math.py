"""Phase 1 pilot: the openai/math intake parses, samples by number and registers claims only."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

from amvo.core import RecordError
from amvo.registry import load_registry, registry_report

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("openai_math", ROOT / "tools" / "intake" / "openai_math.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)

SNIPPET = """# Mathematics manuscript collection

**2 manuscripts covering 2 result families.**

<tbody><tr>
<td>

**001. A synthetic result.** Proves that every widget is a gadget. ([Lean](lean/docs/001.md))

</td>
</tr></tbody>
<tbody><tr>
<td>

&emsp;[Widgets are gadgets](preprints/Widgets-October-1-2026/paper.pdf)

An abstract that is not copied.

&emsp;[Gadgets in CAT(0) spaces](preprints/Gadgets-in-CAT(0)-spaces-October-2-2026/paper.pdf) — secondary writeup

</td>
</tr></tbody>
<tbody><tr>
<td>

**002. Another result.** Proves something else.

</td>
</tr></tbody>
"""


class IntakeTests(unittest.TestCase):
    def test_parse(self):
        results = intake.parse(SNIPPET)
        self.assertEqual(sorted(results), [1, 2])
        self.assertEqual(results[1]["title"], "A synthetic result.")
        self.assertEqual(results[1]["summary"], "Proves that every widget is a gadget.")   # Lean marker removed
        self.assertEqual(results[1]["lean"], "lean/docs/001.md")
        self.assertEqual(results[1]["manuscripts"], [
            ("Widgets are gadgets", "preprints/Widgets-October-1-2026/paper.pdf", ""),
            ("Gadgets in CAT(0) spaces", "preprints/Gadgets-in-CAT(0)-spaces-October-2-2026/paper.pdf",
             "— secondary writeup")])                     # an annotation and a path with parentheses
        self.assertEqual((results[2]["lean"], results[2]["manuscripts"]), (None, []))
        with self.assertRaisesRegex(RecordError, "appears twice"):
            intake.parse(SNIPPET + "\n**001. A synthetic result.** Again.\n")

    def test_parse_refuses_rather_than_skips(self):
        """the pilot's first parser skipped a manuscript line silently; now nothing is skipped"""
        with self.assertRaisesRegex(RecordError, "manuscript line that does not parse"):
            intake.parse(SNIPPET + "\n&emsp;[Broken link](preprints/no-extension)\n")
        with self.assertRaisesRegex(RecordError, "result line that does not parse"):
            intake.parse(SNIPPET + "\n**003 Missing the dot.** Text.\n")
        with self.assertRaisesRegex(RecordError, "states 3 manuscripts"):
            intake.parse(SNIPPET.replace("**2 manuscripts", "**3 manuscripts"))
        with self.assertRaisesRegex(RecordError, "no .* header"):
            intake.parse(SNIPPET.replace("**2 manuscripts covering 2 result families.**", ""))

    def test_claim_quotes_the_summary_and_lists_manuscripts_without_their_text(self):
        objects, _ = load_registry(ROOT / "registry")
        claim = intake.claim_for(intake.parse(SNIPPET)[1], objects[intake.REVISION])
        self.assertEqual(claim["statement"], "A synthetic result. Proves that every widget is a gadget.")
        self.assertEqual(claim["location"], "CONTENTS.md result 001; Lean: lean/docs/001.md")
        self.assertIn("Widgets are gadgets (preprints/Widgets-October-1-2026/paper.pdf)", claim["scope"])
        self.assertIn("(preprints/Gadgets-in-CAT(0)-spaces-October-2-2026/paper.pdf) — secondary writeup",
                      claim["scope"])
        self.assertNotIn("abstract", claim["scope"])
        self.assertIn("AMVO has checked nothing", claim["scope"])

    def test_a_copy_that_is_not_the_pinned_file_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "CONTENTS.md"
            fake.write_text(SNIPPET, "utf-8")
            self.assertEqual(intake.main(["--contents", str(fake), "--root", td]), 2)

    def test_registered_openai_math_claims_include_the_pilot_and_are_unchecked(self):
        """the pilot sample is registered; later batches add families, and every one stays unchecked.
        Family claims are amvo-clm-openai-math-rNNN; the statements inside the manuscripts are their children
        (tests/test_intake_openai_math_statements.py), and a family whose Lean page names formal targets
        also reads SEMANTIC_ALIGNMENT_PENDING - still not checked."""
        objects, manifests = load_registry(ROOT / "registry")
        pilot = {k: v for k, v in objects.items() if re.fullmatch(r"amvo-clm-openai-math-r[0-9]{3}", k)}
        self.assertTrue(set(intake.SAMPLE) <= {int(k[-3:]) for k in pilot})
        self.assertEqual(len(intake.SAMPLE), 10)
        self.assertLessEqual(len(pilot), 372)
        for c in pilot.values():
            self.assertEqual(c["revision"]["id"], intake.REVISION)
            self.assertIn(intake.CONTENTS_SHA256[:16], c["scope"])
        from amvo.lineage import lineage, load_events
        events = load_events(ROOT / "events")
        fixes = [e for e in events if e["type"] == "corrects" and e["target"] in pilot]
        self.assertEqual([e["target"] for e in fixes], ["amvo-clm-openai-math-r107"])   # the one recorded erratum
        report = registry_report(objects, manifests, ROOT, lineages=lineage(list(objects.values()), events))
        for c in report["claims"]:
            if c["id"] in pilot:
                aligned = ["SEMANTIC_ALIGNMENT_PENDING"] if c["formal_targets"] else []
                self.assertEqual(c["statuses"], ["NOT_CHECKED"] + aligned + ["INDEPENDENT_REPLICATION_PENDING"])
                self.assertFalse(c["theorem_proved"])


if __name__ == "__main__":
    unittest.main()
