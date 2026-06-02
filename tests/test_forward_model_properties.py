"""Property-based tests for Forward Model Accuracy Upgrade.

Feature: forward-model-accuracy-upgrade, Property 2: Capture Rate 公式正确性
Feature: forward-model-accuracy-upgrade, Property 3: Capture Rate 子函数单调递减
Feature: forward-model-accuracy-upgrade, Property 4: Capture Rate 边界约束
Feature: forward-model-accuracy-upgrade, Property 5: ML 样本权重时间衰减
Feature: forward-model-accuracy-upgrade, Property 6: 渗透率区间分类正确性
Feature: forward-model-accuracy-upgrade, Property 7: 管道实现率加权容量
Feature: forward-model-accuracy-upgrade, Property 9: 动态峰值需求公式与下界
Feature: forward-model-accuracy-upgrade, Property 10: 煤电退役日期情景调整
Feature: forward-model-accuracy-upgrade, Property 11: 调整后事件日期不早于今天
Feature: forward-model-accuracy-upgrade, Property 12: Duration 效率因子公式
Feature: forward-model-accuracy-upgrade, Property 13: Duration 效率因子单调递增
Feature: forward-model-accuracy-upgrade, Property 14: 结构性风险条件包含
Feature: forward-model-accuracy-upgrade, Property 15: 分位数排序不变量
Feature: forward-model-accuracy-upgrade, Property 16: 最小分位数区间宽度
Feature: forward-model-accuracy-upgrade, Property 17: Pinball Loss 公式正确性
Feature: forward-model-accuracy-upgrade, Property 18: 日内价差特征计算

Uses Hypothesis to verify mathematical invariants across randomized inputs.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import math
from datetime import date, datetime, timedelta
from unittest import mock

import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from engines import forward_price_engine as fpe_module
from engines.forward_price_engine import (
    BASE_CAPTURE_RATE,
    COAL_RETIREMENT_SCENARIO_ADJUSTMENT,
    DEMAND_GROWTH_BASE_YEAR,
    DEMAND_GROWTH_RATE,
    ForwardPriceEngine,
    PEAK_DEMAND,
    PIPELINE_REALIZATION_RATES,
    SUPPORTED_REGIONS,
)
from models.forward_price_models import (
    EventConfidence,
    EventType,
    ScenarioType,
    SupplyDemandEvent,
)


# ---------------------------------------------------------------------------
# Helper: create engine instances without DB (pure math methods)
# ---------------------------------------------------------------------------

def _make_forward_engine() -> ForwardPriceEngine:
    """Create a ForwardPriceEngine instance bypassing __init__ (no DB needed)."""
    engine = object.__new__(ForwardPriceEngine)
    engine._calibrated_spreads = {}
    engine._calibration = {"status": "skipped"}
    # Minimal event registry for methods that don't need it
    from models.forward_price_models import EventRegistry
    engine.event_registry = EventRegistry(events=[], last_updated=date.today())
    return engine


def _make_ml_engine():
    """Create an MLCalibrationEngine instance with mocked DB."""
    from engines.ml_calibration_engine import MLCalibrationEngine
    db_mock = mock.MagicMock()
    engine = object.__new__(MLCalibrationEngine)
    engine.db = db_mock
    engine.model = None
    engine.model_p10 = None
    engine.model_p90 = None
    engine.calibration_metadata = {}
    engine.calibrated_params = {}
    return engine


# ===========================================================================
# Task 2.3 — Capture Rate 属性测试
# ===========================================================================

class TestCaptureRateProperties:
    """Feature: forward-model-accuracy-upgrade, Property 2/3/4: Capture Rate."""


    @given(
        compression=st.floats(min_value=0.05, max_value=1.0),
        year=st.integers(min_value=2025, max_value=2050),
        bess_ratio=st.floats(min_value=0.0, max_value=1.0),
        fleet_size=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_property_2_capture_rate_formula_correctness(
        self, compression, year, bess_ratio, fleet_size
    ):
        """Feature: forward-model-accuracy-upgrade, Property 2: Capture Rate 公式正确性

        Verify output equals 0.55 × compression^0.5 × autobidder_decay(year)
        × fleet_size_factor(fleet_size) clamped to [0.10, 0.55],
        with additional cap at 0.40 when bess_capacity_ratio > 0.30.

        **Validates: Requirements 2.1, 2.2**
        """
        engine = _make_forward_engine()

        result = engine._compute_capture_rate(compression, year, bess_ratio, fleet_size)

        # Compute expected value manually
        autobidder = engine._autobidder_decay(year)
        fleet_factor = engine._fleet_size_factor(fleet_size)
        raw = BASE_CAPTURE_RATE * (compression ** 0.5) * autobidder * fleet_factor

        expected = max(0.10, min(0.55, raw))
        if bess_ratio > 0.30:
            expected = min(expected, 0.40)

        assert abs(result - expected) < 1e-10, (
            f"capture_rate mismatch: got {result}, expected {expected}"
        )

    @given(
        year1=st.integers(min_value=2025, max_value=2050),
        year2=st.integers(min_value=2025, max_value=2050),
    )
    @settings(max_examples=100)
    def test_property_3_subfunctions_monotone_decreasing(self, year1, year2):
        """Feature: forward-model-accuracy-upgrade, Property 3: Capture Rate 子函数单调递减

        autobidder_decay(year1) >= autobidder_decay(year2) for year1 < year2.
        fleet_size_factor(fs1) >= fleet_size_factor(fs2) for fs1 < fs2.

        **Validates: Requirements 2.3, 2.5**
        """
        assume(year1 < year2)
        engine = _make_forward_engine()

        decay1 = engine._autobidder_decay(year1)
        decay2 = engine._autobidder_decay(year2)
        assert decay1 >= decay2, (
            f"autobidder_decay not monotone decreasing: "
            f"decay({year1})={decay1} < decay({year2})={decay2}"
        )
        # Range check [0.7, 1.0]
        assert 0.7 <= decay1 <= 1.0
        assert 0.7 <= decay2 <= 1.0

    @given(
        fs1=st.integers(min_value=0, max_value=200),
        fs2=st.integers(min_value=0, max_value=200),
    )
    @settings(max_examples=100)
    def test_property_3_fleet_size_factor_monotone_decreasing(self, fs1, fs2):
        """Feature: forward-model-accuracy-upgrade, Property 3: fleet_size_factor 单调递减

        fleet_size_factor(fs1) >= fleet_size_factor(fs2) for fs1 < fs2.

        **Validates: Requirements 2.3, 2.5**
        """
        assume(fs1 < fs2)
        engine = _make_forward_engine()

        factor1 = engine._fleet_size_factor(fs1)
        factor2 = engine._fleet_size_factor(fs2)
        assert factor1 >= factor2, (
            f"fleet_size_factor not monotone decreasing: "
            f"factor({fs1})={factor1} < factor({fs2})={factor2}"
        )

    @given(
        compression=st.floats(min_value=0.05, max_value=1.0),
        year=st.integers(min_value=2025, max_value=2050),
        bess_ratio=st.floats(min_value=0.0, max_value=1.0),
        fleet_size=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_property_4_capture_rate_boundary_constraints(
        self, compression, year, bess_ratio, fleet_size
    ):
        """Feature: forward-model-accuracy-upgrade, Property 4: Capture Rate 边界约束

        capture_rate ∈ [0.10, 0.55], and ≤ 0.40 when bess_capacity_ratio > 0.30.

        **Validates: Requirements 2.4, 2.6**
        """
        engine = _make_forward_engine()

        result = engine._compute_capture_rate(compression, year, bess_ratio, fleet_size)

        assert 0.10 <= result <= 0.55, (
            f"capture_rate {result} out of bounds [0.10, 0.55]"
        )
        if bess_ratio > 0.30:
            assert result <= 0.40, (
                f"capture_rate {result} > 0.40 when bess_ratio={bess_ratio} > 0.30"
            )


# ===========================================================================
# Task 3.2 — Duration 效率因子属性测试
# ===========================================================================

class TestDurationEfficiencyProperties:
    """Feature: forward-model-accuracy-upgrade, Property 12/13: Duration 效率因子."""

    @given(duration=st.floats(min_value=0.5, max_value=24.0))
    @settings(max_examples=100)
    def test_property_12_duration_efficiency_formula(self, duration):
        """Feature: forward-model-accuracy-upgrade, Property 12: Duration 效率因子公式

        duration ≤ 12: factor = duration^0.85
        duration > 12: factor = 12^0.85 × (duration/12)^0.75

        **Validates: Requirements 7.1, 7.2, 7.5**
        """
        engine = _make_forward_engine()

        result = engine._compute_duration_efficiency(duration)

        if duration <= 12.0:
            expected = duration ** 0.85
        else:
            expected = (12.0 ** 0.85) * ((duration / 12.0) ** 0.75)

        assert abs(result - expected) < 1e-10, (
            f"duration_efficiency mismatch for duration={duration}: "
            f"got {result}, expected {expected}"
        )

    @given(
        d1=st.floats(min_value=0.5, max_value=24.0),
        d2=st.floats(min_value=0.5, max_value=24.0),
    )
    @settings(max_examples=100)
    def test_property_13_duration_efficiency_monotone_increasing(self, d1, d2):
        """Feature: forward-model-accuracy-upgrade, Property 13: Duration 效率因子单调递增

        duration1 < duration2 → factor1 < factor2.

        **Validates: Requirements 7.3**
        """
        assume(d1 < d2)
        engine = _make_forward_engine()

        factor1 = engine._compute_duration_efficiency(d1)
        factor2 = engine._compute_duration_efficiency(d2)

        assert factor1 < factor2, (
            f"duration_efficiency not monotone increasing: "
            f"f({d1})={factor1} >= f({d2})={factor2}"
        )


# ===========================================================================
# Task 4.3 — 管道实现率属性测试
# ===========================================================================

class TestPipelineRealizationProperties:
    """Feature: forward-model-accuracy-upgrade, Property 7: 管道实现率加权容量."""

    @given(
        capacity=st.floats(min_value=1.0, max_value=1000.0),
        status=st.sampled_from(
            ["registered", "construction", "committed", "proposed", "speculated", "unknown_status"]
        ),
    )
    @settings(max_examples=100)
    def test_property_7_pipeline_realization_weighted_capacity(self, capacity, status):
        """Feature: forward-model-accuracy-upgrade, Property 7: 管道实现率加权容量

        weighted = capacity × realization_rate(status)
        registered/construction/committed → 0.90, proposed → 0.50,
        speculated → 0.20, unknown → 0.20.

        **Validates: Requirements 4.1, 4.3, 4.5**
        """
        engine = _make_forward_engine()

        result = engine._apply_pipeline_realization(capacity, status)

        # Determine expected rate
        expected_rates = {
            "registered": 1.00,
            "construction": 0.95,
            "committed": 0.90,
            "proposed": 0.50,
            "speculated": 0.20,
        }
        expected_rate = expected_rates.get(status, 0.20)
        expected = capacity * expected_rate

        assert abs(result - expected) < 1e-10, (
            f"pipeline realization mismatch for status='{status}', capacity={capacity}: "
            f"got {result}, expected {expected}"
        )


# ===========================================================================
# Task 5.3 — 动态需求和煤电退役属性测试
# ===========================================================================

class TestDynamicDemandAndCoalRetirementProperties:
    """Feature: forward-model-accuracy-upgrade, Property 9/10/11."""

    @given(
        region=st.sampled_from(list(PEAK_DEMAND.keys())),
        year=st.integers(min_value=2025, max_value=2050),
        growth_rate=st.floats(min_value=0.0, max_value=0.10),
    )
    @settings(max_examples=100)
    def test_property_9_dynamic_peak_demand_formula_and_lower_bound(
        self, region, year, growth_rate
    ):
        """Feature: forward-model-accuracy-upgrade, Property 9: 动态峰值需求公式与下界

        peak_demand = base × (1+rate)^(year-2025), ≥ static PEAK_DEMAND value.

        **Validates: Requirements 5.1, 5.3**
        """
        engine = _make_forward_engine()

        result = engine._get_dynamic_peak_demand(region, year, growth_rate)

        base = PEAK_DEMAND[region]
        expected_dynamic = base * ((1.0 + growth_rate) ** (year - DEMAND_GROWTH_BASE_YEAR))
        expected = max(base, expected_dynamic)

        assert abs(result - expected) < 1e-6, (
            f"dynamic peak demand mismatch for region={region}, year={year}, "
            f"rate={growth_rate}: got {result}, expected {expected}"
        )
        # Lower bound: never below static PEAK_DEMAND
        assert result >= base, (
            f"dynamic peak demand {result} < static {base} for {region}"
        )

    @given(
        base_year=st.integers(min_value=2026, max_value=2040),
    )
    @settings(max_examples=100)
    def test_property_10_coal_retirement_scenario_adjustment(self, base_year):
        """Feature: forward-model-accuracy-upgrade, Property 10: 煤电退役日期情景调整

        Central +2yr, High -2yr, Low +4yr.

        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        engine = _make_forward_engine()

        # Create a coal closure event with a future date
        base_date = date(base_year, 6, 15)
        event = SupplyDemandEvent(
            event_type=EventType.COAL_CLOSURE,
            name="Test Coal Plant",
            region="NSW1",
            expected_date=base_date,
            capacity_mw=500.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=1.1,
        )

        # Central: +2 years
        central_date = engine._get_effective_event_date(event, ScenarioType.CENTRAL)
        expected_central = base_date.replace(year=base_date.year + 2)
        today = date.today()
        if expected_central < today:
            expected_central = today
        assert central_date == expected_central, (
            f"Central adjustment: got {central_date}, expected {expected_central}"
        )

        # High: -2 years
        high_date = engine._get_effective_event_date(event, ScenarioType.HIGH)
        expected_high = base_date.replace(year=base_date.year - 2)
        if expected_high < today:
            expected_high = today
        assert high_date == expected_high, (
            f"High adjustment: got {high_date}, expected {expected_high}"
        )

        # Low: +4 years
        low_date = engine._get_effective_event_date(event, ScenarioType.LOW)
        expected_low = base_date.replace(year=base_date.year + 4)
        if expected_low < today:
            expected_low = today
        assert low_date == expected_low, (
            f"Low adjustment: got {low_date}, expected {expected_low}"
        )

    @given(
        base_year=st.integers(min_value=2025, max_value=2050),
        base_month=st.integers(min_value=1, max_value=12),
        base_day=st.integers(min_value=1, max_value=28),
        scenario=st.sampled_from(list(ScenarioType)),
    )
    @settings(max_examples=100)
    def test_property_11_adjusted_date_not_before_today(
        self, base_year, base_month, base_day, scenario
    ):
        """Feature: forward-model-accuracy-upgrade, Property 11: 调整后事件日期不早于今天

        For any event and scenario, _get_effective_event_date returns a date
        not earlier than today.

        **Validates: Requirements 6.4**
        """
        engine = _make_forward_engine()

        base_date = date(base_year, base_month, base_day)
        event = SupplyDemandEvent(
            event_type=EventType.COAL_CLOSURE,
            name="Test Coal Plant",
            region="NSW1",
            expected_date=base_date,
            capacity_mw=500.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=1.1,
        )

        result = engine._get_effective_event_date(event, scenario)
        today = date.today()

        assert result >= today, (
            f"Adjusted date {result} is before today {today} "
            f"(base={base_date}, scenario={scenario})"
        )


# ===========================================================================
# Task 8.3 — 结构性风险属性测试
# ===========================================================================

class TestStructuralRiskProperties:
    """Feature: forward-model-accuracy-upgrade, Property 14: 结构性风险条件包含."""

    @given(year=st.integers(min_value=2025, max_value=2060))
    @settings(max_examples=100)
    def test_property_14_structural_risk_conditional_inclusion(self, year):
        """Feature: forward-model-accuracy-upgrade, Property 14: 结构性风险条件包含

        year > 2028 → contains Nelson Review risk.
        year ≤ 2028 → empty list.

        **Validates: Requirements 8.2, 8.4**
        """
        engine = _make_forward_engine()

        result = engine._compute_structural_risks(year)

        # Always returns a list (never None)
        assert isinstance(result, list)

        if year > 2028:
            assert len(result) > 0, (
                f"Expected Nelson Review risk for year={year}, got empty list"
            )
            # Check that at least one entry mentions Nelson Review
            has_nelson = any("Nelson Review" in r for r in result)
            assert has_nelson, (
                f"Expected 'Nelson Review' in risks for year={year}, got {result}"
            )
        else:
            assert len(result) == 0, (
                f"Expected empty risk list for year={year}, got {result}"
            )


# ===========================================================================
# Task 9.5 — ML Concept Drift 属性测试
# ===========================================================================

class TestMLConceptDriftProperties:
    """Feature: forward-model-accuracy-upgrade, Property 5/6: ML 样本权重与渗透率分类."""

    @given(
        months_ago=st.floats(min_value=0.0, max_value=60.0),
    )
    @settings(max_examples=100)
    def test_property_5_sample_weight_time_decay(self, months_ago):
        """Feature: forward-model-accuracy-upgrade, Property 5: ML 样本权重时间衰减

        ≤12mo → 1.0, 12-24mo → 0.5, >24mo → 0.2.

        **Validates: Requirements 3.1**
        """
        ml_engine = _make_ml_engine()

        # Create a record with a date that is `months_ago` months in the past
        days_ago = int(months_ago * 30.44)
        record_date = datetime.now() - timedelta(days=days_ago)
        record = {"trade_date": record_date.strftime("%Y-%m-%d")}

        weights = ml_engine._compute_sample_weights([record])
        weight = weights[0]

        # 引擎用 days_diff / 30.44 计算 months_diff(浮点),边界判定基于该值
        # 测试这里用 int(months_ago * 30.44) 截断到天再算回月,会和原始 months_ago
        # 在边界(12.0/24.0 附近)产生分歧。改用引擎相同的 actual 月数判断。
        actual_months = days_ago / 30.44

        if actual_months <= 12:
            assert weight == 1.0, (
                f"Expected weight=1.0 for actual={actual_months:.4f}mo (input={months_ago:.4f}), got {weight}"
            )
        elif actual_months <= 24:
            assert weight == 0.5, (
                f"Expected weight=0.5 for actual={actual_months:.4f}mo (input={months_ago:.4f}), got {weight}"
            )
        else:
            assert weight == 0.2, (
                f"Expected weight=0.2 for actual={actual_months:.4f}mo (input={months_ago:.4f}), got {weight}"
            )

    @given(bess_ratio=st.floats(min_value=0.0, max_value=0.5))
    @settings(max_examples=100)
    def test_property_6_regime_indicator_classification(self, bess_ratio):
        """Feature: forward-model-accuracy-upgrade, Property 6: 渗透率区间分类正确性

        <0.05 → "low", 0.05-0.15 → "medium", >0.15 → "high".

        **Validates: Requirements 3.4**
        """
        ml_engine = _make_ml_engine()

        result = ml_engine._compute_regime_indicator(bess_ratio)

        if bess_ratio < 0.05:
            assert result == "low", (
                f"Expected 'low' for ratio={bess_ratio}, got '{result}'"
            )
        elif bess_ratio <= 0.15:
            assert result == "medium", (
                f"Expected 'medium' for ratio={bess_ratio}, got '{result}'"
            )
        else:
            assert result == "high", (
                f"Expected 'high' for ratio={bess_ratio}, got '{result}'"
            )


# ===========================================================================
# Task 10.3 — Quantile Regression 属性测试
# ===========================================================================

class TestQuantileRegressionProperties:
    """Feature: forward-model-accuracy-upgrade, Property 15/16/17: Quantile Regression."""

    @given(
        data=st.lists(
            st.tuples(
                st.floats(min_value=-100.0, max_value=500.0),
                st.floats(min_value=-100.0, max_value=500.0),
                st.floats(min_value=-100.0, max_value=500.0),
            ),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=100)
    def test_property_15_quantile_ordering_invariant(self, data):
        """Feature: forward-model-accuracy-upgrade, Property 15: 分位数排序不变量

        P10 ≤ P50 ≤ P90 after isotonic regression for all samples.

        **Validates: Requirements 9.1, 9.2**
        """
        ml_engine = _make_ml_engine()

        p10_raw = np.array([d[0] for d in data])
        p50_raw = np.array([d[1] for d in data])
        p90_raw = np.array([d[2] for d in data])

        p10, p50, p90 = ml_engine._apply_isotonic_regression(p10_raw, p50_raw, p90_raw)

        for i in range(len(data)):
            assert p10[i] <= p50[i], (
                f"P10[{i}]={p10[i]} > P50[{i}]={p50[i]} after isotonic regression"
            )
            assert p50[i] <= p90[i], (
                f"P50[{i}]={p50[i]} > P90[{i}]={p90[i]} after isotonic regression"
            )

    @given(
        data=st.lists(
            st.tuples(
                st.floats(min_value=-100.0, max_value=500.0),
                st.floats(min_value=-100.0, max_value=500.0),
                st.floats(min_value=-100.0, max_value=500.0),
            ),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=100)
    def test_property_16_minimum_quantile_interval_width(self, data):
        """Feature: forward-model-accuracy-upgrade, Property 16: 最小分位数区间宽度

        P90 - P10 ≥ 20 AUD/MWh after isotonic regression.

        **Validates: Requirements 9.5**
        """
        ml_engine = _make_ml_engine()

        p10_raw = np.array([d[0] for d in data])
        p50_raw = np.array([d[1] for d in data])
        p90_raw = np.array([d[2] for d in data])

        p10, p50, p90 = ml_engine._apply_isotonic_regression(p10_raw, p50_raw, p90_raw)

        for i in range(len(data)):
            width = p90[i] - p10[i]
            assert width >= 20.0 - 1e-10, (
                f"Quantile interval width {width} < 20 at index {i} "
                f"(P10={p10[i]}, P90={p90[i]})"
            )

    @given(
        y_true=st.floats(min_value=-100.0, max_value=500.0),
        y_pred=st.floats(min_value=-100.0, max_value=500.0),
        alpha=st.floats(min_value=0.01, max_value=0.99),
    )
    @settings(max_examples=100)
    def test_property_17_pinball_loss_formula_correctness(self, y_true, y_pred, alpha):
        """Feature: forward-model-accuracy-upgrade, Property 17: Pinball Loss 公式正确性

        pinball = α × max(y-q, 0) + (1-α) × max(q-y, 0).

        **Validates: Requirements 9.4**
        """
        ml_engine = _make_ml_engine()

        # Compute using the engine method (arrays of size 1)
        result = ml_engine._compute_pinball_loss(
            np.array([y_true]), np.array([y_pred]), alpha
        )

        # Compute expected manually
        residual = y_true - y_pred
        expected = alpha * max(residual, 0.0) + (1.0 - alpha) * max(-residual, 0.0)

        assert abs(result - expected) < 1e-10, (
            f"Pinball loss mismatch: got {result}, expected {expected} "
            f"(y_true={y_true}, y_pred={y_pred}, alpha={alpha})"
        )


# ===========================================================================
# Task 11.3 — 日内特征属性测试
# ===========================================================================

class TestIntradayFeatureProperties:
    """Feature: forward-model-accuracy-upgrade, Property 18: 日内价差特征计算."""

    @given(
        prices=st.lists(
            st.floats(min_value=-100.0, max_value=500.0),
            min_size=48,
            max_size=48,
        )
    )
    @settings(max_examples=100)
    def test_property_18_intraday_spread_feature_calculation(self, prices):
        """Feature: forward-model-accuracy-upgrade, Property 18: 日内价差特征计算

        evening_solar_spread = avg(intervals 34:42) - avg(intervals 20:28)
        morning_ramp_spread = avg(intervals 12:18) - avg(intervals 0:10)

        **Validates: Requirements 10.1, 10.2**
        """
        ml_engine = _make_ml_engine()

        result = ml_engine._compute_intraday_features(prices)

        # Verify not marked as incomplete
        assert result["incomplete_intraday"] is False

        # evening_solar_spread: avg(17:00-21:00) - avg(10:00-14:00)
        evening_prices = prices[34:42]   # intervals 34-41
        solar_prices = prices[20:28]     # intervals 20-27
        expected_evening = float(np.mean(evening_prices) - np.mean(solar_prices))

        assert abs(result["evening_solar_spread"] - expected_evening) < 1e-10, (
            f"evening_solar_spread mismatch: got {result['evening_solar_spread']}, "
            f"expected {expected_evening}"
        )

        # morning_ramp_spread: avg(06:00-09:00) - avg(00:00-05:00)
        morning_prices = prices[12:18]   # intervals 12-17
        overnight_prices = prices[0:10]  # intervals 0-9
        expected_morning = float(np.mean(morning_prices) - np.mean(overnight_prices))

        assert abs(result["morning_ramp_spread"] - expected_morning) < 1e-10, (
            f"morning_ramp_spread mismatch: got {result['morning_ramp_spread']}, "
            f"expected {expected_morning}"
        )


# ===========================================================================
# qld-rvf-correction Task 5 — Compression 因子相对 RVF 的属性测试
# ===========================================================================

class TestCompressionFactorProperties:
    """Feature: qld-rvf-correction, Property A/B: Compression Factor 相对 RVF 的不变量。

    这两条属性测试是 qld-rvf-correction spec 的 Req 4 要求,目的是把
    `_compute_compression_factor` 的两条代数性质固化为机器可验证的约束:

    - Property A: RVF 单调性(RVF↑ → compression↑,因为 RVF 在 exp 分母里)
    - Property B: compression 始终在 [0.05, 1.0](实现内部 clamp)
    """

    @given(
        rvf_a=st.floats(
            min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False
        ),
        rvf_b=st.floats(
            min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False
        ),
        ratio=st.floats(min_value=0.0, max_value=1.0),
        sensitivity=st.floats(min_value=0.5, max_value=3.0),
        psf=st.floats(min_value=0.0, max_value=0.7),
    )
    @settings(max_examples=100)
    def test_property_a_compression_monotone_in_rvf(
        self, rvf_a, rvf_b, ratio, sensitivity, psf
    ):
        """Feature: qld-rvf-correction, Property A: Compression monotonicity in RVF

        固定 (ratio, sensitivity, psf),对任意 RVF_lo ≤ RVF_hi,有
        compression(RVF_lo) ≤ compression(RVF_hi)(浮点容差 1e-9)。

        数学:compression = clamp(exp(-k·X / RVF), 0.05, 1.0),其中 X = ratio·sens
        + w·psf ≥ 0;d/dRVF[exp(-k·X/RVF)] = (k·X/RVF²)·exp(-k·X/RVF) ≥ 0,故
        compression 在 RVF 上单调不降。

        **Validates: Requirements 4.1, 4.3**
        """
        lo, hi = (rvf_a, rvf_b) if rvf_a <= rvf_b else (rvf_b, rvf_a)
        engine = _make_forward_engine()

        c_lo = engine._compute_compression_factor(ratio, sensitivity, psf, lo)
        c_hi = engine._compute_compression_factor(ratio, sensitivity, psf, hi)

        assert c_lo <= c_hi + 1e-9, (
            f"compression not monotone in RVF: "
            f"compression(RVF={lo})={c_lo} > compression(RVF={hi})={c_hi} "
            f"(ratio={ratio}, sensitivity={sensitivity}, psf={psf})"
        )

    @given(
        rvf=st.floats(
            min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False
        ),
        ratio=st.floats(min_value=0.0, max_value=1.0),
        sensitivity=st.floats(min_value=0.5, max_value=3.0),
        psf=st.floats(min_value=0.0, max_value=0.7),
    )
    @settings(max_examples=100)
    def test_property_b_compression_bounded(self, rvf, ratio, sensitivity, psf):
        """Feature: qld-rvf-correction, Property B: Compression bounded in [0.05, 1.0]

        实现内部 clamp 把下界提升到 0.05、上界为 1.0,故 compression 始终在
        闭区间 [0.05, 1.0] 内,无论输入如何。

        **Validates: Requirements 4.2, 4.3**
        """
        engine = _make_forward_engine()
        c = engine._compute_compression_factor(ratio, sensitivity, psf, rvf)

        assert 0.05 <= c <= 1.0, (
            f"compression {c} out of [0.05, 1.0] "
            f"(ratio={ratio}, sensitivity={sensitivity}, psf={psf}, rvf={rvf})"
        )


# ===========================================================================
# seasonal-capture-rate-correction Task 7 — Zero_Season_Mode 等价性 + 边界 PBT
# ===========================================================================


@pytest.fixture
def zero_season_mode(monkeypatch):
    """把 ``SEASONAL_CAPTURE_MULTIPLIER`` 全部置为 1.0,并同步刷新 ``_ZERO_SEASON_MODE`` 缓存。

    Property 20 需要在运行期把字典改为全 1.0 进入 Zero_Season_Mode。``_compute_capture_rate``
    内部读取模块级 ``_ZERO_SEASON_MODE`` 标志而非每次重新遍历字典,因此本 fixture 必须
    **同时** monkeypatch 字典 **与** ``_ZERO_SEASON_MODE`` — 只改字典不改标志会让短路路径失效,
    数值上仍等价但不走设计中规定的 Zero_Season_Mode 优化路径。

    使用 ``monkeypatch`` 而非直接赋值,确保测试结束自动恢复(避免污染其他用例)。
    """
    zeroed_table = {
        region: {"summer": 1.0, "shoulder": 1.0, "winter": 1.0}
        for region in fpe_module.SEASONAL_CAPTURE_MULTIPLIER.keys()
    }
    monkeypatch.setattr(fpe_module, "SEASONAL_CAPTURE_MULTIPLIER", zeroed_table)
    monkeypatch.setattr(fpe_module, "_ZERO_SEASON_MODE", True)
    yield


class TestSeasonalCaptureProperties:
    """Feature: seasonal-capture-rate-correction, Property 20: Zero_Season_Mode 等价性 + 边界。"""

    @given(
        compression=st.floats(
            min_value=0.05, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        year=st.integers(min_value=2024, max_value=2050),
        bess_ratio=st.floats(
            min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
        fleet_size=st.integers(min_value=0, max_value=50),
        region=st.sampled_from(["NSW1", "QLD1", "VIC1", "SA1"]),
        month=st.integers(min_value=1, max_value=12),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_20_zero_season_mode_equivalence_and_bounds(
        self,
        zero_season_mode,
        compression,
        year,
        bess_ratio,
        fleet_size,
        region,
        month,
    ):
        """Feature: seasonal-capture-rate-correction, Property 20: Zero_Season_Mode 等价性 + 边界

        在 Zero_Season_Mode 激活下,对任意合法输入:
        (a) 等价性:``_compute_capture_rate(..., region, month)`` 与
            ``_compute_capture_rate(...)``(不带 region/month)的返回值绝对差 ≤ 1e-9。
        (b) 边界:两次调用的返回值都满足 ``0.10 <= rate <= 0.55``(包含 high-saturation
            二次 clamp 后仍 ≥ 0.10)。

        本 PBT 仅覆盖**业务代码 ``_compute_capture_rate``** 的 Zero_Season_Mode 行为;
        ``validate_against_benchmarks`` 的 model_revenue 公式(回测特有的 0.65 +
        季节乘子叠层,变体路径 C)不在本 PBT 范围内,由集成回测
        (``run_full_backtest.py`` 16 数据点)端到端验证。

        **Validates: Requirements 7.2, 7.3, 3.5, 4.3, 9.1**
        """
        engine = _make_forward_engine()

        rate_with = engine._compute_capture_rate(
            compression,
            year,
            bess_ratio,
            fleet_size,
            region=region,
            month=month,
        )
        rate_without = engine._compute_capture_rate(
            compression,
            year,
            bess_ratio,
            fleet_size,
        )

        # Property A: Zero_Season_Mode 等价性(Req 7.2 / 3.5)
        assert abs(rate_with - rate_without) <= 1e-9, (
            f"Zero_Season_Mode 不等价: with={rate_with}, without={rate_without} "
            f"(compression={compression}, year={year}, bess_ratio={bess_ratio}, "
            f"fleet_size={fleet_size}, region={region}, month={month})"
        )
        # Property B: 边界 [0.10, 0.55](Req 7.3 / 4.3)
        assert 0.10 <= rate_with <= 0.55, (
            f"rate_with={rate_with} 越界 [0.10, 0.55] "
            f"(compression={compression}, year={year}, bess_ratio={bess_ratio}, "
            f"fleet_size={fleet_size}, region={region}, month={month})"
        )
        assert 0.10 <= rate_without <= 0.55, (
            f"rate_without={rate_without} 越界 [0.10, 0.55] "
            f"(compression={compression}, year={year}, bess_ratio={bess_ratio}, "
            f"fleet_size={fleet_size})"
        )
