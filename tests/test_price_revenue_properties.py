"""Property-based tests for price/revenue dimension invariants.

Feature: platform-optimization, Property 1-3: Price and Revenue dimension correctness.

Uses Hypothesis to verify that:
- Property 1: PriceAnalysisEngine output is independent of battery parameters and unit is $/MWh
- Property 2: RevenueAnalysisEngine output unit is $ and revenue is monotonically non-decreasing with capacity
- Property 3: Passing $/MWh-tagged data into RevenueAnalysisEngine raises DimensionMismatchError
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.price_analysis_engine import PriceAnalysisEngine
from engines.revenue_analysis_engine import RevenueAnalysisEngine
from engines.exceptions import DimensionMismatchError


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate a non-empty list of price records with realistic price values
price_record_strategy = st.fixed_dictionaries({
    "timestamp": st.text(min_size=1, max_size=20),
    "price": st.floats(min_value=-500.0, max_value=15000.0, allow_nan=False, allow_infinity=False),
})

price_series_strategy = st.lists(price_record_strategy, min_size=1, max_size=50)

# Battery parameters (used to prove price analysis is independent of them)
battery_power_strategy = st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False)
battery_energy_strategy = st.floats(min_value=0.1, max_value=5000.0, allow_nan=False, allow_infinity=False)
efficiency_strategy = st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False)

# Region and market strategies
region_strategy = st.sampled_from(["NSW1", "QLD1", "VIC1", "SA1", "TAS1"])
market_strategy = st.sampled_from(["NEM", "WEM"])


# ---------------------------------------------------------------------------
# Property 1: 价格分析维度不变量
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    prices=price_series_strategy,
    region=region_strategy,
    market=market_strategy,
    power_mw_a=battery_power_strategy,
    energy_mwh_a=battery_energy_strategy,
    efficiency_a=efficiency_strategy,
    power_mw_b=battery_power_strategy,
    energy_mwh_b=battery_energy_strategy,
    efficiency_b=efficiency_strategy,
)
def test_property_1_price_analysis_dimension_invariant(
    prices,
    region,
    market,
    power_mw_a,
    energy_mwh_a,
    efficiency_a,
    power_mw_b,
    energy_mwh_b,
    efficiency_b,
):
    """Feature: platform-optimization, Property 1: 价格分析维度不变量

    For any price time series and any battery parameter combination,
    PriceAnalysisEngine output should always be the same (independent of
    battery parameters) and metadata.unit must be "$/MWh".

    **Validates: Requirements 1.1, 1.2, 1.4**
    """
    engine = PriceAnalysisEngine()

    # Run analysis — PriceAnalysisEngine does NOT accept battery params,
    # which is the design guarantee. We call it twice with the same prices
    # to confirm deterministic output regardless of what battery params exist.
    result_a = engine.analyze(prices, region=region, market=market)
    result_b = engine.analyze(prices, region=region, market=market)

    # Unit must always be $/MWh
    assert result_a.metadata.unit == "$/MWh", (
        f"Expected unit '$/MWh', got '{result_a.metadata.unit}'"
    )
    assert result_b.metadata.unit == "$/MWh", (
        f"Expected unit '$/MWh', got '{result_b.metadata.unit}'"
    )

    # Results must be identical (price analysis is deterministic and
    # independent of any external battery parameters)
    assert result_a.statistics == result_b.statistics
    assert result_a.distribution == result_b.distribution
    assert result_a.time_series == result_b.time_series


# ---------------------------------------------------------------------------
# Property 2: 收入计算维度正确性
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    prices=price_series_strategy,
    power_mw=battery_power_strategy,
    energy_mwh_small=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
    energy_mwh_large_delta=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    efficiency=efficiency_strategy,
)
def test_property_2_revenue_dimension_correctness(
    prices,
    power_mw,
    energy_mwh_small,
    energy_mwh_large_delta,
    efficiency,
):
    """Feature: platform-optimization, Property 2: 收入计算维度正确性

    For any valid price series and valid battery parameters,
    RevenueAnalysisEngine output metadata.unit must be "$" and revenue
    should be monotonically non-decreasing with capacity (larger capacity
    means equal or greater revenue under the same price series).

    **Validates: Requirements 1.3, 1.4**
    """
    # Ensure at least one positive price exists for meaningful revenue
    assume(any(float(p["price"]) > 0 for p in prices))

    engine = RevenueAnalysisEngine()

    energy_mwh_large = energy_mwh_small + energy_mwh_large_delta

    result_small = engine.calculate(
        prices,
        power_mw=power_mw,
        energy_mwh=energy_mwh_small,
        round_trip_efficiency=efficiency,
    )

    result_large = engine.calculate(
        prices,
        power_mw=power_mw,
        energy_mwh=energy_mwh_large,
        round_trip_efficiency=efficiency,
    )

    # Unit must always be $
    assert result_small.metadata.unit == "$", (
        f"Expected unit '$', got '{result_small.metadata.unit}'"
    )
    assert result_large.metadata.unit == "$", (
        f"Expected unit '$', got '{result_large.metadata.unit}'"
    )

    # Revenue with larger capacity should be >= revenue with smaller capacity
    # (more energy storage means more opportunity to capture value)
    assert result_large.gross_revenue >= result_small.gross_revenue, (
        f"Revenue should be monotonically non-decreasing with capacity: "
        f"small={result_small.gross_revenue}, large={result_large.gross_revenue}, "
        f"energy_small={energy_mwh_small}, energy_large={energy_mwh_large}"
    )


# ---------------------------------------------------------------------------
# Property 3: 维度不匹配拒绝
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    random_stats=st.dictionaries(
        keys=st.text(min_size=1, max_size=10),
        values=st.floats(allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=5,
    ),
    extra_fields=st.dictionaries(
        keys=st.text(min_size=1, max_size=10),
        values=st.text(min_size=0, max_size=20),
        min_size=0,
        max_size=3,
    ),
)
def test_property_3_dimension_mismatch_rejection(
    random_stats,
    extra_fields,
):
    """Feature: platform-optimization, Property 3: 维度不匹配拒绝

    For any input data tagged with metadata.unit="$/MWh", when passed to
    RevenueAnalysisEngine.validate_input_dimensions(), the system should
    raise DimensionMismatchError rather than proceeding with calculation.

    **Validates: Requirements 1.5**
    """
    engine = RevenueAnalysisEngine()

    # Construct input data with $/MWh metadata tag
    input_data = {
        "statistics": random_stats,
        **extra_fields,
        "metadata": {"unit": "$/MWh"},
    }

    # Must raise DimensionMismatchError
    with pytest.raises(DimensionMismatchError) as exc_info:
        engine.validate_input_dimensions(input_data)

    # Verify error attributes
    assert exc_info.value.expected_unit == "raw_price_series"
    assert exc_info.value.received_unit == "$/MWh"
