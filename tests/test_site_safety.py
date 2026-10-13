"""P0: the static observatory renders public data as text only and loads nothing foreign."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from amvo.cli import main
from amvo.core import RecordError, list_records

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

# DOM sinks that parse strings as HTML or code
SINKS = re.compile(r"\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\.write|\beval\s*\(|"
                   r"new\s+Function\s*\(|setTimeout\s*\(\s*['\"`]|setInterval\s*\(\s*['\"`]|"
                   r"\.srcdoc\b|javascript:")


class SiteSafetyTests(unittest.TestCase):
    def test_no_html_or_code_sinks_in_scripts(self):
        for js in sorted(WEB.glob("*.js")):
            with self.subTest(file=js.name):
                text = js.read_text("utf-8")
                code = "\n".join(line.split("//", 1)[0] for line in text.splitlines())
                self.assertIsNone(SINKS.search(code), f"unsafe DOM/code sink in {js.name}")

    def test_pages_carry_a_strict_csp_and_no_foreign_scripts(self):
        for page in sorted(WEB.glob("*.html")):
            with self.subTest(page=page.name):
                html = page.read_text("utf-8")
                m = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html)
                self.assertIsNotNone(m, "missing CSP")
                csp = m.group(1)
                self.assertIn("default-src 'none'", csp)
                self.assertIn("script-src 'self'", csp)
                self.assertNotIn("unsafe-inline", csp)
                self.assertNotIn("unsafe-eval", csp)
                self.assertNotRegex(html, r'<script[^>]+src="(?:https?:)?//')
                self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>")   # no inline script

    def test_hostile_strings_reach_the_site_only_as_data(self):
        """a title or statement full of markup is copied into data/index.json as a JSON string;
        the page renders it with textContent (test above), so it can never become markup"""
        hostile = '<img src=x onerror=alert(1)><script>alert(2)</script>'
        rec = json.loads((ROOT / "cases" / "amvo-synthetic-fraction.json").read_text("utf-8"))
        rec["title"] = "fixture " + hostile
        rec["claim"]["statement"] = hostile
        with tempfile.TemporaryDirectory() as td:
            cases = Path(td) / "cases"
            cases.mkdir()
            (cases / f"{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False), "utf-8")
            out = Path(td) / "site"
            self.assertEqual(main(["build-site", "--cases", str(cases), "--output", str(out)]), 0)
            data = json.loads((out / "data" / "index.json").read_text("utf-8"))
            self.assertEqual(data["records"][0]["claim"]["statement"], hostile)
            for name in ("index.html", "app.js", "styles.css"):
                self.assertEqual((out / name).read_bytes(), (WEB / name).read_bytes())

    def test_duplicate_record_ids_across_files_rejected(self):
        rec = json.loads((ROOT / "cases" / "amvo-synthetic-fraction.json").read_text("utf-8"))
        with tempfile.TemporaryDirectory() as td:
            cases = Path(td)
            (cases / f"{rec['id']}.json").write_text(json.dumps(rec), "utf-8")
            (cases / "amvo-other.json").write_text(json.dumps(rec), "utf-8")   # same id, other name
            with self.assertRaises(RecordError):
                list_records(cases)


if __name__ == "__main__":
    unittest.main()
