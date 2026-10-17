"""P0: the static observatory renders public data as text only and loads nothing foreign."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from amvo.cli import SITE_FILES, main
from amvo.core import RecordError, list_records
from amvo.registry import load_registry

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
            self.assertEqual(main(["build-site", "--cases", str(cases), "--root", td, "--output", str(out)]), 0)
            data = json.loads((out / "data" / "index.json").read_text("utf-8"))
            self.assertEqual(data["records"][0]["claim"]["statement"], hostile)
            for name in SITE_FILES:
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


class FrontEndReportTests(unittest.TestCase):
    """P1-D: the page renders the layered report and never presents an unchecked item as checked"""

    def js_keys(self, name):
        text = (WEB / "app.js").read_text("utf-8")
        body = re.search(r"const " + name + r" = \{(.*?)\n\};", text, re.S).group(1)
        return set(re.findall(r"^\s*([A-Za-z_]+):", body, re.M))

    def test_every_report_status_has_a_label_and_none_says_verified(self):
        from amvo.registry import STATUSES
        self.assertEqual(self.js_keys("STATUS"), set(STATUSES))
        js = (WEB / "app.js").read_text("utf-8")
        code = "\n".join(line.split("//", 1)[0] if not line.lstrip().startswith("//") else ""
                         for line in js.splitlines())             # comments may name what is never shown
        for word in ("VERIFIED", "已驗證", "已證明", "已獲證"):          # no label the script can render
            self.assertNotIn(word, code)
        self.assertNotIn("VERIFIED", (WEB / "index.html").read_text("utf-8"))

    def test_every_pin_state_has_a_label(self):
        from amvo.provenance import STATUSES as CAPTURE_STATUSES
        states = set(CAPTURE_STATUSES) | {"declared_only", "no_pin", "fixture_only", "capture_invalid"}
        self.assertEqual(self.js_keys("PIN_STATES"), states)

    def test_site_carries_the_layered_report(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "site"
            self.assertEqual(main(["build-site", "--output", str(out)]), 0)
            data = json.loads((out / "data" / "index.json").read_text("utf-8"))
            self.assertEqual(data["registry"]["report_schema"], "0.2")
            self.assertEqual(data["registry"]["counts"]["theorems_proved"], 0)
            self.assertTrue(all(c["theorem_proved"] is False for c in data["registry"]["claims"]))
            # the card calls a type the source's label only where the location names the heading it was quoted under
            js = (WEB / "app.js").read_text("utf-8")
            self.assertIn('"原稿標示："', js)
            self.assertIn('"（非原稿標示）"', js)
            objects, _ = load_registry(ROOT / "registry")
            grouped = [c for g in data["registry"]["claim_groups"].values()
                       for c in json.loads((out / "data" / g["file"]).read_text("utf-8"))["claims"]]
            for c in data["registry"]["claims"] + grouped:
                self.assertEqual(c["location"], objects[c["id"]].get("location"))
                named = any(part.startswith(c["claim_type"].capitalize() + " ")
                            for part in (c["location"] or "").split(", "))
                if re.fullmatch(r"amvo-clm-openai-math-r[0-9]{3}", c["id"]):
                    self.assertFalse(named, c["id"])                  # a family's type is AMVO's, not a heading
                elif c["id"].startswith("amvo-clm-openai-math-r"):
                    self.assertTrue(named, c["id"])                   # a statement's type is its heading's word

    def test_site_index_stays_small_and_statements_load_on_demand(self):
        """statements filed under a claim go to that claim's own file; every claim appears exactly once,
        the index stays small enough to load on a phone, and a rebuild leaves no stale file behind"""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "site"
            (out / "data" / "claims").mkdir(parents=True)
            (out / "data" / "claims" / "amvo-clm-stale.json").write_text("{}", "utf-8")
            self.assertEqual(main(["build-site", "--output", str(out)]), 0)
            index = json.loads((out / "data" / "index.json").read_text("utf-8"))["registry"]
            self.assertFalse((out / "data" / "claims" / "amvo-clm-stale.json").exists())
            self.assertLess((out / "data" / "index.json").stat().st_size, 2_000_000)
            seen = [c["id"] for c in index["claims"]]
            self.assertTrue(all(not c["parent_claims"] for c in index["claims"]))
            for parent, g in index["claim_groups"].items():
                self.assertRegex(g["file"], r"^claims/[a-z0-9-]+\.json$")
                body = json.loads((out / "data" / g["file"]).read_text("utf-8"))
                self.assertEqual(body["parent"], parent)
                self.assertEqual(len(body["claims"]), g["count"])
                self.assertIn(parent, seen[:len(index["claims"])])          # every group hangs off a listed claim
                seen += [c["id"] for c in body["claims"]]
            self.assertEqual(len(seen), len(set(seen)))
            self.assertEqual(len(seen), index["counts"]["claims"])
        self.assertIn("/^claims\\/[a-z0-9-]+\\.json$/.test(group.file)", (WEB / "app.js").read_text("utf-8"))

    def test_deployment_headers_and_worker_config(self):
        headers = (WEB / "_headers").read_text("utf-8")
        self.assertIn("frame-ancestors 'none'", headers)
        self.assertIn("no-transform", headers)          # keeps the edge from injecting analytics scripts
        self.assertIn("X-Content-Type-Options: nosniff", headers)
        csp = re.search(r"Content-Security-Policy: (.+)", headers).group(1)
        self.assertNotIn("unsafe-", csp)
        config = (ROOT / "wrangler.jsonc").read_text("utf-8")
        body = json.loads("\n".join(line for line in config.splitlines() if not line.lstrip().startswith("//")))
        self.assertEqual(body["assets"]["directory"], "./site")
        self.assertEqual(body["routes"], [{"pattern": "amvo.evemisslab.com", "custom_domain": True}])
        self.assertNotIn("main", body)                  # assets only: no Worker code runs
