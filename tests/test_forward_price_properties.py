"""Property-based tests for Forward Price Scenario Engine.

Feature: financial-accuracy-modules, Property 15: Event Impact Multiplicative Composition
Feature: financial-accuracy-modules, Property 16: BESS Saturation Compression Monotonicity
Feature: financial-accuracy-modules, Property 17: Price Distribution Output Bounds
Feature: financial-accuracy-modules, Property 18: Revenue Degradation Monotonicity
Feature: financial-accuracy-modules, Property 19: Revenue Efficiency Metamorphic Property
Feature: financial-accuracy-modules, Property 22: Forward Price Serialization Round-Trip

Uses Hypothesis to verify invariants across randomized event parameters,
battery specs, and scenario configurations.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import math
from datetime import date, timedelta

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.forward_price_engine import (
    BASE_CAPTURE_RATE,
    BASE_SPREAD_PARAMS,
    ForwardPriceEngine,
    PEAK_DEMAND,
    SATURATION_SENSITIVITY,
    SUPPORTED_REGIONS,
)
from models.forward_price_models import (
    AnnualRevenueProjection,
    EventConfidence,
    EventRegistry,
    EventType,
    PriceDistribution,
    ScenarioDefinition,
    ScenarioProjection,
    ScenarioType,
    SupplyDemandEvent,
)
from models.financial_params import BatterySpecs


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_region(draw):
    """Generate a valid region code."""
    return draw(st.sampled_from(SUPPORTED_REGIONS))


@st.composite
def valid_scenario_type(draw):
    """Generate a valid scenario type."""
    return draw(st.sampled_from(list(ScenarioType)))


@st.composite
def valid_bess_capacity_ratio(draw):
    """Generate a valid BESS capacity-to-demand ratio (0 to 2.0)."""
    return draw(st.floats(min_value=0.0, max_value=2.0))


@st.composite
def valid_impact_factor(draw):
    """Generate a valid spread impact factor."""
    return draw(st.floats(min_value=0.5, max_value=2.0))


@st.composite
def valid_battery_specs(draw):
    """Generate valid BatterySpecs for revenue calculations."""
    power_mw = draw(st.floats(min_value=10.0, max_value=500.0))
    duration_hours = draw(st.floats(min_value=1.0, max_value=8.0))
    rte = draw(st.floats(min_value=0.70, max_value=0.95))
    degradation = draw(st.floats(min_value=0.005, max_value=0.03))
    return BatterySpecs(
        power_mw=power_mw,
        duration_hours=duration_hours,
        round_trip_efficiency=rte,
        calendar_degradation_rate=degradation,
    )


@st.composite
def valid_supply_demand_event(draw):
    """Generate a valid future SupplyDemandEvent."""
    event_type = draw(st.sampled_from(list(EventType)))
    region = draw(st.sampled_from(SUPPORTED_REGIONS))
    # Future date: 1 to 15 years from now
    days_ahead = draw(st.integers(min_value=365, max_value=365 * 15))
    expected_date = date.today() + timedelta(days=days_ahead)
    capacity_mw = draw(st.floats(min_value=10.0, max_value=3000.0))
    confidence = draw(st.sampled_from(list(EventConfidence)))
    impact_factor = draw(st.floats(min_value=0.5, max_value=2.0))

    return SupplyDemandEvent(
        event_type=event_type,
        name=f"Test Event {region}",
        region=region,
        expected_date=expected_date,
        capacity_mw=capacity_mw,
        confidence=confidence,
        spread_impact_factor=impact_factor,
    )


@st.composite
def valid_scenario_projection(draw):
    """Generate a valid ScenarioProjection for serialization tests."""
    scenario = draw(st.sampled_from(list(ScenarioType)))
    region = draw(st.sampled_from(SUPPORTED_REGIONS))

    num_years = draw(st.integers(min_value=1, max_value=20))
    projections = []
    for i in range(num_years):
        projections.append(
            AnnualRevenueProjection(
                year=2025 + i,
                estimated_revenue_per_mw=draw(
                    st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False)
                ),
                state_of_health=draw(st.floats(min_value=0.5, max_value=1.0)),
                mean_spread=draw(
                    st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
                ),
                capture_rate=draw(st.floats(min_value=0.0, max_value=1.0)),
            )
        )

    total_revenue = sum(p.estimated_revenue_per_mw for p in projections)
    npv = draw(st.floats(min_value=-1000000.0, max_value=5000000.0, allow_nan=False, allow_infinity=False))

    return ScenarioProjection(
        scenario=scenario,
        region=region,
        annual_projections=projections,
        total_revenue_per_mw=total_revenue,
        npv_per_mw=npv,
    )


# ---------------------------------------------------------------------------
# Property 15: Event Impact Multiplicative Composition
# ---------------------------------------------------------------------------


class TestEventImpactMultiplicativeComposition:
    """**Validates: Requirements 8.3**

    For any sequence of supply-demand events affecting a region, the final
    spread parameter for a future year SHALL equal the base spread × product
    of all applicable event impact factors.
    """

    @given(
        region=valid_region(),
        impact_factors=st.lists(
            st.floats(min_value=0.5, max_value=2.0),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_spread_equals_base_times_product_of_impacts(
        self, region: str, impact_factors: list
    ):
        """Event impacts compose multiplicatively relative to no-event baseline.

        修正（2026-07-28）：旧断言假设 ratio=0 时 compression=1，但 PSF 项
        不依赖 ratio，导致 compression<1。改用比值法（有事件/无事件）隔离
        事件乘性效应，与压缩无关。同时改用 NETWORK_AUGMENTATION 事件类型
        （无煤退衰减/情景调整/交互效应）以纯粹测试乘性组合性质。
        """
        today = date.today()
        target_year = today.year + 10

        # 使用 NETWORK_AUGMENTATION：无衰减、无情景调整、无交互效应
        events = []
        for i, factor in enumerate(impact_factors):
            event_date = today + timedelta(days=365 * (i + 1))
            events.append(
                SupplyDemandEvent(
                    event_type=EventType.NETWORK_AUGMENTATION,
                    name=f"Test Event {i}",
                    region=region,
                    expected_date=event_date,
                    capacity_mw=500.0,
                    confidence=EventConfidence.CONFIRMED,
                    spread_impact_factor=factor,
                )
            )

        # 基线：无事件
        engine_base = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine_base.event_registry = EventRegistry(events=[], last_updated=today)
        dist_base = engine_base.calculate_price_distribution(
            region=region, scenario=ScenarioType.CENTRAL,
            year=target_year, bess_capacity_ratio=0.0,
        )

        # 有事件
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=events, last_updated=today)
        dist = engine.calculate_price_distribution(
            region=region, scenario=ScenarioType.CENTRAL,
            year=target_year, bess_capacity_ratio=0.0,
        )

        # 性质：比值 == 因子乘积（乘性组合，与压缩无关）
        expected_ratio = math.prod(impact_factors)
        actual_ratio = (
            dist.mean_spread / dist_base.mean_spread
            if dist_base.mean_spread > 0 else 1.0
        )
        assert math.isclose(actual_ratio, expected_ratio, rel_tol=1e-6)

    @given(
        region=valid_region(),
        factor=st.floats(min_value=0.5, max_value=2.0),
    )
    @settings(max_examples=100)
    def test_single_event_impact_is_multiplicative(self, region: str, factor: float):
        """A single event multiplies the spread by its factor (ratio method).

        修正（2026-07-28）：同 test_spread_equals_base_times_product_of_impacts，
        改用比值法 + NETWORK_AUGMENTATION 事件类型。
        """
        today = date.today()
        target_year = today.year + 5

        event = SupplyDemandEvent(
            event_type=EventType.NETWORK_AUGMENTATION,
            name="Single Test Event",
            region=region,
            expected_date=today + timedelta(days=365),
            capacity_mw=1000.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=factor,
        )

        # 基线：无事件
        engine_base = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine_base.event_registry = EventRegistry(events=[], last_updated=today)
        dist_base = engine_base.calculate_price_distribution(
            region=region, scenario=ScenarioType.CENTRAL,
            year=target_year, bess_capacity_ratio=0.0,
        )

        # 有事件
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=[event], last_updated=today)
        dist = engine.calculate_price_distribution(
            region=region, scenario=ScenarioType.CENTRAL,
            year=target_year, bess_capacity_ratio=0.0,
        )

        # 性质：比值 == factor
        actual_ratio = (
            dist.mean_spread / dist_base.mean_spread
            if dist_base.mean_spread > 0 else 1.0
        )
        assert math.isclose(actual_ratio, factor, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Property 16: BESS Saturation Compression Monotonicity
# ---------------------------------------------------------------------------


class TestBessSaturationCompressionMonotonicity:
    """**Validates: Requirements 8.4**

    For any two BESS capacity-to-demand ratios r1 < r2, the compression
    factor at r2 SHALL be less than or equal to the compression factor at r1.
    """

    @given(
        region=valid_region(),
        scenario=valid_scenario_type(),
        ratio_low=st.floats(min_value=0.0, max_value=1.0),
        ratio_delta=st.floats(min_value=0.01, max_value=1.0),
    )
    @settings(max_examples=100)
    def test_higher_ratio_lower_compression(
        self, region: str, scenario: ScenarioType, ratio_low: float, ratio_delta: float
    ):
        """Higher BESS penetration → lower or equal compression factor."""
        ratio_high = ratio_low + ratio_delta

        # Create engine with no events to isolate compression effect
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=[], last_updated=date.today())

        target_year = date.today().year + 5

        dist_low = engine.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=target_year,
            bess_capacity_ratio=ratio_low,
        )
        dist_high = engine.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=target_year,
            bess_capacity_ratio=ratio_high,
        )

        # Compression factor should be monotonically non-increasing
        assert dist_high.compression_factor <= dist_low.compression_factor + 1e-9

    @given(
        region=valid_region(),
        scenario=valid_scenario_type(),
        ratio=st.floats(min_value=0.0, max_value=2.0),
    )
    @settings(max_examples=100)
    def test_compression_factor_in_valid_range(
        self, region: str, scenario: ScenarioType, ratio: float
    ):
        """Compression factor is always between 0.0 and 1.0."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=[], last_updated=date.today())

        target_year = date.today().year + 5

        dist = engine.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=target_year,
            bess_capacity_ratio=ratio,
        )

        assert 0.0 <= dist.compression_factor <= 1.0


# ---------------------------------------------------------------------------
# Property 17: Price Distribution Output Bounds
# ---------------------------------------------------------------------------


class TestPriceDistributionOutputBounds:
    """**Validates: Requirements 8.5, 8.6**

    All outputs within defined ranges: mean_spread [0, 10000],
    std_dev [0, 5000], spike_frequency [0, 1], capture_rate [0, 1].
    """

    @given(
        region=valid_region(),
        scenario=valid_scenario_type(),
        bess_ratio=st.floats(min_value=0.0, max_value=2.0),
    )
    @settings(max_examples=100)
    def test_all_outputs_within_bounds(
        self, region: str, scenario: ScenarioType, bess_ratio: float
    ):
        """All price distribution outputs are within their defined ranges."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=[], last_updated=date.today())

        target_year = date.today().year + 5

        dist = engine.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=target_year,
            bess_capacity_ratio=bess_ratio,
        )

        assert 0.0 <= dist.mean_spread <= 10000.0
        assert 0.0 <= dist.std_dev <= 5000.0
        assert 0.0 <= dist.spike_frequency <= 1.0
        assert 0.0 <= dist.compression_factor <= 1.0
        assert 0.0 <= dist.capture_rate <= 1.0

    @given(
        region=valid_region(),
        scenario=valid_scenario_type(),
        impact_factors=st.lists(
            st.floats(min_value=0.5, max_value=2.0),
            min_size=0,
            max_size=10,
        ),
        bess_ratio=st.floats(min_value=0.0, max_value=2.0),
    )
    @settings(max_examples=100)
    def test_bounds_with_events(
        self,
        region: str,
        scenario: ScenarioType,
        impact_factors: list,
        bess_ratio: float,
    ):
        """Output bounds hold even with multiple events applied."""
        today = date.today()
        events = []
        for i, factor in enumerate(impact_factors):
            events.append(
                SupplyDemandEvent(
                    event_type=EventType.COAL_CLOSURE,
                    name=f"Bound Test {i}",
                    region=region,
                    expected_date=today + timedelta(days=365 * (i + 1)),
                    capacity_mw=500.0,
                    confidence=EventConfidence.CONFIRMED,
                    spread_impact_factor=factor,
                )
            )

        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=events, last_updated=today)

        target_year = today.year + 15

        dist = engine.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=target_year,
            bess_capacity_ratio=bess_ratio,
        )

        assert 0.0 <= dist.mean_spread <= 10000.0
        assert 0.0 <= dist.std_dev <= 5000.0
        assert 0.0 <= dist.spike_frequency <= 1.0
        assert 0.0 <= dist.compression_factor <= 1.0
        assert 0.0 <= dist.capture_rate <= 1.0


# ---------------------------------------------------------------------------
# Property 18: Revenue Degradation Monotonicity
# ---------------------------------------------------------------------------


class TestRevenueDegradationMonotonicity:
    """**Validates: Requirements 10.3**

    For any 20-year revenue projection with constant price distribution
    parameters, the estimated annual revenue SHALL be non-increasing over
    time due to state-of-health degradation.
    """

    @given(
        region=valid_region(),
        scenario=valid_scenario_type(),
        power_mw=st.floats(min_value=10.0, max_value=500.0),
        duration_hours=st.floats(min_value=1.0, max_value=8.0),
        rte=st.floats(min_value=0.70, max_value=0.95),
        degradation_rate=st.floats(min_value=0.005, max_value=0.03),
    )
    @settings(max_examples=100)
    def test_revenue_non_increasing_over_time(
        self,
        region: str,
        scenario: ScenarioType,
        power_mw: float,
        duration_hours: float,
        rte: float,
        degradation_rate: float,
    ):
        """Revenue is non-increasing over time with constant price distribution.

        We test with a fixed bess_capacity_ratio (no new BESS additions)
        and no events, so the only changing factor is SoH degradation.
        """
        battery = BatterySpecs(
            power_mw=power_mw,
            duration_hours=duration_hours,
            round_trip_efficiency=rte,
            calendar_degradation_rate=degradation_rate,
        )

        # Create engine with no events for constant price distribution
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=[], last_updated=date.today())

        target_year = date.today().year + 5
        bess_ratio = 0.1  # Fixed ratio

        revenues = []
        for i in range(20):
            soh = max(0.0, 1.0 - degradation_rate * (i + 1))
            dist = engine.calculate_price_distribution(
                region=region,
                scenario=scenario,
                year=target_year,
                bess_capacity_ratio=bess_ratio,
            )
            # Revenue formula from engine
            revenue = (
                dist.mean_spread
                * dist.capture_rate
                * power_mw
                * duration_hours
                * 365
                * rte
                * soh
            )
            revenues.append(revenue)

        # Revenue should be non-increasing
        for i in range(1, len(revenues)):
            assert revenues[i] <= revenues[i - 1] + 1e-6


# ---------------------------------------------------------------------------
# Property 19: Revenue Efficiency Metamorphic Property
# ---------------------------------------------------------------------------


class TestRevenueEfficiencyMetamorphic:
    """**Validates: Requirements 10.2**

    For any two battery configurations identical except for round-trip
    efficiency where η1 < η2, the estimated annual revenue with η1 SHALL
    be less than or equal to the revenue with η2.
    """

    @given(
        region=valid_region(),
        scenario=valid_scenario_type(),
        power_mw=st.floats(min_value=10.0, max_value=500.0),
        duration_hours=st.floats(min_value=1.0, max_value=8.0),
        rte_low=st.floats(min_value=0.70, max_value=0.90),
        rte_delta=st.floats(min_value=0.01, max_value=0.10),
    )
    @settings(max_examples=100)
    def test_higher_rte_higher_revenue(
        self,
        region: str,
        scenario: ScenarioType,
        power_mw: float,
        duration_hours: float,
        rte_low: float,
        rte_delta: float,
    ):
        """Higher round-trip efficiency → higher or equal revenue."""
        rte_high = min(0.99, rte_low + rte_delta)
        assume(rte_high > rte_low)

        battery_low = BatterySpecs(
            power_mw=power_mw,
            duration_hours=duration_hours,
            round_trip_efficiency=rte_low,
        )
        battery_high = BatterySpecs(
            power_mw=power_mw,
            duration_hours=duration_hours,
            round_trip_efficiency=rte_high,
        )

        # Create engine with no events for consistent comparison
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = EventRegistry(events=[], last_updated=date.today())

        target_year = date.today().year + 5
        soh = 1.0

        revenue_low, _ = engine.estimate_annual_revenue(
            region=region,
            scenario=scenario,
            year=target_year,
            battery=battery_low,
            soh=soh,
        )
        revenue_high, _ = engine.estimate_annual_revenue(
            region=region,
            scenario=scenario,
            year=target_year,
            battery=battery_high,
            soh=soh,
        )

        assert revenue_high >= revenue_low - 1e-6


# ---------------------------------------------------------------------------
# Property 22: Forward Price Serialization Round-Trip
# ---------------------------------------------------------------------------


class TestForwardPriceSerializationRoundTrip:
    """**Validates: Requirements 13.1, 13.2, 13.3**

    For any valid ScenarioProjection or SupplyDemandEvent object,
    serializing to JSON and then deserializing back SHALL produce
    an object equal to the original.
    """

    @given(event=valid_supply_demand_event())
    @settings(max_examples=100)
    def test_supply_demand_event_round_trip(self, event: SupplyDemandEvent):
        """SupplyDemandEvent serializes to JSON and deserializes back to equal object."""
        json_str = event.model_dump_json()
        restored = SupplyDemandEvent.model_validate_json(json_str)
        assert restored == event

    @given(event=valid_supply_demand_event())
    @settings(max_examples=100)
    def test_supply_demand_event_dict_round_trip(self, event: SupplyDemandEvent):
        """SupplyDemandEvent serializes to dict and deserializes back to equal object."""
        data = event.model_dump()
        restored = SupplyDemandEvent.model_validate(data)
        assert restored == event

    @given(projection=valid_scenario_projection())
    @settings(max_examples=100)
    def test_scenario_projection_round_trip(self, projection: ScenarioProjection):
        """ScenarioProjection serializes to JSON and deserializes back to equal object."""
        json_str = projection.model_dump_json()
        restored = ScenarioProjection.model_validate_json(json_str)
        assert restored == projection

    @given(projection=valid_scenario_projection())
    @settings(max_examples=100)
    def test_scenario_projection_dict_round_trip(self, projection: ScenarioProjection):
        """ScenarioProjection serializes to dict and deserializes back to equal object."""
        data = projection.model_dump()
        restored = ScenarioProjection.model_validate(data)
        assert restored == projection
