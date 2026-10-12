import copy
import json
import tempfile
import unittest
from pathlib import Path

from amvo.core import (
    RecordError, audit_public, canonical_bytes, check_one, list_records,
    sha256, validate_record, verify_record,
)


ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = json.loads(
            (ROOT / "cases" / "amvo-synthetic-fraction.json").read_text(encoding="utf-8")
        )

    def test_canonical_digest_is_order_invariant(self):
        self.assertEqual(canonical_bytes({"a": 2, "z": 1}),
                         canonical_bytes({"z": 1, "a": 2}))

    def test_source_intake_and_fixture_load(self):
        records = list_records(ROOT / "cases")
        self.assertGreaterEqual(len(records), 2)
        self.assertEqual(len({r["id"] for r in records}), len(records))

    def test_exact_fixture_passes_without_claiming_theorem(self):
        result = verify_record(self.sample, ROOT)
        self.assertEqual(result["outcome"], "bounded_checks_pass")
        self.assertFalse(result["theorem_proved"])
        self.assertEqual(result["formal_kernel"], "not_run")

    def test_false_identity_fails(self):
        invalid = copy.deepcopy(self.sample)
        invalid["checks"][0]["rhs"] = ["1/3"]
        result = verify_record(invalid, ROOT)
        self.assertEqual(result["outcome"], "checks_not_passed")
        self.assertEqual(result["checks"][0]["result"], "fail")

    def test_zero_denominator_rejected(self):
        bad = copy.deepcopy(self.sample)
        bad["checks"][0]["rhs"] = ["1/0"]
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_duplicate_check_ids_rejected(self):
        bad = copy.deepcopy(self.sample)
        bad["checks"].append(copy.deepcopy(bad["checks"][0]))
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_private_source_rejected(self):
        bad = copy.deepcopy(self.sample)
        bad["source"]["public"] = False
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_credentials_in_url_rejected(self):
        bad = copy.deepcopy(self.sample)
        bad["source"]["url"] = "https://someone:secret@example.org/private"
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_query_token_in_url_rejected(self):
        bad = copy.deepcopy(self.sample)
        bad["source"]["url"] = "https://example.org/?token=abc"
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_public_source_intake_cannot_be_checked(self):
        bad = copy.deepcopy(self.sample)
        bad["type"] = "public_source_intake"
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_evidence_escape_blocked(self):
        bad = copy.deepcopy(self.sample)
        bad["checks"] = [{"id": "escape", "kind": "file_sha256",
                          "path": "evidence/../secret", "sha256": "0" * 64}]
        with self.assertRaises(RecordError):
            validate_record(bad)

    def test_symlink_escape_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "evidence").mkdir()
            (root / "secret").write_text("hidden")
            (root / "evidence" / "link").symlink_to(root / "secret")
            check = {"id": "hash", "kind": "file_sha256",
                     "path": "evidence/link", "sha256": sha256(b"hidden")}
            bad = copy.deepcopy(self.sample)
            bad["checks"] = [check]
            outcome = verify_record(bad, root)
            self.assertEqual(outcome["outcome"], "checks_not_passed")

    def test_integrity_hash_has_limited_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "evidence").mkdir()
            (root / "evidence" / "ok.txt").write_bytes(b"artifact")
            bad = copy.deepcopy(self.sample)
            bad["checks"] = [{"id": "hash", "kind": "file_sha256",
                              "path": "evidence/ok.txt", "sha256": sha256(b"artifact")}]
            result = verify_record(bad, root)
            self.assertEqual(result["outcome"], "bounded_checks_pass")
            self.assertFalse(result["theorem_proved"])
            self.assertIn("integrity only", result["checks"][0]["scope"])

    def test_polynomial_coefficients(self):
        good = {"id": "poly", "kind": "polynomial_coefficients",
                "lhs_coefficients": ["1/2", "2", "0"],
                "rhs_coefficients": ["1/2", "2"]}
        self.assertEqual(check_one(good, ROOT)["result"], "pass")

    def test_public_audit_no_unreviewed_leaks(self):
        self.assertEqual(audit_public(list_records(ROOT / "cases")), [])

    def test_secret_material_flagged_without_leaking_value(self):
        bad = copy.deepcopy(self.sample)
        bad["claim"]["statement"] = "api_key = abcdefghijklmnopqrst"
        findings = audit_public([bad])
        self.assertEqual(len(findings), 1)
        self.assertNotIn("abcdefghijklmnopqrst", findings[0])


if __name__ == "__main__":
    unittest.main()
