import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from models.financial_params import (
    BatterySpecs,
    FcasRevenueMode,
    FinancialAssumptions,
    InvestmentParams,
)


class InvestmentEndpointSmokeTests(unittest.TestCase):
    def test_investment_endpoint_returns_expected_sections(self):
        import server

        params = InvestmentParams(
            region="SA1",
            backtest_years=[2024],
            battery=BatterySpecs(
                power_mw=100.0,
                duration_hours=2.0,
            ),
            financial=FinancialAssumptions(
                project_life_years=15,
            ),
            fcas_revenue_mode=FcasRevenueMode.AUTO,
            revenue_capture_rate=0.65,
        )
        params.monte_carlo.enabled = True
        params.monte_carlo.iterations = 100

        response = server.investment_analysis(params)

        self.assertIn("region", response)
        self.assertIn("base_metrics", response)
        self.assertIn("scenarios", response)
        self.assertIn("metrics", response)
        self.assertIn("cash_flows", response)
        self.assertIn("baseline_revenue", response)


if __name__ == "__main__":
    unittest.main()
