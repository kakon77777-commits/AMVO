import json
import tempfile
import unittest
from pathlib import Path

from amvo.cli import main


class CommandTests(unittest.TestCase):
    def test_standard_commands(self):
        self.assertEqual(main(["validate"]), 0)
        self.assertEqual(main(["audit-public"]), 0)

    def test_reproducible_report(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "one.json", Path(td) / "two.json"
            self.assertEqual(main(["verify", "--output", str(a)]), 0)
            self.assertEqual(main(["verify", "--output", str(b)]), 0)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            obj = json.loads(a.read_text("utf-8"))
            self.assertTrue(all(r["theorem_proved"] is False for r in obj["cases"]))

    def test_site_build_is_complete_and_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "site-a", Path(td) / "site-b"
            self.assertEqual(main(["build-site", "--output", str(a)]), 0)
            self.assertEqual(main(["build-site", "--output", str(b)]), 0)
            for path in ("index.html", "styles.css", "app.js", "data/index.json"):
                self.assertTrue((a / path).is_file())
                self.assertEqual((a / path).read_bytes(), (b / path).read_bytes())
            content = json.loads((a / "data/index.json").read_text("utf-8"))
            self.assertGreaterEqual(len(content["records"]), 2)


if __name__ == "__main__":
    unittest.main()
