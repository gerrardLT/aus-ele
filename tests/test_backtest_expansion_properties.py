"""Property-based tests for Backtest Expansion MVP.

Feature: backtest-expansion-mvp, Property 1: 月度 mean_spread 聚合正确性
Feature: backtest-expansion-mvp, Property 2: 负电价保留不被过滤或截断
Feature: backtest-expansion-mvp, Property 3: 月份枚举范围连续且区域齐全
Feature: backtest-expansion-mvp, Property 4: 数据不足月标记与排除
Feature: backtest-expansion-mvp, Property 5: deviation_pct 计算公式正确性
Feature: backtest-expansion-mvp, Property 6: 聚合指标数学不变量
Feature: backtest-expansion-mvp, Property 7: 完美预见日收入最优性与公式正确性
Feature: backtest-expansion-mvp, Property 8: monthly_capture_rate 公式正确性
Feature: backtest-expansion-mvp, Property 9: capture_rate 封顶有界与标记
Feature: backtest-expansion-mvp, Property 10: 越界判定与 efficiency_ratio
Feature: backtest-expansion-mvp, Property 11: violation_count 与明细一致性
Feature: backtest-expansion-mvp, Property 12: reconciliation 归档 append 不变量

复用项目既有 Hypothesis（与 ``tests/test_forward_model_properties.py`` 一致），针对
``backend/engines/backtest_expansion.py`` 中的纯计算函数验证 12 条 Correctness
Properties 的数学不变量。与既有 20 条 PBT 完全隔离（Req 8.4）。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import copy

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.backtest_expansion import (
    MonthlyBenchmarkCalculator,
    CaptureRateCalculator,
    CaptureRateComparison,
    _deviation_pct,
    _aggregate_deviation_metrics,
    _append_reconciliation_record,
    _HIT_RATE_THRESHOLD_PCT,
)

# ---------------------------------------------------------------------------
# 共享生成器
# ---------------------------------------------------------------------------

# 价格生成器：显式包含负价区间，覆盖 Property 2 与 Req 9.4 的边界（设计要求）。
price_strategy = st.floats(
    min_value=-1000.0, max_value=16000.0, allow_nan=False, allow_infinity=False
)

# 单日聚合行 (day, spread, intervals)；intervals 跨 200 阈值以混合有效 / 无效日。
daily_row_strategy = st.tuples(
    st.text(min_size=1, max_size=10),
    st.floats(min_value=-2000.0, max_value=32000.0, allow_nan=False, allow_infinity=False),
    st.integers(min_value=0, max_value=400),
)

# capture rate 量级浮点（含 >1 以触发封顶、含负以覆盖亏损月）。
capture_rate_strategy = st.floats(
    min_value=-2.0, max_value=3.0, allow_nan=False, allow_infinity=False
)


# ===========================================================================
# Property 1: 月度 mean_spread 聚合正确性 (Task 2.4, Validates 1.1, 1.3)
# ===========================================================================


@settings(max_examples=100)
@given(daily_rows=st.lists(daily_row_strategy, max_size=40))
def test_property_1_monthly_mean_spread_aggregation(daily_rows):
    """Feature: backtest-expansion-mvp, Property 1: 对任意 region-month 的一组逐日
    价格序列，aggregate_monthly_benchmark 返回的 mean_spread_aud_mwh 应等于所有有效日
    （interval >= 200）每日价差 max(rrp)-min(rrp) 的算术平均值。

    Validates: Requirements 1.1, 1.3
    """
    min_intervals = MonthlyBenchmarkCalculator.MIN_INTERVALS_PER_DAY
    valid_spreads = [
        spread for _day, spread, intervals in daily_rows if intervals >= min_intervals
    ]
    expected_mean = sum(valid_spreads) / len(valid_spreads) if valid_spreads else 0.0

    result = MonthlyBenchmarkCalculator.aggregate_monthly_benchmark(
        "NSW1", "2024-01", daily_rows
    )

    assert result.sample_days == len(valid_spreads)
    assert result.mean_spread_aud_mwh == pytest.approx(
        expected_mean, rel=1e-9, abs=1e-9
    )


# ===========================================================================
# Property 2: 负电价保留不被过滤或截断 (Task 2.5, Validates 9.4)
# ===========================================================================


@settings(max_examples=100)
@given(
    other_prices=st.lists(price_strategy, min_size=1, max_size=24),
    neg_price=st.floats(
        min_value=-1000.0, max_value=-0.01, allow_nan=False, allow_infinity=False
    ),
)
def test_property_2_negative_prices_preserved(other_prices, neg_price):
    """Feature: backtest-expansion-mvp, Property 2: 对任意含负电价的每日价格序列，
    该日价差应使用真实 min（含负值）与 max 计算，负价既不剔除也不截断为 0；当某日
    存在负价时其价差严格大于忽略（截断为 0）负价时的价差。

    Validates: Requirements 9.4
    """
    prices = other_prices + [neg_price]
    assume(max(prices) > min(prices))  # 需存在价差变化，否则两种价差均为 0

    # 生成器保证存在负价
    assert min(prices) < 0

    real_spread = max(prices) - min(prices)
    truncated = [p if p > 0 else 0.0 for p in prices]  # 把负价截断为 0
    truncated_spread = max(truncated) - min(truncated)

    # 真实价差（含负价）严格大于把负价截断为 0 后的价差
    assert real_spread > truncated_spread

    # 聚合层不对该价差做任何过滤 / 截断：单个有效日的 mean 即真实价差
    result = MonthlyBenchmarkCalculator.aggregate_monthly_benchmark(
        "NSW1", "2024-01", [("2024-01-01", real_spread, 288)]
    )
    assert result.mean_spread_aud_mwh == pytest.approx(real_spread)


# ===========================================================================
# Property 3: 月份枚举范围连续且区域齐全 (Task 2.6, Validates 1.2, 1.4)
# ===========================================================================


@settings(max_examples=100)
@given(
    end_year=st.integers(min_value=2024, max_value=2035),
    end_month_num=st.integers(min_value=1, max_value=12),
)
def test_property_3_month_enumeration_continuous_and_regions_complete(
    end_year, end_month_num
):
    """Feature: backtest-expansion-mvp, Property 3: 对任意合法截止月 end_month
    (>= 2024-01)，_enumerate_months 枚举的月份应从 2024-01 起连续覆盖到 end_month、
    无遗漏无越界且严格升序，且每月都包含全部五个 NEM 区域（NSW1/QLD1/SA1/TAS1/VIC1）
    而不含 WEM。

    Validates: Requirements 1.2, 1.4
    """
    start = MonthlyBenchmarkCalculator.START_MONTH  # "2024-01"
    end = f"{end_year:04d}-{end_month_num:02d}"

    months = MonthlyBenchmarkCalculator._enumerate_months(start, end)

    # 起止与总数：连续、无遗漏、无越界
    expected_count = (end_year - 2024) * 12 + (end_month_num - 1) + 1
    assert len(months) == expected_count
    assert months[0] == "2024-01"
    assert months[-1] == end

    # 严格升序且逐月连续（无跳月、无重复）
    for i in range(1, len(months)):
        py, pm = int(months[i - 1][:4]), int(months[i - 1][5:7])
        cy, cm = int(months[i][:4]), int(months[i][5:7])
        assert (cy, cm) > (py, pm)
        expected_next = (py + 1, 1) if pm == 12 else (py, pm + 1)
        assert (cy, cm) == expected_next

    # 区域齐全：每月配全部 5 个 NEM 区域且不含 WEM
    regions = MonthlyBenchmarkCalculator.NEM_REGIONS
    assert set(regions) == {"NSW1", "QLD1", "SA1", "TAS1", "VIC1"}
    assert "WEM" not in regions
    for _ym in months:
        assert set(regions) == {"NSW1", "QLD1", "SA1", "TAS1", "VIC1"}
        assert len(regions) == 5


# ===========================================================================
# Property 4: 数据不足月标记与排除 (Task 2.7, Validates 1.5)
# ===========================================================================


@settings(max_examples=100)
@given(
    n_valid=st.integers(min_value=0, max_value=31),
    n_invalid=st.integers(min_value=0, max_value=10),
    valid_intervals=st.integers(min_value=200, max_value=300),
    invalid_intervals=st.integers(min_value=0, max_value=199),
)
def test_property_4_insufficient_data_flag(
    n_valid, n_invalid, valid_intervals, invalid_intervals
):
    """Feature: backtest-expansion-mvp, Property 4: 对任意有效日计数 sample_days，
    当 sample_days < 20 时 data_quality_flag 应为 "insufficient_data"（不进入对比集合）；
    当 sample_days >= 20 时 flag 应为 "ok"（进入对比）。

    Validates: Requirements 1.5
    """
    rows = [(f"v{i}", 100.0, valid_intervals) for i in range(n_valid)]
    rows += [(f"x{i}", 50.0, invalid_intervals) for i in range(n_invalid)]

    result = MonthlyBenchmarkCalculator.aggregate_monthly_benchmark(
        "NSW1", "2024-01", rows
    )

    assert result.sample_days == n_valid
    if n_valid < MonthlyBenchmarkCalculator.MIN_VALID_DAYS:
        assert result.data_quality_flag == "insufficient_data"
    else:
        assert result.data_quality_flag == "ok"


# ===========================================================================
# Property 5: deviation_pct 计算公式正确性 (Task 6.3, Validates 2.3)
# ===========================================================================


@settings(max_examples=100)
@given(
    model=st.floats(
        min_value=-1000.0, max_value=16000.0, allow_nan=False, allow_infinity=False
    ),
    benchmark=st.floats(
        min_value=0.01, max_value=16000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_property_5_deviation_pct_formula(model, benchmark):
    """Feature: backtest-expansion-mvp, Property 5: 对任意模型预测值 model 与非零基准值
    benchmark，deviation_pct 应等于 (model - benchmark) / benchmark × 100，且 model >
    benchmark 时符号为正、model < benchmark 时符号为负。

    Validates: Requirements 2.3
    """
    result = _deviation_pct(model, benchmark)
    expected = (model - benchmark) / benchmark * 100.0
    assert result == pytest.approx(expected, rel=1e-9, abs=1e-9)

    # benchmark > 0，符号由 model 与 benchmark 的大小关系决定
    if model > benchmark:
        assert result > 0
    elif model < benchmark:
        assert result < 0
    else:
        assert result == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# Property 6: 聚合指标数学不变量 (Task 6.4, Validates 2.4)
# ===========================================================================


@settings(max_examples=100)
@given(
    deviations=st.lists(
        st.floats(
            min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False
        ),
        max_size=50,
    )
)
def test_property_6_aggregate_metrics_invariants(deviations):
    """Feature: backtest-expansion-mvp, Property 6: 对任意 deviation 列表，聚合指标应满足
    MAPE = mean(|d|) >= 0、RMSE = sqrt(mean(d²)) >= |Bias|、Bias = mean(d)、
    Hit Rate ∈ [0, 100] 且等于 |d| <= 30 的元素占比百分比。

    Validates: Requirements 2.4
    """
    metrics = _aggregate_deviation_metrics(deviations)

    count = len(deviations)
    expected_bias = sum(deviations) / count if count else 0.0
    expected_mape = sum(abs(d) for d in deviations) / count if count else 0.0
    expected_hits = sum(1 for d in deviations if abs(d) <= _HIT_RATE_THRESHOLD_PCT)
    expected_hit_rate = expected_hits / count * 100.0 if count else 0.0

    # MAPE >= 0
    assert metrics["mape"] >= 0
    assert metrics["mape"] == pytest.approx(expected_mape, rel=1e-9, abs=1e-9)
    # Bias == mean(d)
    assert metrics["bias"] == pytest.approx(expected_bias, rel=1e-9, abs=1e-9)
    # RMSE >= |Bias|（幂平均不等式，留极小浮点容差）
    assert metrics["rmse"] >= abs(metrics["bias"]) - 1e-6
    # Hit Rate ∈ [0, 100] 且等于 |d| <= 30 占比百分比
    assert 0.0 <= metrics["hit_rate"] <= 100.0
    assert metrics["hit_rate"] == pytest.approx(expected_hit_rate, rel=1e-9, abs=1e-9)
    assert metrics["count"] == count


# ===========================================================================
# Property 7: 完美预见日收入最优性与公式正确性 (Task 4.3, Validates 3.1, 3.2)
# ===========================================================================


@settings(max_examples=100)
@given(hourly_prices=st.lists(price_strategy, min_size=8, max_size=24))
def test_property_7_perfect_foresight_daily_revenue(hourly_prices):
    """Feature: backtest-expansion-mvp, Property 7: 对任意一天的小时价格，
    compute_daily_revenue 选出的 4 个放电小时应是价格最高的 4 个、4 个充电小时应是价格
    最低的 4 个（任一放电小时价 >= 任一未选小时价 >= 任一充电小时价），且当日收入应等于
    Σ(top4_price) - Σ(bottom4_price) / RTE（RTE=0.87）。

    Validates: Requirements 3.1, 3.2
    """
    hours = CaptureRateCalculator.BATTERY_HOURS  # 4
    rte = CaptureRateCalculator.RTE             # 0.87

    revenue = CaptureRateCalculator.compute_daily_revenue(hourly_prices)

    ordered = sorted(hourly_prices)
    charge = ordered[:hours]      # 最低 4 个 -> 充电
    discharge = ordered[-hours:]  # 最高 4 个 -> 放电
    middle = ordered[hours:-hours]  # 未选小时

    # 最优性：任一放电价 >= 任一未选价 >= 任一充电价
    for d in discharge:
        for m in middle:
            assert d >= m
    for m in middle:
        for c in charge:
            assert m >= c
    # 即便无中间段，放电最小值仍 >= 充电最大值
    assert min(discharge) >= max(charge)

    # 公式正确性：Σtop4 - Σbottom4 / RTE
    expected = sum(discharge) - sum(charge) / rte
    assert revenue == pytest.approx(expected, rel=1e-9, abs=1e-6)


# ===========================================================================
# Property 8: monthly_capture_rate 公式正确性 (Task 4.4, Validates 3.3)
# ===========================================================================


@settings(max_examples=100)
@given(
    actual=st.floats(
        min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
    mean_spread=st.floats(
        min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False
    ),
    days=st.integers(min_value=1, max_value=31),
    rte=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property_8_monthly_capture_rate_formula(actual, mean_spread, days, rte):
    """Feature: backtest-expansion-mvp, Property 8: 对任意月度实际收入 actual、月度
    mean_spread > 0、当月天数 days >= 1，封顶前的 monthly_capture_rate 应等于
    actual / (mean_spread × days × 4 × RTE)。

    Validates: Requirements 3.3
    """
    hours = CaptureRateCalculator.BATTERY_HOURS  # 4
    denom = mean_spread * days * hours * rte
    raw = actual / denom
    # 约束输入域到未封顶分支（raw <= 1.0），以便断言等于公式值
    assume(raw <= 1.0)

    rate, capped = CaptureRateCalculator.compute_monthly_capture_rate(
        monthly_actual_revenue=actual,
        monthly_mean_spread=mean_spread,
        days=days,
        rte=rte,
    )

    assert rate == pytest.approx(raw, rel=1e-9, abs=1e-12)
    assert capped is False


# ===========================================================================
# Property 9: capture_rate 封顶有界与标记 (Task 4.5, Validates 3.5)
# ===========================================================================


@settings(max_examples=100)
@given(raw=capture_rate_strategy)
def test_property_9_capture_rate_cap(raw):
    """Feature: backtest-expansion-mvp, Property 9: 对任意封顶前 capture rate 原始值，
    输出值应 <= 1.0；当原始值 > 1.0 时输出为 1.0 且 capped=True，否则输出等于原始值且
    capped=False。该封顶操作幂等。

    Validates: Requirements 3.5
    """
    value, capped = CaptureRateCalculator._cap_capture_rate(raw)

    assert value <= 1.0
    if raw > 1.0:
        assert value == 1.0
        assert capped is True
    else:
        assert value == raw
        assert capped is False

    # 幂等：对输出再封顶不变
    value2, capped2 = CaptureRateCalculator._cap_capture_rate(value)
    assert value2 == value
    assert capped2 is False


# ===========================================================================
# Property 10: 越界判定与 efficiency_ratio (Task 4.6, Validates 3.6, 4.1, 4.3, 4.4)
# ===========================================================================


@settings(max_examples=100)
@given(
    model=capture_rate_strategy,
    pf=capture_rate_strategy,
)
def test_property_10_violation_and_efficiency_ratio(model, pf):
    """Feature: backtest-expansion-mvp, Property 10: 对任意模型 capture rate model 与
    完美预见 capture rate pf，violation 为真当且仅当 model > pf + 0.05；当 violation 为假
    时 efficiency_ratio 应等于 model / pf（pf > 0），且 efficiency_ratio < 0.40 时
    low_efficiency_warning 为真。

    Validates: Requirements 3.6, 4.1, 4.3, 4.4
    """
    calc = CaptureRateCalculator()
    margin = CaptureRateCalculator.VIOLATION_MARGIN          # 0.05
    threshold = CaptureRateCalculator.LOW_EFFICIENCY_THRESHOLD  # 0.40

    comparison = calc.compare_with_model(
        model_capture_rate=model,
        perfect_foresight_rate=pf,
        region="NSW1",
        year_month="2024-01",
    )

    # violation 当且仅当 model > pf + 0.05
    assert comparison.violation == (model > pf + margin)

    if comparison.violation:
        # 越界时 efficiency_ratio 无意义，置 None
        assert comparison.efficiency_ratio is None
        assert comparison.low_efficiency_warning is False
    else:
        if pf > 0:
            assert comparison.efficiency_ratio == pytest.approx(
                model / pf, rel=1e-9, abs=1e-12
            )
            expected_warn = comparison.efficiency_ratio < threshold
            assert comparison.low_efficiency_warning == expected_warn
        else:
            # 非越界但 pf <= 0：无法计算有意义比值
            assert comparison.efficiency_ratio is None
            assert comparison.low_efficiency_warning is False


# ===========================================================================
# Property 11: violation_count 与明细一致性 (Task 4.7, Validates 4.2)
# ===========================================================================


def _make_comparison(violation: bool, idx: int) -> CaptureRateComparison:
    """构造一个 violation 标志确定的 CaptureRateComparison（仅用于 Property 11）。"""
    return CaptureRateComparison(
        region="NSW1",
        year_month=f"2024-{(idx % 12) + 1:02d}",
        model_capture_rate=0.9 if violation else 0.5,
        perfect_foresight_capture_rate=0.5 if violation else 0.9,
        efficiency_ratio=None if violation else 0.55,
        violation=violation,
        low_efficiency_warning=False,
    )


@settings(max_examples=100)
@given(violation_flags=st.lists(st.booleans(), max_size=30))
def test_property_11_violation_count_consistency(violation_flags):
    """Feature: backtest-expansion-mvp, Property 11: 对任意 region-month 对比结果集合，
    报告的 violation_count 应等于越界明细列表的长度，且明细列表中每一项的 violation 均为真、
    非明细项均为假。

    Validates: Requirements 4.2
    """
    comparisons = [_make_comparison(flag, i) for i, flag in enumerate(violation_flags)]

    summary = CaptureRateCalculator._summarize_comparisons(comparisons)

    expected_violations = sum(1 for f in violation_flags if f)
    # violation_count 等于越界明细列表长度
    assert summary["violation_count"] == len(summary["violations"])
    assert summary["violation_count"] == expected_violations

    # 明细项对应的对比 violation 均为真（明细数量与为真项一一对应）
    assert len(summary["violations"]) == sum(1 for c in comparisons if c.violation)
    # 非明细项均为假：非越界对比数量 == 总数 - 明细数
    non_violation_count = sum(1 for c in comparisons if not c.violation)
    assert non_violation_count == len(comparisons) - summary["violation_count"]


# ===========================================================================
# Property 12: reconciliation 归档 append 不变量 (Task 7.3, Validates 5.4, 6.2, 6.4)
# ===========================================================================


@settings(max_examples=100)
@given(
    existing=st.lists(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=8),
            values=st.integers(min_value=-1000, max_value=1000),
            max_size=5,
        ),
        max_size=20,
    ),
    record=st.dictionaries(
        keys=st.text(min_size=1, max_size=8),
        values=st.integers(min_value=-1000, max_value=1000),
        max_size=5,
    ),
)
def test_property_12_append_reconciliation_invariant(existing, record):
    """Feature: backtest-expansion-mvp, Property 12: 对任意既有记录数组（含空数组起点）与
    一条新对账记录，_append_reconciliation_record 结果应等于"原数组 + [新记录]"：长度恰好
    加一、所有历史记录按原顺序原值保留、新记录追加在末尾，且不修改入参。

    Validates: Requirements 5.4, 6.2, 6.4
    """
    existing_snapshot = copy.deepcopy(existing)
    record_snapshot = copy.deepcopy(record)

    result = _append_reconciliation_record(existing, record)

    # 长度恰好加一
    assert len(result) == len(existing) + 1
    # 历史记录按原顺序原值保留
    assert result[:-1] == existing_snapshot
    # 新记录追加在末尾
    assert result[-1] == record_snapshot
    # 等价于 existing + [record]
    assert result == existing_snapshot + [record_snapshot]
    # 不修改入参
    assert existing == existing_snapshot
    assert record == record_snapshot
