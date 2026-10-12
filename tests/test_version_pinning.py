import copy
import json
import unittest
from pathlib import Path

from amvo.core import RecordError, validate_record, verify_record


ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "cases" / "amvo-synthetic-fraction.json").read_text("utf-8"))


def candidate():
    rec = copy.deepcopy(BASE)
    rec["type"] = "claim"
    rec["source"]["url"] = "https://github.com/example/public-math"
    rec["source"]["pin"] = {"kind": "git_commit", "value": "a" * 40}
    return rec


class VersionPinTests(unittest.TestCase):
    def test_claim_requires_declared_pin(self):
        rec = candidate()
        del rec["source"]["pin"]
        with self.assertRaises(RecordError):
            validate_record(rec)

    def test_git_commit_pin_is_declaration_not_remote_replay(self):
        rec = candidate()
        self.assertIs(validate_record(rec), rec)
        result = verify_record(rec, ROOT)
        self.assertEqual(result["source_pin"]["value"], "a" * 40)
        self.assertFalse(result["source_pin_verified"])
        self.assertFalse(result["theorem_proved"])

    def test_arxiv_version_pin(self):
        rec = candidate()
        rec["source"]["pin"] = {"kind": "arxiv_version", "value": "2610.12345v2"}
        validate_record(rec)

    def test_sha256_pin(self):
        rec = candidate()
        rec["source"]["pin"] = {"kind": "sha256", "value": "b" * 64}
        validate_record(rec)

    def test_invalid_pin_rejected(self):
        for item in [
            {"kind": "git_commit", "value": "main"},
            {"kind": "arxiv_version", "value": "2610.12345"},
            {"kind": "sha256", "value": "z" * 64},
            {"kind": "sha256", "value": "a" * 64, "internal": "secret"},
        ]:
            with self.subTest(pin=item):
                rec = candidate()
                rec["source"]["pin"] = item
                with self.assertRaises(RecordError):
                    validate_record(rec)

    def test_public_intake_without_pin_allowed(self):
        rec = candidate()
        rec["type"] = "public_source_intake"
        rec["checks"] = []
        del rec["source"]["pin"]
        validate_record(rec)

    def test_malformed_url_is_clean_error(self):
        for url in [
            "https://[:::bad", "https://localhost/private",
            "https://127.0.0.1/secret", "https://example.org/\\nsecret",
            "https://example.org/\\t", "https://192.168.1.2/private",
        ]:
            with self.subTest(url=url):
                rec = candidate()
                rec["source"]["url"] = url
                with self.assertRaises(RecordError):
                    validate_record(rec)

    def test_empty_authors_blocked(self):
        rec = candidate()
        rec["source"]["authors"] = []
        with self.assertRaises(RecordError):
            validate_record(rec)

    def test_dot_segment_evidence_blocked(self):
        rec = candidate()
        rec["checks"] = [{"id": "integrity", "kind": "file_sha256",
                          "path": "evidence/./public.json", "sha256": "a" * 64}]
        with self.assertRaises(RecordError):
            validate_record(rec)


if __name__ == "__main__":
    unittest.main()
