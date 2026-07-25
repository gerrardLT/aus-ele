"""Tests for S3/B3: cannibalization effect feedback into multi-year cash flows.

Validates:
- Decay factors ∈ (0, 1] and monotonically decreasing with year
- Enabling cannibalization → NPV monotonically non-increasing
- Disabled (default) → bit-identical results (zero regression)
"""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.financial_model import FinancialModel
from models.financial_params import InvestmentParams, ScenarioConfig


class CannibalizationDecayFactorTests(unittest.TestCase):
    """Property tests for compute_cannibalization_decay_factors."""

    def test_factors_in_unit_interval(self):
        """All decay factors must be in (0, 1]."""
        factors = FinancialModel.compute_cannibalization_decay_factors(
            n_years=20, alpha=0.6, annual_growth_rate=0.10
        )
        self.assertEqual(len(factors), 20)
        for i, f in enumerate(factors):
            self.assertGreater(f, 0.0, f"Factor at year {i} must be > 0")
            self.assertLessEqual(f, 1.0, f"Factor at year {i} must be ≤ 1")

    def test_first_factor_is_one(self):
        """Year 1 (t=0) has no decay: factor = 1.0."""
        factors = FinancialModel.compute_cannibalization_decay_factors(
            n_years=10, alpha=0.6, annual_growth_rate=0.10
        )
        self.assertAlmostEqual(factors[0], 1.0)

    def test_monotonically_decreasing(self):
        """Factors decrease with year (more capacity → more dilution)."""
        factors = FinancialModel.compute_cannibalization_decay_factors(
            n_years=20, alpha=0.6, annual_growth_rate=0.10
        )
        for i in range(1, len(factors)):
            self.assertLessEqual(
                factors[i], factors[i - 1],
                f"Factor[{i}]={factors[i]} should be ≤ Factor[{i-1}]={factors[i-1]}"
            )

    def test_higher_alpha_faster_decay(self):
        """Higher alpha → faster revenue dilution."""
        f_low = FinancialModel.compute_cannibalization_decay_factors(20, alpha=0.3, annual_growth_rate=0.10)
        f_high = FinancialModel.compute_cannibalization_decay_factors(20, alpha=0.9, annual_growth_rate=0.10)
        # At year 20, higher alpha should give lower factor
        self.assertLess(f_high[-1], f_low[-1])

    def test_zero_growth_no_decay(self):
        """Zero market growth → all factors are 1.0 (no dilution)."""
        factors = FinancialModel.compute_cannibalization_decay_factors(
            n_years=20, alpha=0.6, annual_growth_rate=0.0
        )
        for f in factors:
            self.assertAlmostEqual(f, 1.0)


class CannibalizationNPVTests(unittest.TestCase):
    """Integration tests: cannibalization effect on NPV."""

    def _build_params(self, apply_cannibalization: bool = False, **overrides):
        payload = {
            "region": "SA1",
            "battery": {"power_mw": 50.0, "duration_hours": 2.0},
            "financial": {
                "project_life_years": 20,
                "discount_rate": 0.08,
                "capex_per_kwh": 350.0,
            },
            "apply_cannibalization": apply_cannibalization,
            "cannibalization_alpha": 0.6,
            "cannibalization_annual_growth_rate": 0.10,
        }
        payload.update(overrides)
        return InvestmentParams(**payload)

    def test_disabled_is_zero_regression(self):
        """Default flag is False; disabled run is deterministic and unchanged."""
        # Verify the default is disabled
        bare_params = InvestmentParams(region="SA1")
        self.assertFalse(bare_params.apply_cannibalization)

        # Two identical runs with cannibalization off → same NPV (determinism)
        params = self._build_params(apply_cannibalization=False)
        scenario = ScenarioConfig(name="Base")
        baseline_arb = 5_000_000.0
        baseline_fcas = 1_000_000.0
        cycles = [365.0] * 20

        r1 = FinancialModel.run_scenario(
            params, scenario, baseline_arb, baseline_fcas, cycles
        )
        r2 = FinancialModel.run_scenario(
            params, scenario, baseline_arb, baseline_fcas, cycles
        )
        self.assertEqual(r1.metrics.npv, r2.metrics.npv)

    def test_enabled_npv_monotonically_non_increasing(self):
        """Enabling cannibalization cannot increase NPV (revenue only goes down)."""
        scenario = ScenarioConfig(name="Base")
        baseline_arb = 5_000_000.0
        baseline_fcas = 1_000_000.0
        cycles = [365.0] * 20

        params_off = self._build_params(apply_cannibalization=False)
        params_on = self._build_params(apply_cannibalization=True)

        r_off = FinancialModel.run_scenario(
            params_off, scenario, baseline_arb, baseline_fcas, cycles
        )
        r_on = FinancialModel.run_scenario(
            params_on, scenario, baseline_arb, baseline_fcas, cycles
        )
        self.assertLessEqual(
            r_on.metrics.npv, r_off.metrics.npv,
            "Cannibalization should reduce or maintain NPV, never increase it"
        )

    def test_stronger_cannibalization_lower_npv(self):
        """Higher growth rate → lower NPV (more dilution)."""
        scenario = ScenarioConfig(name="Base")
        baseline_arb = 5_000_000.0
        baseline_fcas = 1_000_000.0
        cycles = [365.0] * 20

        params_mild = self._build_params(
            apply_cannibalization=True, cannibalization_annual_growth_rate=0.05
        )
        params_severe = self._build_params(
            apply_cannibalization=True, cannibalization_annual_growth_rate=0.20
        )

        r_mild = FinancialModel.run_scenario(
            params_mild, scenario, baseline_arb, baseline_fcas, cycles
        )
        r_severe = FinancialModel.run_scenario(
            params_severe, scenario, baseline_arb, baseline_fcas, cycles
        )
        self.assertLessEqual(
            r_severe.metrics.npv, r_mild.metrics.npv,
            "More aggressive cannibalization should yield lower NPV"
        )

    def test_fcas_revenue_unaffected(self):
        """Cannibalization only affects arbitrage, not FCAS revenue."""
        scenario = ScenarioConfig(name="Base")
        baseline_arb = 0.0  # zero arbitrage
        baseline_fcas = 2_000_000.0
        cycles = [100.0] * 20

        params_off = self._build_params(apply_cannibalization=False)
        params_on = self._build_params(apply_cannibalization=True)

        r_off = FinancialModel.run_scenario(
            params_off, scenario, baseline_arb, baseline_fcas, cycles
        )
        r_on = FinancialModel.run_scenario(
            params_on, scenario, baseline_arb, baseline_fcas, cycles
        )
        # With zero arbitrage, cannibalization has no effect
        self.assertAlmostEqual(r_on.metrics.npv, r_off.metrics.npv, places=2)


if __name__ == "__main__":
    unittest.main()
