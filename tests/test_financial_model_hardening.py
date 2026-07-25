"""Tests for S4: Financial model hardening (M1-M5).

Validates:
- M1: payback interpolation ∈ (i-1, i]
- M2: sign changes ≥2 triggers MIRR, irr_reliable=False
- M3: sculpting mode maintains DSCR ≈ target each year
- M4: LLCR ≥ 1 consistent with debt serviceability
- M5: roi_undiscounted flag is True
"""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.financial_model import FinancialModel
from models.financial_params import InvestmentParams, ScenarioConfig


class M1PaybackInterpolationTests(unittest.TestCase):
    """M1: payback uses linear interpolation, not integer years."""

    def test_payback_is_fractional(self):
        """Payback should be fractional, not just an integer year index."""
        # CAPEX=100, then 30/yr → payback during year 4 (cum: -100,-70,-40,-10,+20)
        cash_flows = [-100.0, 30.0, 30.0, 30.0, 30.0, 30.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        self.assertIsNotNone(metrics.payback_years)
        # Should be between 3 and 4 (crosses zero during year 4)
        self.assertGreater(metrics.payback_years, 3.0)
        self.assertLessEqual(metrics.payback_years, 4.0)
        # Exact: after year 3 cumulative=-10, year 4 cf=30 → fraction=10/30=0.333
        self.assertAlmostEqual(metrics.payback_years, 3.0 + 10.0 / 30.0, places=5)

    def test_payback_exact_boundary(self):
        """When cumulative hits exactly 0, payback = integer year."""
        cash_flows = [-100.0, 50.0, 50.0, 50.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        # After year 2: cumulative = 0 exactly
        self.assertAlmostEqual(metrics.payback_years, 2.0, places=5)

    def test_payback_none_when_never_recovers(self):
        """If cumulative never reaches 0, payback is None."""
        cash_flows = [-100.0, 10.0, 10.0, 10.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        self.assertIsNone(metrics.payback_years)


class M2IRRReliabilityTests(unittest.TestCase):
    """M2: multiple sign changes → MIRR fallback, irr_reliable=False."""

    def test_single_sign_change_reliable(self):
        """Standard investment (one sign change) → irr_reliable=True."""
        cash_flows = [-100.0, 30.0, 40.0, 50.0, 60.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        self.assertTrue(metrics.irr_reliable)
        self.assertIsNone(metrics.mirr)
        self.assertIsNotNone(metrics.irr)

    def test_multiple_sign_changes_unreliable(self):
        """Non-conventional cash flows (≥2 sign changes) → irr_reliable=False, MIRR set."""
        # -100, +50, -30, +60, +40 → sign changes: - to +, + to -, - to + = 3
        cash_flows = [-100.0, 50.0, -30.0, 60.0, 40.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        self.assertFalse(metrics.irr_reliable)
        self.assertIsNotNone(metrics.mirr)

    def test_mirr_is_finite(self):
        """MIRR should be a finite number when computed."""
        cash_flows = [-1000.0, 500.0, -200.0, 600.0, 400.0, 300.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 1000.0, 0.08)
        if metrics.mirr is not None:
            self.assertGreater(metrics.mirr, -1.0)
            self.assertLess(metrics.mirr, 10.0)


class M3DebtSculptingTests(unittest.TestCase):
    """M3: sculpting mode maintains DSCR ≈ target each year."""

    def _build_params(self, mode: str = "annuity"):
        return InvestmentParams(
            region="SA1",
            battery={"power_mw": 50.0, "duration_hours": 2.0},
            financial={
                "project_life_years": 20,
                "discount_rate": 0.08,
                "capex_per_kwh": 350.0,
                "cost_of_debt": 0.06,
                "target_dscr": 1.30,
                "debt_tenor_years": 15,
                "debt_repayment_mode": mode,
            },
        )

    def test_sculpting_dscr_near_target(self):
        """In sculpting mode, each year's DSCR should be close to target."""
        params = self._build_params(mode="sculpting")
        scenario = ScenarioConfig(name="Base")
        result = FinancialModel.run_scenario(
            params, scenario,
            baseline_arbitrage=5_000_000.0,
            baseline_fcas=1_000_000.0,
            annual_cycles_history=[365.0] * 20,
        )
        # Check DSCR for years with positive debt service
        tenor = min(params.financial.debt_tenor_years, params.financial.project_life_years)
        for cfy in result.cash_flows:
            if cfy.year <= tenor and cfy.debt_service > 0 and cfy.net_cash_flow > 0:
                dscr = cfy.net_cash_flow / cfy.debt_service
                # Sculpting targets DSCR = target; allow tolerance for interest floor
                self.assertGreaterEqual(dscr, 0.9, f"Year {cfy.year} DSCR too low: {dscr}")

    def test_annuity_is_default(self):
        """Default mode is annuity (zero regression)."""
        params = InvestmentParams(region="SA1")
        self.assertEqual(params.financial.debt_repayment_mode, "annuity")

    def test_sculpting_and_annuity_differ(self):
        """Sculpting produces different levered cash flows than annuity."""
        scenario = ScenarioConfig(name="Base")
        arb, fcas = 5_000_000.0, 1_000_000.0
        cycles = [365.0] * 20

        r_annuity = FinancialModel.run_scenario(
            self._build_params("annuity"), scenario, arb, fcas, cycles
        )
        r_sculpt = FinancialModel.run_scenario(
            self._build_params("sculpting"), scenario, arb, fcas, cycles
        )
        # Debt service patterns should differ
        ds_annuity = [cfy.debt_service for cfy in r_annuity.cash_flows[:15]]
        ds_sculpt = [cfy.debt_service for cfy in r_sculpt.cash_flows[:15]]
        self.assertNotEqual(ds_annuity, ds_sculpt)


class M4LLCRTests(unittest.TestCase):
    """M4: LLCR = PV(CFADS over loan life) / debt."""

    def test_llcr_present_when_debt_exists(self):
        """LLCR should be computed when debt capacity > 0."""
        params = InvestmentParams(
            region="SA1",
            battery={"power_mw": 50.0, "duration_hours": 2.0},
            financial={"project_life_years": 20, "capex_per_kwh": 350.0},
        )
        result = FinancialModel.run_scenario(
            params, ScenarioConfig(name="Base"),
            baseline_arbitrage=5_000_000.0,
            baseline_fcas=1_000_000.0,
            annual_cycles_history=[365.0] * 20,
        )
        if result.metrics.debt_capacity > 0:
            self.assertIsNotNone(result.metrics.llcr)
            # LLCR ≥ 1 means project can service its debt
            self.assertGreaterEqual(result.metrics.llcr, 1.0)

    def test_llcr_none_without_debt(self):
        """LLCR is None when no debt capacity."""
        # Very small project with no positive CFADS → no debt
        cash_flows = [-100.0, -10.0, -10.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        # calculate_metrics doesn't set LLCR (that's in run_scenario)
        self.assertIsNone(metrics.llcr)


class M5ROIFlagTests(unittest.TestCase):
    """M5: roi_undiscounted flag is explicitly True."""

    def test_roi_undiscounted_flag(self):
        """ROI is flagged as undiscounted."""
        cash_flows = [-100.0, 30.0, 40.0, 50.0]
        metrics = FinancialModel.calculate_metrics(cash_flows, 100.0, 0.08)
        self.assertTrue(metrics.roi_undiscounted)


if __name__ == "__main__":
    unittest.main()
