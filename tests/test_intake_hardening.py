import copy
import json
import unittest
from pathlib import Path

from amvo.core import RecordError, validate_record

SAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "cases" / "amvo-synthetic-fraction.json")
    .read_text(encoding="utf-8")
)


class MalformedRecordTests(unittest.TestCase):
    def test_unexpected_field_blocked(self):
        record = copy.deepcopy(SAMPLE)
        record["private_debug_notes"] = "not public"
        with self.assertRaises(RecordError):
            validate_record(record)

    def test_unhashable_case_type_clean_error(self):
        record = copy.deepcopy(SAMPLE)
        record["type"] = ["synthetic_fixture"]
        with self.assertRaises(RecordError):
            validate_record(record)

    def test_unhashable_check_kind_clean_error(self):
        record = copy.deepcopy(SAMPLE)
        record["checks"][0]["kind"] = ["rational_sum"]
        with self.assertRaises(RecordError):
            validate_record(record)

    def test_unknown_source_field_blocked(self):
        record = copy.deepcopy(SAMPLE)
        record["source"]["internal_notes"] = "never publish"
        with self.assertRaises(RecordError):
            validate_record(record)

    def test_unknown_check_field_blocked(self):
        record = copy.deepcopy(SAMPLE)
        record["checks"][0]["private_context"] = "never publish"
        with self.assertRaises(RecordError):
            validate_record(record)


if __name__ == "__main__":
    unittest.main()
