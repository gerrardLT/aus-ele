"""Property-based tests for Co-Optimization Engine.

Feature: market-modules-redesign, Property 10: Co-optimization dominance
Feature: market-modules-redesign, Property 11: Co-optimization constraint satisfaction
Feature: market-modules-redesign, Property 12: Revenue decomposition additivity

Uses Hypothesis to verify invariants across randomized battery parameters,
energy prices, and FCAS prices.

**Validates: Requirements 6.1, 6.2, 6.3**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.co_optimization_engine import CoOptConfig, CoOptimizationEngine
from models.financial_params import BatterySpecs


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

FCAS_SERVICES = ["raise6sec", "raise60sec", "raise5min"]


@st.composite
def battery_specs(draw):
    """Generate valid BatterySpecs for co-optimization testing.

    Keeps parameters in realistic ranges to ensure solver feasibility.
    """
    power_mw = draw(st.floats(min_value=10.0, max_value=200.0))
    duration_hours = draw(st.floats(min_value=1.0, max_value=4.0))
    rte = draw(st.floats(min_value=0.80, max_value=0.95))

    return BatterySpecs(
        power_mw=power_mw,
        duration_hours=duration_hours,
        round_trip_efficiency=rte,
    )


@st.composite
def energy_price_series(draw, min_size=24, max_size=48):
    """Generate a small energy price series (24-48 intervals).

    Uses realistic NEM-like prices to avoid degenerate cases.
    Each interval is 5 minutes (interval_hours = 5/60).
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    prices = draw(
        st.lists(
            st.floats(min_value=10.0, max_value=500.0),
            min_size=n,
            max_size=n,
        )
    )

    intervals = [
        {
            "timestamp": f"2024-01-01T{i // 12:02d}:{(i % 12) * 5:02d}:00",
            "price": price,
            "interval_hours": 5.0 / 60.0,
        }
        for i, price in enumerate(prices)
    ]
    return intervals


@st.composite
def fcas_price_dict(draw, n_intervals: int):
    """Generate FCAS prices for configured services.

    Prices are positive and in a realistic range for FCAS markets.
    """
    fcas_prices = {}
    for service in FCAS_SERVICES:
        prices = draw(
            st.lists(
                st.floats(min_value=10.0, max_value=500.0),
                min_size=n_intervals,
                max_size=n_intervals,
            )
        )
        fcas_prices[service] = prices
    return fcas_prices


@st.composite
def coopt_test_inputs(draw):
    """Generate a complete set of co-optimization test inputs.

    Returns (BatterySpecs, energy_prices, fcas_prices) tuple.
    """
    specs = draw(battery_specs())
    energy_prices = draw(energy_price_series())
    n = len(energy_prices)
    fcas_prices = draw(fcas_price_dict(n))
    return specs, energy_prices, fcas_prices


# ---------------------------------------------------------------------------
# Property 10: Co-optimization dominance
# ---------------------------------------------------------------------------


class TestProperty10CoOptDominance:
    """Property 10: Co-optimization dominance

    Co-optimization total_net_revenue >= energy_only_revenue.
    Joint optimization can never do worse than energy-only because
    the energy-only solution is a feasible point in the co-optimization
    problem (with all FCAS variables set to zero).

    **Validates: Requirements 6.1, 6.2**
    """

    @given(data=coopt_test_inputs())
    @settings(max_examples=50, deadline=None)
    def test_coopt_revenue_dominates_energy_only(self, data):
        """Co-optimization net revenue must be >= energy-only revenue.

        Feature: market-modules-redesign, Property 10: Co-optimization dominance
        **Validates: Requirements 6.1, 6.2**
        """
        specs, energy_prices, fcas_prices = data

        config = CoOptConfig(
            fcas_services=FCAS_SERVICES,
            fcas_max_capacity_pct=0.5,
            time_limit_seconds=15,
            optimality_gap_tolerance=0.05,
            monthly_segmentation=False,
        )

        engine = CoOptimizationEngine(specs, config)
        result = engine.optimize(energy_prices, fcas_prices)

        # Only assert when both co-opt and energy-only succeed
        if result.status not in ("optimal", "feasible"):
            return

        if result.energy_only_revenue is None:
            return

        # Co-optimization should never do worse than energy-only
        # Allow tolerance for solver gap and floating point
        tolerance = 0.1 + abs(result.energy_only_revenue) * 0.02

        assert result.total_net_revenue >= result.energy_only_revenue - tolerance, (
            f"Co-optimization dominance violated: "
            f"co_opt_net_revenue={result.total_net_revenue:.4f} < "
            f"energy_only_revenue={result.energy_only_revenue:.4f}. "
            f"Difference: {result.total_net_revenue - result.energy_only_revenue:.4f}. "
            f"Status: {result.status}, gap: {result.optimality_gap}"
        )


# ---------------------------------------------------------------------------
# Property 11: Co-optimization constraint satisfaction
# ---------------------------------------------------------------------------


class TestProperty11ConstraintSatisfaction:
    """Property 11: Co-optimization constraint satisfaction

    For any optimal/feasible result, the solver must produce a valid solution.
    This is implicitly enforced by the MILP constraints (SOC bounds are
    hard constraints in the model), but we verify the solver doesn't return
    infeasible for reasonable inputs.

    **Validates: Requirements 6.2, 6.3**
    """

    @given(data=coopt_test_inputs())
    @settings(max_examples=50, deadline=None)
    def test_reasonable_inputs_produce_feasible_solution(self, data):
        """Reasonable inputs should not produce infeasible results.

        Feature: market-modules-redesign, Property 11: Co-optimization constraint satisfaction
        **Validates: Requirements 6.2, 6.3**
        """
        specs, energy_prices, fcas_prices = data

        config = CoOptConfig(
            fcas_services=FCAS_SERVICES,
            fcas_max_capacity_pct=0.5,
            time_limit_seconds=15,
            optimality_gap_tolerance=0.05,
            monthly_segmentation=False,
        )

        engine = CoOptimizationEngine(specs, config)
        result = engine.optimize(energy_prices, fcas_prices)

        # For reasonable inputs, the problem should be feasible or timeout with a solution.
        # "timeout" without a solution is acceptable for very tight time limits.
        assert result.status in ("optimal", "feasible", "timeout"), (
            f"Expected feasible solution for reasonable inputs, "
            f"got status='{result.status}', solver_status='{result.solver_status}'. "
            f"Battery: power_mw={specs.power_mw:.1f}, "
            f"capacity_mwh={specs.capacity_mwh:.1f}, "
            f"rte={specs.round_trip_efficiency:.3f}. "
            f"Intervals: {len(energy_prices)}"
        )


# ---------------------------------------------------------------------------
# Property 12: Revenue decomposition additivity
# ---------------------------------------------------------------------------


class TestProperty12RevenueDecomposition:
    """Property 12: Revenue decomposition additivity

    total_gross_revenue = energy_revenue + fcas_revenue (exact equality).
    The gross revenue must always decompose exactly into its energy and
    FCAS components.

    **Validates: Requirements 6.1, 6.3**
    """

    @given(data=coopt_test_inputs())
    @settings(max_examples=50, deadline=None)
    def test_revenue_decomposition_is_additive(self, data):
        """total_gross_revenue must equal energy_revenue + fcas_revenue.

        Feature: market-modules-redesign, Property 12: Revenue decomposition additivity
        **Validates: Requirements 6.1, 6.3**
        """
        specs, energy_prices, fcas_prices = data

        config = CoOptConfig(
            fcas_services=FCAS_SERVICES,
            fcas_max_capacity_pct=0.5,
            time_limit_seconds=15,
            optimality_gap_tolerance=0.05,
            monthly_segmentation=False,
        )

        engine = CoOptimizationEngine(specs, config)
        result = engine.optimize(energy_prices, fcas_prices)

        # Only check when we have a valid solution
        if result.status not in ("optimal", "feasible"):
            return

        expected_gross = result.energy_revenue + result.fcas_revenue

        # Use tolerance for floating point rounding: the engine rounds each
        # component independently to 2 decimal places, so round(a,2) + round(b,2)
        # can differ from round(a+b,2) by up to 0.01. Use 0.02 for safety.
        assert abs(result.total_gross_revenue - expected_gross) < 0.02, (
            f"Revenue decomposition violated: "
            f"total_gross_revenue={result.total_gross_revenue:.4f} != "
            f"energy_revenue({result.energy_revenue:.4f}) + "
            f"fcas_revenue({result.fcas_revenue:.4f}) = {expected_gross:.4f}. "
            f"Difference: {abs(result.total_gross_revenue - expected_gross):.6f}"
        )
