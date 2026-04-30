import unittest

from pydantic import ValidationError

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from models.bess_backtest_params import BessBacktestParams
from models.financial_params import (
    BatterySpecs,
    FinancialAssumptions,
    InvestmentParams,
)


class BessBacktestParamsTests(unittest.TestCase):
    def test_derives_energy_mwh_from_power_and_duration(self):
        params = BessBacktestParams(
            market="NEM",
            region="NSW1",
            year=2025,
            power_mw=50,
            duration_hours=2,
        )

        self.assertEqual(params.energy_mwh, 100)
        self.assertEqual(params.duration_hours, 2)
        self.assertEqual(params.initial_soc_mwh, 50)

    def test_derives_duration_hours_from_power_and_energy(self):
        params = BessBacktestParams(
            market="NEM",
            region="VIC1",
            year=2025,
            power_mw=25,
            energy_mwh=50,
        )

        self.assertEqual(params.duration_hours, 2)
        self.assertEqual(params.energy_mwh, 50)

    def test_rejects_inconsistent_energy_and_duration(self):
        with self.assertRaises(ValidationError):
            BessBacktestParams(
                market="NEM",
                region="QLD1",
                year=2025,
                power_mw=50,
                energy_mwh=120,
                duration_hours=2,
            )

    def test_from_investment_params_maps_existing_investment_contract(self):
        investment_params = InvestmentParams(
            region="SA1",
            backtest_years=[2024, 2025],
            battery=BatterySpecs(
                power_mw=100,
                duration_hours=4,
                round_trip_efficiency=0.9,
            ),
            financial=FinancialAssumptions(
                variable_om_per_mwh=3.5,
            ),
        )

        params = BessBacktestParams.from_investment_params(investment_params)

        self.assertEqual(params.market, "NEM")
        self.assertEqual(params.region, "SA1")
        self.assertEqual(params.year, 2024)
        self.assertEqual(params.power_mw, 100)
        self.assertEqual(params.energy_mwh, 400)
        self.assertEqual(params.duration_hours, 4)
        self.assertEqual(params.round_trip_efficiency, 0.9)
        self.assertEqual(params.variable_om_per_mwh, 3.5)
        self.assertEqual(params.initial_soc_pct, 50)
        self.assertEqual(params.to_storage_config()["capacity_mwh"], 400)

    def test_from_investment_params_uses_explicit_year_override(self):
        investment_params = InvestmentParams(
            region="WEM",
            backtest_years=[2024, 2025],
        )

        params = BessBacktestParams.from_investment_params(investment_params, year=2025)

        self.assertEqual(params.market, "WEM")
        self.assertEqual(params.year, 2025)


if __name__ == "__main__":
    unittest.main()
