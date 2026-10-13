"""Phase 1 pilot: the openai/math intake parses, samples by number and registers claims only."""
import importlib.util
import json
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

<tbody><tr>
<td>

**001. A synthetic result.** Proves that every widget is a gadget. ([Lean](lean/docs/001.md))

</td>
</tr></tbody>
<tbody><tr>
<td>

&emsp;[Widgets are gadgets](preprints/Widgets-October-1-2026/paper.pdf)

An abstract that is not copied.

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
        self.assertEqual(results[1]["manuscripts"], [("Widgets are gadgets", "preprints/Widgets-October-1-2026/paper.pdf")])
        self.assertEqual((results[2]["lean"], results[2]["manuscripts"]), (None, []))
        with self.assertRaisesRegex(RecordError, "appears twice"):
            intake.parse(SNIPPET + "\n**001. A synthetic result.** Again.\n")

    def test_claim_quotes_the_summary_and_lists_manuscripts_without_their_text(self):
        objects, _ = load_registry(ROOT / "registry")
        claim = intake.claim_for(intake.parse(SNIPPET)[1], objects[intake.REVISION])
        self.assertEqual(claim["statement"], "A synthetic result. Proves that every widget is a gadget.")
        self.assertEqual(claim["location"], "CONTENTS.md result 001; Lean: lean/docs/001.md")
        self.assertIn("Widgets are gadgets (preprints/Widgets-October-1-2026/paper.pdf)", claim["scope"])
        self.assertNotIn("abstract", claim["scope"])
        self.assertIn("AMVO has checked nothing", claim["scope"])

    def test_a_copy_that_is_not_the_pinned_file_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "CONTENTS.md"
            fake.write_text(SNIPPET, "utf-8")
            self.assertEqual(intake.main(["--contents", str(fake), "--root", td]), 2)

    def test_the_registered_pilot_is_the_fixed_sample_and_unchecked(self):
        objects, manifests = load_registry(ROOT / "registry")
        pilot = {k: v for k, v in objects.items() if k.startswith("amvo-clm-openai-math-r")}
        self.assertEqual(sorted(int(k[-3:]) for k in pilot), list(intake.SAMPLE))
        self.assertEqual(len(intake.SAMPLE), 10)
        for c in pilot.values():
            self.assertEqual(c["revision"]["id"], intake.REVISION)
            self.assertIn(intake.CONTENTS_SHA256[:16], c["scope"])
        report = registry_report(objects, manifests, ROOT)
        for c in report["claims"]:
            if c["id"] in pilot:
                self.assertEqual(c["statuses"], ["NOT_CHECKED", "INDEPENDENT_REPLICATION_PENDING"])
                self.assertFalse(c["theorem_proved"])


if __name__ == "__main__":
    unittest.main()
