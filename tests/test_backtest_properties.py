"""Property-based tests for BESS Backtest Engine V2.

Feature: platform-optimization, Property 5: SOC 边界不变量
Feature: platform-optimization, Property 6: 回测收入非负性

Uses Hypothesis to verify invariants across randomized battery parameters
and price sequences.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.bess_backtest_v2 import (
    BacktestConstraints,
    BacktestV2Params,
    run_bess_backtest_v2,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_battery_params(draw):
    """Generate valid battery parameters for backtest.

    Ensures:
    - Positive power and energy values
    - min_soc_pct < max_soc_pct with sufficient gap
    - Valid round-trip efficiency
    - initial_soc within SOC bounds
    - No auxiliary power (simplifies feasibility)
    """
    energy_mwh = draw(st.floats(min_value=10.0, max_value=500.0))
    max_charge_mw = draw(st.floats(min_value=1.0, max_value=100.0))
    max_discharge_mw = draw(st.floats(min_value=1.0, max_value=100.0))

    min_soc_pct = draw(st.floats(min_value=5.0, max_value=40.0))
    max_soc_pct = draw(st.floats(min_value=60.0, max_value=95.0))

    round_trip_efficiency = draw(st.floats(min_value=0.7, max_value=1.0))

    # Initial SOC must be within bounds
    min_soc_mwh = energy_mwh * (min_soc_pct / 100.0)
    max_soc_mwh = energy_mwh * (max_soc_pct / 100.0)
    initial_soc_mwh = draw(
        st.floats(min_value=min_soc_mwh, max_value=max_soc_mwh)
    )

    constraints = BacktestConstraints(
        max_charge_mw=max_charge_mw,
        max_discharge_mw=max_discharge_mw,
        min_soc_pct=min_soc_pct,
        max_soc_pct=max_soc_pct,
        round_trip_efficiency=round_trip_efficiency,
        auxiliary_power_mw=0.0,
        min_duration_intervals=1,
        dispatch_alignment_minutes=5,
        registered_capacity_mw=None,
    )

    params = BacktestV2Params(
        energy_mwh=energy_mwh,
        initial_soc_mwh=initial_soc_mwh,
        constraints=constraints,
        max_cycles_per_day=2.0,
        network_fee_per_mwh=0.0,
        degradation_cost_per_mwh=0.0,
        variable_om_per_mwh=0.0,
    )

    return params


@st.composite
def price_intervals(draw, min_size=5, max_size=20):
    """Generate a random price sequence with 5-minute intervals.

    Prices are realistic electricity market values (can be negative).
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    prices = draw(
        st.lists(
            st.floats(min_value=-50.0, max_value=500.0),
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
def price_intervals_with_positive_spread(draw, min_size=5, max_size=20):
    """Generate price intervals guaranteed to have a positive spread.

    Ensures max(prices) - min(prices) > 0 so arbitrage is possible.
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))

    # Generate base prices
    prices = draw(
        st.lists(
            st.floats(min_value=10.0, max_value=300.0),
            min_size=n,
            max_size=n,
        )
    )

    # Ensure there's a meaningful spread by forcing at least one low and one high
    low_price = draw(st.floats(min_value=10.0, max_value=50.0))
    high_price = draw(st.floats(min_value=100.0, max_value=500.0))

    # Replace first and last with guaranteed low/high
    prices[0] = low_price
    prices[-1] = high_price

    intervals = [
        {
            "timestamp": f"2024-01-01T{i // 12:02d}:{(i % 12) * 5:02d}:00",
            "price": price,
            "interval_hours": 5.0 / 60.0,
        }
        for i, price in enumerate(prices)
    ]
    return intervals


# ---------------------------------------------------------------------------
# Property 5: SOC 边界不变量
# ---------------------------------------------------------------------------


class TestProperty5SocBoundaryInvariant:
    """Property 5: SOC 边界不变量

    For any valid battery parameters (power_mw > 0, energy_mwh > 0,
    0 < min_soc_pct < max_soc_pct <= 100) and any non-empty price sequence,
    the Backtest_Engine result timeline must satisfy:
        energy_mwh * min_soc_pct/100 <= soc_mwh <= energy_mwh * max_soc_pct/100
    at every time step.

    **Validates: Requirements 9.1, 9.5**
    """

    @given(params=valid_battery_params(), intervals=price_intervals())
    @settings(max_examples=50, deadline=None)
    def test_soc_within_bounds_for_random_inputs(self, params, intervals):
        """SOC must stay within [SOC_min, SOC_max] for all optimal solutions.

        Feature: platform-optimization, Property 5: SOC 边界不变量
        **Validates: Requirements 9.1, 9.5**
        """
        result = run_bess_backtest_v2(params, intervals)

        # Only check optimal solutions — infeasible results have no timeline
        if result.status != "optimal":
            return

        min_soc_mwh = params.energy_mwh * (params.constraints.min_soc_pct / 100.0)
        max_soc_mwh = params.energy_mwh * (params.constraints.max_soc_pct / 100.0)

        # Allow small numerical tolerance for MILP solver
        tolerance = 1e-4

        for i, item in enumerate(result.timeline):
            soc = item["soc_mwh"]
            assert soc >= min_soc_mwh - tolerance, (
                f"SOC violation at interval {i}: soc_mwh={soc:.6f} < "
                f"min_soc_mwh={min_soc_mwh:.6f} "
                f"(min_soc_pct={params.constraints.min_soc_pct}, "
                f"energy_mwh={params.energy_mwh})"
            )
            assert soc <= max_soc_mwh + tolerance, (
                f"SOC violation at interval {i}: soc_mwh={soc:.6f} > "
                f"max_soc_mwh={max_soc_mwh:.6f} "
                f"(max_soc_pct={params.constraints.max_soc_pct}, "
                f"energy_mwh={params.energy_mwh})"
            )


# ---------------------------------------------------------------------------
# Property 6: 回测收入非负性
# ---------------------------------------------------------------------------


class TestProperty6RevenueNonNegativity:
    """Property 6: 回测收入非负性（在正价差市场）

    For any price sequence with a positive spread (max - min > 0),
    valid battery parameters, and terminal SOC constraint (soc[-1] >= initial_soc),
    the Backtest_Engine net_revenue must be >= 0.

    The optimizer can always choose to do nothing (zero charge/discharge),
    so it should never actively choose a loss-making strategy.

    **Validates: Requirements 9.1, 9.2**
    """

    @given(
        params=valid_battery_params(),
        intervals=price_intervals_with_positive_spread(),
    )
    @settings(max_examples=50, deadline=None)
    def test_net_revenue_non_negative_with_positive_spread(self, params, intervals):
        """Net revenue must be >= 0 when price spread exists and optimizer is free.

        Feature: platform-optimization, Property 6: 回测收入非负性
        **Validates: Requirements 9.1, 9.2**
        """
        result = run_bess_backtest_v2(params, intervals)

        # Only check optimal solutions
        if result.status != "optimal":
            return

        net_revenue = result.summary["net_revenue"]

        # Allow small numerical tolerance for MILP solver rounding
        tolerance = 1e-4

        assert net_revenue >= -tolerance, (
            f"Net revenue is negative: {net_revenue:.6f}. "
            f"The optimizer should be able to achieve non-negative revenue "
            f"by choosing not to operate. "
            f"Params: energy_mwh={params.energy_mwh}, "
            f"initial_soc_mwh={params.initial_soc_mwh}, "
            f"max_charge_mw={params.constraints.max_charge_mw}, "
            f"max_discharge_mw={params.constraints.max_discharge_mw}, "
            f"efficiency={params.constraints.round_trip_efficiency}"
        )
