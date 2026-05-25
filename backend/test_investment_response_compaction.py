import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


class InvestmentResponseCompactionTests(unittest.TestCase):
    def test_strip_scenario_cash_flows_keeps_metrics_and_names(self):
        payloads = [
            {
                "scenario_name": "Base",
                "metrics": {"npv": 1.0},
                "cash_flows": [{"year": 1, "net_cash_flow": 100.0}],
            },
            {
                "scenario_name": "Bear",
                "metrics": {"npv": -1.0},
                "cash_flows": [{"year": 1, "net_cash_flow": 50.0}],
            },
        ]

        stripped = server._strip_scenario_cash_flows_for_response(payloads)

        self.assertEqual(len(stripped), 2)
        self.assertEqual(stripped[0]["scenario_name"], "Base")
        self.assertEqual(stripped[1]["metrics"]["npv"], -1.0)
        self.assertNotIn("cash_flows", stripped[0])
        self.assertNotIn("cash_flows", stripped[1])
        self.assertIn("cash_flows", payloads[0])


if __name__ == "__main__":
    unittest.main()
