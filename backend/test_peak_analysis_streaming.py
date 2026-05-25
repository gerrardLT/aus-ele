import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


class PeakAnalysisStreamingTests(unittest.TestCase):
    def test_iter_peak_daily_results_matches_expected_day_boundaries(self):
        rows = [
            ("2025-01-01T00:00:00Z", 10.0),
            ("2025-01-01T00:05:00Z", 30.0),
            ("2025-01-01T00:10:00Z", 20.0),
            ("2025-01-01T00:15:00Z", 40.0),
            ("2025-01-02T00:00:00Z", 15.0),
            ("2025-01-02T00:05:00Z", 25.0),
            ("2025-01-02T00:10:00Z", 5.0),
            ("2025-01-02T00:15:00Z", 35.0),
        ]
        windows = {"1h": 2, "2h": 2, "4h": 5, "6h": 6}

        results = list(server._iter_peak_daily_results(rows, windows=windows, fee=5.0))

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["date"], "2025-01-01")
        self.assertEqual(results[0]["peak_1h"], 30.0)
        self.assertEqual(results[0]["trough_1h"], 20.0)
        self.assertEqual(results[0]["spread_2h"], 10.0)
        self.assertEqual(results[0]["net_spread_2h"], 0.0)
        self.assertIsNone(results[0]["peak_4h"])
        self.assertEqual(results[1]["date"], "2025-01-02")
        self.assertEqual(results[1]["peak_1h"], 20.0)
        self.assertEqual(results[1]["trough_1h"], 15.0)
        self.assertEqual(results[1]["spread_2h"], 5.0)
        self.assertEqual(results[1]["net_spread_2h"], -5.0)


if __name__ == "__main__":
    unittest.main()
