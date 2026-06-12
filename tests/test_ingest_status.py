import unittest
from datetime import date

from lib.ingest_status import (
    DEFAULT_STATUS_ALL_TABLE,
    DEFAULT_STATUS_LATEST_TABLE,
    IngestStatusStore,
    pcom_table_identifier,
    sql_identifier,
    _parse_session_date,
    _validate_job_field,
    _validate_status,
)


class TestIngestStatusValidation(unittest.TestCase):
    def test_sql_identifier_accepts_valid_names(self):
        self.assertEqual(sql_identifier("pcom_status_all"), "pcom_status_all")

    def test_sql_identifier_rejects_invalid_names(self):
        with self.assertRaises(ValueError):
            sql_identifier("bad-name")

    def test_pcom_table_identifier_requires_prefix(self):
        self.assertEqual(
            pcom_table_identifier(DEFAULT_STATUS_ALL_TABLE),
            DEFAULT_STATUS_ALL_TABLE,
        )
        with self.assertRaises(ValueError):
            pcom_table_identifier("dbento_status_all")

    def test_validate_status_normalizes_case(self):
        self.assertEqual(_validate_status("Running"), "running")

    def test_validate_status_rejects_unknown(self):
        with self.assertRaises(ValueError):
            _validate_status("exploded")

    def test_validate_job_field_rejects_empty(self):
        with self.assertRaises(ValueError):
            _validate_job_field("project", "  ")

    def test_parse_session_date_from_string(self):
        self.assertEqual(_parse_session_date("2026-06-02"), date(2026, 6, 2))

    def test_parse_session_date_from_date(self):
        value = date(2026, 6, 2)
        self.assertEqual(_parse_session_date(value), value)

    def test_defaults_use_pcom_tables(self):
        self.assertEqual(DEFAULT_STATUS_ALL_TABLE, "pcom_status_all")
        self.assertEqual(DEFAULT_STATUS_LATEST_TABLE, "pcom_status_latest")


class TestIngestStatusStoreInit(unittest.TestCase):
    def test_rejects_non_pcom_table_names(self):
        class FakeDb:
            conf = {}

        with self.assertRaises(ValueError):
            IngestStatusStore(FakeDb(), status_all_table="wiki_status_all")


if __name__ == "__main__":
    unittest.main()
