import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from backend.fcas_opportunity import summarize_nem_fcas_opportunity


class FcasOpportunityMemoryTests(unittest.TestCase):
    def test_tuple_rows_match_dict_rows(self):
        dict_rows = [
            {
                "settlement_date": "2025-01-01T00:00:00Z",
                "rrp_aud_mwh": 50.0,
                "raise1sec_rrp": 12.0,
                "lower1sec_rrp": 4.0,
            },
            {
                "settlement_date": "2025-01-01T00:05:00Z",
                "rrp_aud_mwh": -10.0,
                "raise1sec_rrp": 6.0,
                "lower1sec_rrp": 9.0,
            },
            {
                "settlement_date": "2025-01-01T00:10:00Z",
                "rrp_aud_mwh": 120.0,
                "raise1sec_rrp": 18.0,
                "lower1sec_rrp": 3.0,
            },
        ]
        columns = ["settlement_date", "rrp_aud_mwh", "raise1sec_rrp", "lower1sec_rrp"]
        tuple_rows = [tuple(row[column] for column in columns) for row in dict_rows]

        dict_result = summarize_nem_fcas_opportunity(dict_rows, capacity_mw=100.0, duration_hours=4.0)
        tuple_result = summarize_nem_fcas_opportunity(
            tuple_rows,
            capacity_mw=100.0,
            duration_hours=4.0,
            columns=columns,
        )

        self.assertEqual(dict_result, tuple_result)


if __name__ == "__main__":
    unittest.main()
