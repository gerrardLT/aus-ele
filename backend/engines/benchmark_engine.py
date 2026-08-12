"""NEM BESS revenue benchmark engine（Phase 1，2026-08-12）。

对标 Modo ME BESS AUS NEM Index 的轻量内部基准：用既有结算价数据
（trading_price_<year>）+ RevenueAnalysisEngine 计算滚动月度收益指数。

口径约定（必须随输出一起暴露，禁止与 Modo 绝对值直接对比）：
- 理想日内循环套利：每日取最高价 4 个时段放电、最低价 4 个时段充电
  （2h 参考电池每日最多 2 次满充放），能量平衡受 RTE 约束
- 不含 FCAS / 容量 / CIS 等价值流（coverage_mode: arbitrage-only）
- 不含网络费与市场费
- data_grade = derived

参考：docs/tasks/任务规划-2026-08-12-Benchmark整合与前后端规划.md
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 参考电池：与 Modo 参考资产同量级的 2h 电网级储能
DEFAULT_POWER_MW = 100.0
DEFAULT_ENERGY_MWH = 200.0
DEFAULT_RTE = 0.85

# NEM 结算基准：30 分钟（完整性期望值的分母；指数计算的时间长度从数据推断）
SETTLEMENT_INTERVAL_HOURS = 0.5
INTERVALS_PER_DAY = 48

# Benchmark 覆盖的 NEM 大陆区域（TAS1 体量小，暂不入基准）
NEM_BENCHMARK_REGIONS = ["NSW1", "QLD1", "SA1", "VIC1"]

COMPLETENESS_WARN_THRESHOLD = 0.90

# 完整性低于此阈值的月份视为不可用（不参与 latest/对比），仅展示
COMPLETE_MONTH_THRESHOLD = 0.95

BENCHMARK_COVERAGE_MODE = "arbitrage-only, FCAS not included"

BENCHMARK_CAVEATS = [
    "理想日内循环套利：每日最高价/最低价各取电池时长对应时段数放电/充电（2h 电池每日一次满充放），时间粒度按数据实际推断",
    "不含 FCAS / 容量 / CIS 等其他价值流",
    "不含网络费与市场费",
    "derived 口径，禁止与 Modo 等第三方指数绝对值直接对比",
]

# 2h 电池在 30 分钟粒度下的充/放时段上限（仅作默认参考，实际按数据粒度推断）
DAILY_CYCLE_INTERVALS = int((DEFAULT_ENERGY_MWH / DEFAULT_POWER_MW) / SETTLEMENT_INTERVAL_HOURS)


def _daily_arbitrage_revenue(
    day_prices: list[float],
    *,
    power_mw: float,
    energy_mwh: float,
    rte: float,
    cycle_intervals: int,
    interval_hours: float = SETTLEMENT_INTERVAL_HOURS,
) -> float:
    """单日理想循环套利净收入（AUD）。

    取当日最高价 cycle_intervals 个时段放电、最低价 cycle_intervals 个时段
    充电；日放电能量受时段数与电池容量双重约束，充电能量 = 放电能量 / RTE。
    数据不足一个完整充放循环时返回 0。
    """
    if len(day_prices) < 2 * cycle_intervals:
        return 0.0
    ranked = sorted(day_prices)
    avg_charge = sum(ranked[:cycle_intervals]) / cycle_intervals
    avg_discharge = sum(ranked[-cycle_intervals:]) / cycle_intervals

    discharge_mwh = min(
        cycle_intervals * power_mw * interval_hours,
        energy_mwh,
    )
    charge_mwh = discharge_mwh / rte
    net = discharge_mwh * avg_discharge - charge_mwh * avg_charge
    # 理想算子：无利可图的日不循环，不亏损运行
    return max(net, 0.0)


@dataclass
class MonthlyIndex:
    """单月基准指数记录。"""

    month: str  # "YYYY-MM"
    index_k_aud_per_mw_year: float  # 年化 kAUD/MW/年
    interval_count: int
    expected_intervals: int
    completeness_pct: float
    warnings: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.interval_count > 0 and self.completeness_pct >= COMPLETE_MONTH_THRESHOLD * 100.0


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def build_month_window(end: date, months: int) -> list[str]:
    """返回截至 end 上月的最近 ``months`` 个完整自然月（'YYYY-MM'，升序）。

    当前月数据不完整，永远排除在窗口之外。
    """
    if months < 1:
        raise ValueError("months must be >= 1")
    # end 的上一个月作为窗口终点
    y, m = end.year, end.month - 1
    if m < 1:
        y, m = y - 1, 12
    keys: list[str] = []
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m < 1:
            y, m = y - 1, 12
    keys.reverse()
    return keys


def _expected_intervals(month_key: str) -> int:
    year = int(month_key[:4])
    month = int(month_key[5:7])
    days = calendar.monthrange(year, month)[1]
    return days * INTERVALS_PER_DAY


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def _fetch_rows_for_months(db, region: str, month_keys: list[str]) -> list[tuple]:
    """跨分年表拉取指定月份的结算价行 (settlement_date, rrp_aud_mwh)。

    缺失的年表直接跳过（由完整性检查兜底告警），不抛裸 SQL 错误。
    """
    from sql_safe import trading_price_table

    years = sorted({int(k[:4]) for k in month_keys})
    rows: list[tuple] = []
    with db.get_connection() as conn:
        for year in years:
            table_name = trading_price_table(year)
            if not db._table_exists(conn, table_name):
                continue
            year_months = [k for k in month_keys if k.startswith(f"{year:04d}-")]
            placeholders = ", ".join("?" for _ in year_months)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
                f"WHERE region_id = ? AND substr(settlement_date, 1, 7) IN ({placeholders}) "
                f"ORDER BY settlement_date ASC",
                (region, *year_months),
            )
            rows.extend(cursor.fetchall())
    return rows


def _group_by_month(rows: list[tuple]) -> dict[str, list[tuple]]:
    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        key = str(row[0])[:7]
        grouped.setdefault(key, []).append(row)
    return grouped


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _compute_month_index(
    month_key: str,
    rows: list[tuple],
    *,
    power_mw: float,
    energy_mwh: float,
    rte: float,
) -> MonthlyIndex:
    # 按日分组 → 逐日理想循环套利 → 月度汇总
    by_day: dict[str, list[float]] = {}
    for r in rows:
        if r[1] is None:
            continue
        by_day.setdefault(str(r[0])[:10], []).append(float(r[1]))

    # 数据实际粒度推断（库内可能为 5 分钟粒度）：
    # 循环时段数按电池时长折算；每日能量上限不变（power × duration）
    n_days = len(by_day)
    avg_points_per_day = (sum(len(v) for v in by_day.values()) / n_days) if n_days else 0.0
    if avg_points_per_day > 0:
        interval_hours = 24.0 / avg_points_per_day
    else:
        interval_hours = SETTLEMENT_INTERVAL_HOURS
    duration_hours = energy_mwh / power_mw
    cycle_intervals = max(1, int(round(duration_hours / interval_hours)))

    monthly_revenue = sum(
        _daily_arbitrage_revenue(
            day_prices,
            power_mw=power_mw,
            energy_mwh=energy_mwh,
            rte=rte,
            cycle_intervals=cycle_intervals,
            interval_hours=interval_hours,
        )
        for day_prices in by_day.values()
    )

    # 完整性分母随数据粒度推断（30min 结算基准 × 粒度倍数）
    granularity_factor = SETTLEMENT_INTERVAL_HOURS / interval_hours if interval_hours > 0 else 1.0
    expected = int(_expected_intervals(month_key) * granularity_factor)
    count = len(rows)
    completeness = (count / expected) if expected else 0.0

    warnings: list[str] = []
    if count == 0:
        warnings.append("no_data")
    elif completeness < COMPLETENESS_WARN_THRESHOLD:
        warnings.append("incomplete_month")

    # 月度净收入 → 年化 kAUD/MW/年
    annualized_per_mw = (monthly_revenue / power_mw) * 12 if power_mw else 0.0
    return MonthlyIndex(
        month=month_key,
        index_k_aud_per_mw_year=round(annualized_per_mw / 1000.0, 2),
        interval_count=count,
        expected_intervals=expected,
        completeness_pct=round(completeness * 100.0, 1),
        warnings=warnings,
    )


def build_nem_bess_benchmark(
    db,
    region: str,
    months: int = 12,
    *,
    power_mw: float = DEFAULT_POWER_MW,
    energy_mwh: float = DEFAULT_ENERGY_MWH,
    rte: float = DEFAULT_RTE,
    today: date | None = None,
) -> dict[str, Any]:
    """计算单区域滚动月度基准指数。

    Returns:
        含 monthly 序列、latest、avg、趋势对比与口径 caveat 的 payload。
    """
    if region not in NEM_BENCHMARK_REGIONS:
        raise ValueError(
            f"Benchmark 仅覆盖 NEM 大陆区域 {NEM_BENCHMARK_REGIONS}，不支持 {region}"
        )
    months = max(1, min(int(months), 24))
    end = today or date.today()
    window = build_month_window(end, months)

    rows = _fetch_rows_for_months(db, region, window)
    grouped = _group_by_month(rows)

    monthly = [
        _compute_month_index(
            key,
            grouped.get(key, []),
            power_mw=power_mw,
            energy_mwh=energy_mwh,
            rte=rte,
        )
        for key in window
    ]

    valid = [m for m in monthly if m.is_complete]
    latest = valid[-1] if valid else None
    avg_k = round(sum(m.index_k_aud_per_mw_year for m in valid) / len(valid), 2) if valid else None

    summary: dict[str, Any] = {
        "months_in_window": len(window),
        "months_with_data": len(valid),
        "avg_index_k_aud_per_mw_year": avg_k,
    }
    if latest is not None and avg_k:
        summary["latest_month"] = latest.month
        summary["latest_index_k_aud_per_mw_year"] = latest.index_k_aud_per_mw_year
        summary["latest_vs_avg_pct"] = round(
            (latest.index_k_aud_per_mw_year - avg_k) / avg_k * 100.0, 1
        )

    return {
        "region": region,
        "reference_battery": {
            "power_mw": power_mw,
            "energy_mwh": energy_mwh,
            "round_trip_efficiency": rte,
        },
        "summary": summary,
        "monthly": [
            {
                "month": m.month,
                "index_k_aud_per_mw_year": m.index_k_aud_per_mw_year,
                "interval_count": m.interval_count,
                "completeness_pct": m.completeness_pct,
                "warnings": m.warnings,
            }
            for m in monthly
        ],
        "coverage_mode": BENCHMARK_COVERAGE_MODE,
        "caveats": BENCHMARK_CAVEATS,
    }


def build_nem_bess_region_compare(
    db,
    *,
    months: int = 12,
    power_mw: float = DEFAULT_POWER_MW,
    energy_mwh: float = DEFAULT_ENERGY_MWH,
    rte: float = DEFAULT_RTE,
    today: date | None = None,
) -> dict[str, Any]:
    """最近完整月（completeness ≥ 阈值）的四大区域横向对比。

    完整月通过滚动窗口内逐月完整性判定确定，避免数据未齐的
    当前月末月份污染对比结果。
    """
    months = max(1, min(int(months), 24))
    end = today or date.today()
    window = build_month_window(end, months)

    # 逐区计算滚动窗口，取各自最近完整月；对比月取各区完整月的最大值
    per_region: dict[str, tuple[str, MonthlyIndex]] = {}
    for region in NEM_BENCHMARK_REGIONS:
        rows = _fetch_rows_for_months(db, region, window)
        grouped = _group_by_month(rows)
        latest_complete: tuple[str, MonthlyIndex] | None = None
        for key in window:
            idx = _compute_month_index(
                key,
                grouped.get(key, []),
                power_mw=power_mw,
                energy_mwh=energy_mwh,
                rte=rte,
            )
            if idx.is_complete:
                latest_complete = (key, idx)
        if latest_complete is not None:
            per_region[region] = latest_complete

    if not per_region:
        compare_month = window[-1]
    else:
        compare_month = max(m for m, _ in per_region.values())

    items = []
    for region in NEM_BENCHMARK_REGIONS:
        entry = per_region.get(region)
        if entry is None or entry[0] != compare_month:
            items.append(
                {
                    "region": region,
                    "month": compare_month,
                    "index_k_aud_per_mw_year": None,
                    "completeness_pct": None,
                    "warnings": ["no_complete_month_in_window"],
                }
            )
            continue
        idx = entry[1]
        items.append(
            {
                "region": region,
                "month": compare_month,
                "index_k_aud_per_mw_year": idx.index_k_aud_per_mw_year,
                "completeness_pct": idx.completeness_pct,
                "warnings": idx.warnings,
            }
        )

    items.sort(
        key=lambda x: (x["index_k_aud_per_mw_year"] is None, -(x["index_k_aud_per_mw_year"] or 0.0))
    )
    return {
        "month": compare_month,
        "reference_battery": {
            "power_mw": power_mw,
            "energy_mwh": energy_mwh,
            "round_trip_efficiency": rte,
        },
        "items": items,
        "coverage_mode": BENCHMARK_COVERAGE_MODE,
        "caveats": BENCHMARK_CAVEATS,
    }
