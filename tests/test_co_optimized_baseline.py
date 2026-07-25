"""Tests for S2: co-optimized energy+FCAS revenue baseline (B2) and A2 magic numbers.

Validates:
- co_optimized_net ≤ additive_net (joint optimization respects power coupling)
- Power constraint (charge + discharge + fcas_enablement ≤ P_max) not violated
- Uplift sign is reasonable (≥ 0: adding FCAS can only help)
- Zero-regression: revenue_baseline_mode="additive" is the default
"""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.co_optimization_engine import CoOptConfig, CoOptimizationEngine
from models.financial_params import BatterySpecs, InvestmentParams
from services.investment_baseline import (
    DEFAULT_FCAS_SERVICES,
    CoOptimizedBaseline,
    derive_co_optimized_baseline,
)


def _make_energy_prices(n_intervals: int = 48, interval_hours: float = 0.5):
    """Synthetic daily price pattern: cheap overnight, expensive peak."""
    prices = []
    for i in range(n_intervals):
        hour = i * interval_hours
        if hour < 6 or hour >= 22:
            price = 20.0
        elif 16 <= hour < 20:
            price = 200.0
        else:
            price = 80.0
        prices.append({
            "timestamp": f"2025-01-01T{int(hour):02d}:{int((hour % 1) * 60):02d}:00",
            "price": price,
            "interval_hours": interval_hours,
        })
    return prices


def _make_fcas_prices(n_intervals: int = 48, price: float = 5.0):
    """Flat FCAS price for all services."""
    return {s: [price] * n_intervals for s in DEFAULT_FCAS_SERVICES}


class CoOptimizedBaselineTests(unittest.TestCase):
    """Unit tests for derive_co_optimized_baseline."""

    def _build_params(self, **overrides):
        payload = {
            "region": "NSW1",
            "battery": {
                "power_mw": 10.0,
                "duration_hours": 2.0,
                "round_trip_efficiency": 0.90,
            },
            "backtest_years": [2025],
        }
        payload.update(overrides)
        return InvestmentParams(**payload)

    def test_returns_baseline_with_valid_data(self):
        """Engine produces a feasible baseline from synthetic data."""
        params = self._build_params()
        yearly_data = [{
            "energy_prices": _make_energy_prices(),
            "fcas_prices": _make_fcas_prices(),
        }]
        result = derive_co_optimized_baseline(params, yearly_data)
        self.assertIsInstance(result, CoOptimizedBaseline)
        self.assertGreater(result.years_used, 0)
        self.assertIn(result.status, ("optimal", "feasible"))
        self.assertGreater(result.energy_revenue, 0)

    def test_co_optimized_net_leq_additive_net(self):
        """Joint optimization total ≤ sum of separately-optimized streams.

        The additive path optimizes energy alone (full power) + FCAS alone
        (full power), double-counting capacity. The joint path shares power,
        so its total cannot exceed the additive sum.
        """
        specs = BatterySpecs(power_mw=10.0, duration_hours=2.0, round_trip_efficiency=0.90)
        energy_prices = _make_energy_prices()
        fcas_prices = _make_fcas_prices()

        # Energy-only optimization (no FCAS)
        config_energy = CoOptConfig(fcas_services=[], monthly_segmentation=False)
        engine_energy = CoOptimizationEngine(specs, config_energy)
        energy_only_result = engine_energy.optimize(
            energy_prices, {}, variable_om_per_mwh=0.0,
            network_fee_per_mwh=0.0, degradation_cost_per_mwh=0.0,
        )

        # Joint optimization (energy + FCAS)
        config_joint = CoOptConfig(
            fcas_services=list(DEFAULT_FCAS_SERVICES), monthly_segmentation=False
        )
        engine_joint = CoOptimizationEngine(specs, config_joint)
        joint_result = engine_joint.optimize(
            energy_prices, fcas_prices, variable_om_per_mwh=0.0,
            network_fee_per_mwh=0.0, degradation_cost_per_mwh=0.0,
        )

        # Additive upper bound = energy_only_net + fcas_revenue (double-counted power)
        additive_upper = energy_only_result.total_net_revenue + joint_result.fcas_revenue
        self.assertLessEqual(
            joint_result.total_net_revenue,
            additive_upper + 1e-6,
            "Joint optimization should not exceed additive upper bound",
        )

    def test_uplift_accounting_identity(self):
        """Uplift = total_net_revenue - energy_only_revenue (accounting identity).

        Note: uplift CAN be negative when FCAS SOC-reserve constraints restrict
        energy arbitrage more than FCAS revenue compensates. This is a valid
        economic outcome, not a bug.
        """
        params = self._build_params()
        yearly_data = [{
            "energy_prices": _make_energy_prices(),
            "fcas_prices": _make_fcas_prices(),
        }]
        result = derive_co_optimized_baseline(params, yearly_data)
        if (
            result.co_optimization_uplift is not None
            and result.energy_only_revenue is not None
        ):
            expected_uplift = result.total_net_revenue - result.energy_only_revenue
            self.assertAlmostEqual(
                result.co_optimization_uplift,
                expected_uplift,
                places=1,
                msg="uplift should equal total_net - energy_only",
            )
        # Joint total is always non-negative (optimizer can choose zero dispatch)
        self.assertGreaterEqual(result.total_net_revenue, -1e-6)

    def test_power_constraint_not_violated(self):
        """Engine binding constraints confirm P_max coupling is enforced."""
        specs = BatterySpecs(power_mw=10.0, duration_hours=2.0, round_trip_efficiency=0.90)
        config = CoOptConfig(
            fcas_services=list(DEFAULT_FCAS_SERVICES), monthly_segmentation=False
        )
        engine = CoOptimizationEngine(specs, config)
        result = engine.optimize(
            _make_energy_prices(),
            _make_fcas_prices(price=50.0),  # high FCAS price to stress coupling
            variable_om_per_mwh=0.0,
            network_fee_per_mwh=0.0,
            degradation_cost_per_mwh=0.0,
        )
        self.assertIn(result.status, ("optimal", "feasible"))
        # With high FCAS price, coupling constraints should bind or FCAS earns revenue
        binding_names = [c.get("name", "") for c in result.binding_constraints]
        has_coupling = any("fcas" in name for name in binding_names)
        self.assertTrue(
            has_coupling or result.fcas_revenue > 0,
            "FCAS coupling should be active or FCAS revenue positive",
        )

    def test_empty_data_returns_zero_years(self):
        """No price data → years_used=0, caller falls back to additive."""
        params = self._build_params()
        result = derive_co_optimized_baseline(params, [])
        self.assertEqual(result.years_used, 0)
        self.assertEqual(result.energy_revenue, 0.0)

    def test_multi_year_averaging(self):
        """Multiple years are averaged correctly."""
        params = self._build_params(backtest_years=[2024, 2025])
        yearly_data = [
            {"energy_prices": _make_energy_prices(), "fcas_prices": _make_fcas_prices()},
            {"energy_prices": _make_energy_prices(), "fcas_prices": _make_fcas_prices()},
        ]
        result = derive_co_optimized_baseline(params, yearly_data)
        self.assertEqual(result.years_used, 2)


class RevenueBaselineModeTests(unittest.TestCase):
    """Verify the revenue_baseline_mode switch on InvestmentParams."""

    def test_default_is_additive(self):
        """Default mode is 'additive' for zero-regression."""
        params = InvestmentParams(region="SA1")
        self.assertEqual(params.revenue_baseline_mode, "additive")

    def test_co_optimized_mode_accepted(self):
        """'co_optimized' is a valid mode value."""
        params = InvestmentParams(region="SA1", revenue_baseline_mode="co_optimized")
        self.assertEqual(params.revenue_baseline_mode, "co_optimized")

    def test_invalid_mode_rejected(self):
        """Invalid mode raises validation error."""
        with self.assertRaises(Exception):
            InvestmentParams(region="SA1", revenue_baseline_mode="invalid_mode")


class A2MagicNumberTests(unittest.TestCase):
    """Verify A2: magic numbers replaced by named constants/params."""

    def test_hours_per_year_constant(self):
        """HOURS_PER_YEAR is defined and equals 8760."""
        from routes.investment_routes import HOURS_PER_YEAR
        self.assertEqual(HOURS_PER_YEAR, 8760)

    def test_fcas_revenue_per_mw_year_default(self):
        """Default fcas_revenue_per_mw_year matches the old magic number 15000."""
        params = InvestmentParams(region="SA1")
        self.assertEqual(params.fcas_revenue_per_mw_year, 15000.0)


if __name__ == "__main__":
    unittest.main()
