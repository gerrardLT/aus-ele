"""Backtest Expansion MVP — 月度 AEMO 基准回测扩展模块。

将 Forward Price Engine 的回测框架从 16 个 Modo Energy 基准时段扩展到 96+ 个
月度数据点，数据源为本地 ``data/aemo_data.db``（AEMO 5 分钟级实测交易价格）。

本模块封装三大核心能力（后续任务逐步实现）：

- ``MonthlyBenchmarkCalculator``：从 AEMO 实测数据按"月 × 区域"聚合月度 mean_spread 基准。
- ``CaptureRateCalculator``：基于 4 小时电池完美预见策略直算理论最优 capture rate。
- ``validate_against_monthly_benchmarks_impl`` / ``run_monthly_reconciliation``：
  月度基准验证与月度自动 reconciliation 入口。

设计原则：零侵入既有引擎、补充而非替换、优雅降级。所有数据访问遵循
"记录日志 + 优雅降级、绝不向上抛出"原则。

Requirements: 1.6, 2.5, 8.5
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 仓库根目录：backend/engines/backtest_expansion.py -> engines -> backend -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# set_progress_handler 回调的 VM 指令间隔：每执行该条数 SQLite VM 指令调用一次
# 超时回调。值越小越能及时中止长查询（开销略增），1000 在 30s 量级查询下足够灵敏。
_PROGRESS_HANDLER_INSTRUCTIONS = 1000


def _default_db_path() -> str:
    """解析默认 AEMO 数据库路径（与 ``db_factory`` / ``server`` 同源）。

    优先读取 ``AUS_ELE_DB_PATH`` 环境变量，缺省回退到 ``<repo>/data/aemo_data.db``。
    """
    return os.environ.get(
        "AUS_ELE_DB_PATH",
        str((_REPO_ROOT / "data" / "aemo_data.db").resolve()),
    )


class QueryTimeoutError(Exception):
    """单 region-month 查询超出 ``QUERY_TIMEOUT_SECONDS`` 时由超时回调触发 (Req 9.5)。

    ``set_progress_handler`` 回调返回非零值会令 SQLite 中止当前查询并抛出
    ``sqlite3.OperationalError``；为便于精确区分 "超时中止" 与其他
    ``OperationalError``（如表缺失），回调内同步置位标志，调用方据此重抛本异常。
    """


def _install_timeout(
    conn: sqlite3.Connection, timeout_seconds: float
) -> dict[str, bool]:
    """为连接安装基于 ``set_progress_handler`` 的纯标准库查询超时 (Req 9.5)。

    回调每执行 ``_PROGRESS_HANDLER_INSTRUCTIONS`` 条 SQLite VM 指令触发一次，比较
    ``time.monotonic() - start`` 是否超过 ``timeout_seconds``；超时则置位返回的
    ``state["timed_out"]`` 标志并返回非零值，令 SQLite 抛出 ``OperationalError`` 中止查询。
    本方案不依赖额外线程，纯标准库实现，便于测试中以很小的阈值稳定触发。

    复用说明：任务 4.1 的 ``CaptureRateCalculator`` 可直接调用本辅助以复用同一超时机制。

    Args:
        conn: 待安装超时的 SQLite 连接。
        timeout_seconds: 超时阈值（秒）。

    Returns:
        共享状态字典 ``{"timed_out": bool}``；查询抛 ``OperationalError`` 后，
        调用方检查该标志即可区分 "超时" 与其他错误（如表缺失）。
    """
    start = time.monotonic()
    state = {"timed_out": False}

    def _handler() -> int:
        if time.monotonic() - start > timeout_seconds:
            state["timed_out"] = True
            return 1  # 非零 -> 中止查询，触发 OperationalError
        return 0

    conn.set_progress_handler(_handler, _PROGRESS_HANDLER_INSTRUCTIONS)
    return state


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class MonthlyBenchmark:
    """月度 mean_spread 基准数据点 (Req 1.6)。"""

    region: str  # NSW1 / QLD1 / SA1 / TAS1 / VIC1
    year_month: str  # 'YYYY-MM'
    mean_spread_aud_mwh: float  # 有效日 (max-min) 均值, 可因负价更大
    sample_days: int  # 有效日计数 (interval>=200 的天数)
    data_quality_flag: str  # 'ok' | 'insufficient_data'


@dataclass(frozen=True)
class CaptureRateResult:
    """完美预见 capture rate 直算结果 (Req 3)。"""

    region: str
    year_month: str
    monthly_actual_revenue: float
    perfect_foresight_capture_rate: float  # 已封顶 [0, 1.0]
    capped: bool  # 原始值 > 1.0 时为 True (Req 3.5)
    sample_days: int


@dataclass(frozen=True)
class CaptureRateComparison:
    """模型 vs 完美预见对比 (Req 4)。"""

    region: str
    year_month: str
    model_capture_rate: float
    perfect_foresight_capture_rate: float
    efficiency_ratio: float | None  # 非越界时 = model / pf (Req 4.3)
    violation: bool  # model > pf + 0.05 (Req 4.1)
    low_efficiency_warning: bool  # efficiency_ratio < 0.40 (Req 4.4)


@dataclass(frozen=True)
class MonthlyValidationResult:
    """单 region-month 月度验证结果 (Req 2.5 兼容字段)。"""

    region: str
    year_month: str
    model_mean_spread: float
    benchmark_mean_spread: float
    deviation_pct: float


# =============================================================================
# MonthlyBenchmarkCalculator (Req 1, 9)
# =============================================================================


class MonthlyBenchmarkCalculator:
    """从 AEMO 实测数据按 "月 × 区域" 聚合月度 mean_spread 基准 (Req 1)。

    数据源为本地 ``data/aemo_data.db`` 的 ``trading_price_{year}`` 表，列为
    ``settlement_date`` (TEXT, 形如 ``2024-01-01 00:05:00``)、``region_id`` (TEXT)、
    ``rrp_aud_mwh`` (REAL, 可为负)。月度基准定义为 "某日历月内每日
    ``max(rrp) - min(rrp)`` 的算术平均值"，仅统计有效日（单日 interval >= 200）。

    优雅降级原则：数据库 / 表 / 数据缺失或查询超时均记录日志后返回 None / 跳过，
    绝不向上抛出（Req 9）。
    """

    # NEM 五区域，排除 WEM (Req 1.2)
    NEM_REGIONS: tuple[str, ...] = ("NSW1", "QLD1", "SA1", "TAS1", "VIC1")
    MIN_INTERVALS_PER_DAY: int = 200   # 单日有效阈值 (Req 1.5)
    MIN_VALID_DAYS: int = 20           # 月有效阈值 (Req 1.5)
    QUERY_TIMEOUT_SECONDS: int = 30    # 单 region-month 超时 (Req 9.5)
    START_MONTH: str = "2024-01"       # 起始月 (Req 1.4)

    def __init__(self, db_path: str | None = None) -> None:
        """初始化计算器。

        Args:
            db_path: AEMO 数据库路径。缺省解析 ``AUS_ELE_DB_PATH`` 环境变量，
                再回退到 ``<repo>/data/aemo_data.db``（与既有引擎同源）。
        """
        self.db_path: str = db_path if db_path is not None else _default_db_path()

    # ------------------------------------------------------------------
    # 纯聚合逻辑（与 DB I/O 解耦，便于属性测试）
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_monthly_benchmark(
        region: str,
        year_month: str,
        daily_rows: list[tuple[str, float, int]],
    ) -> MonthlyBenchmark:
        """将每日聚合行折叠为单个 :class:`MonthlyBenchmark`（纯函数）。

        Args:
            region: 区域代码（NSW1 / QLD1 / SA1 / TAS1 / VIC1）。
            year_month: 目标月份 ``'YYYY-MM'``。
            daily_rows: 每日聚合行列表 ``(day, spread, intervals)``，其中
                ``spread = max(rrp) - min(rrp)``（负价已直接进入 min/max，
                不过滤不截断，Req 9.4），``intervals`` 为当日 5 分钟样本计数。

        Returns:
            MonthlyBenchmark：``mean_spread_aud_mwh`` 为所有有效日
            （``intervals >= MIN_INTERVALS_PER_DAY``）价差的算术平均值；
            ``sample_days`` 为有效日计数；有效日 < ``MIN_VALID_DAYS`` 时
            ``data_quality_flag = "insufficient_data"``，否则 ``"ok"``（Req 1.5）。
        """
        valid_spreads = [
            spread
            for _day, spread, intervals in daily_rows
            if intervals >= MonthlyBenchmarkCalculator.MIN_INTERVALS_PER_DAY
        ]
        sample_days = len(valid_spreads)
        mean_spread = sum(valid_spreads) / sample_days if sample_days > 0 else 0.0
        flag = (
            "ok"
            if sample_days >= MonthlyBenchmarkCalculator.MIN_VALID_DAYS
            else "insufficient_data"
        )
        return MonthlyBenchmark(
            region=region,
            year_month=year_month,
            mean_spread_aud_mwh=mean_spread,
            sample_days=sample_days,
            data_quality_flag=flag,
        )

    # ------------------------------------------------------------------
    # DB I/O
    # ------------------------------------------------------------------

    def _query_daily_spreads(
        self, conn: sqlite3.Connection, region: str, year_month: str
    ) -> list[tuple[str, float, int]]:
        """查询单 region-month 的每日价差与 interval 计数。

        使用 ``region_id`` 列（非 ``region``，见 schema 勘误）按
        ``DATE(settlement_date)`` 分组，计算 ``MAX(rrp)-MIN(rrp)`` 与
        ``COUNT(*)``。负电价不做任何过滤或截断，直接进入 MIN/MAX（Req 9.4）。

        Returns:
            每日聚合行列表 ``(day, spread, intervals)``。
        """
        year = year_month[:4]
        table = f"trading_price_{year}"
        rows = conn.execute(
            f"""
            SELECT DATE(settlement_date) AS day,
                   MAX(rrp_aud_mwh) - MIN(rrp_aud_mwh) AS spread,
                   COUNT(*) AS intervals
            FROM {table}
            WHERE region_id = ? AND substr(settlement_date, 1, 7) = ?
            GROUP BY DATE(settlement_date)
            ORDER BY day
            """,
            (region, year_month),
        ).fetchall()
        return [(row[0], float(row[1]), int(row[2])) for row in rows]

    def compute_monthly_benchmark(
        self, region: str, year_month: str
    ) -> MonthlyBenchmark | None:
        """计算单个 region-month 的 mean_spread 基准 (Req 1.1, 1.3, 1.5, 1.6, 9.x)。

        - 解析 ``year_month`` ('YYYY-MM') 取 year，选择 ``trading_price_{year}`` 表。
        - 按 ``DATE(settlement_date)`` 分组取每日 ``max(rrp)-min(rrp)`` 与 interval 计数。
        - 仅保留 ``interval >= 200`` 的有效日；``mean_spread_aud_mwh`` 为有效日价差均值。
        - 有效日 < 20 -> ``data_quality_flag = "insufficient_data"``，否则 ``"ok"``。

        优雅降级（绝不向上抛出，Req 9）：

        - 数据库文件不可达（``Path.exists()`` 为假或连接失败）-> 记 warning 返回 None（Req 9.1）。
        - ``trading_price_{year}`` 表不存在 -> 记 info 返回 None（Req 9.2）。
        - 区域-月零行（无有效数据）-> 记 debug 返回 None（Req 9.3）。
        - 单查询超过 ``QUERY_TIMEOUT_SECONDS`` 秒 -> 中止该查询，记 warning 返回 None（Req 9.5）。

        Returns:
            MonthlyBenchmark；任一降级场景下返回 None。
        """
        # Req 9.1: 数据库文件不可达 — sqlite3.connect 对不存在路径会静默新建空库，
        # 故须先用 Path.exists() 显式检查，避免误把缺库当成 "空数据"。
        if not Path(self.db_path).exists():
            logger.warning(
                "AEMO 数据库文件不可达，跳过 region-month: path=%s region=%s year_month=%s",
                self.db_path,
                region,
                year_month,
            )
            return None

        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error as exc:  # Req 9.1: 连接异常
            logger.warning(
                "连接 AEMO 数据库失败，跳过 region-month: path=%s region=%s "
                "year_month=%s err=%s",
                self.db_path,
                region,
                year_month,
                exc,
            )
            return None

        timeout_state = _install_timeout(conn, self.QUERY_TIMEOUT_SECONDS)
        try:
            daily_rows = self._query_daily_spreads(conn, region, year_month)
        except sqlite3.OperationalError as exc:
            if timeout_state["timed_out"]:
                # Req 9.5: 单查询超时 -> 中止该 region-month，继续其余
                logger.warning(
                    "查询超时（> %ss），跳过 region-month: region=%s year_month=%s",
                    self.QUERY_TIMEOUT_SECONDS,
                    region,
                    year_month,
                )
                return None
            if "no such table" in str(exc).lower():
                # Req 9.2: trading_price_{year} 表缺失 -> 跳过该年/该 region-month
                logger.info(
                    "trading_price 表不存在，跳过 region-month: region=%s "
                    "year_month=%s err=%s",
                    region,
                    year_month,
                    exc,
                )
                return None
            # 其余 OperationalError 不静默吞掉
            raise
        finally:
            conn.set_progress_handler(None, _PROGRESS_HANDLER_INSTRUCTIONS)
            conn.close()

        if not daily_rows:
            # Req 9.3: 区域-月零行 -> 排除该点
            logger.debug(
                "region-month 无数据，排除: region=%s year_month=%s", region, year_month
            )
            return None

        return self.aggregate_monthly_benchmark(region, year_month, daily_rows)

    # ------------------------------------------------------------------
    # 月份枚举（纯函数，与 DB I/O 解耦，便于属性测试 — Property 3）
    # ------------------------------------------------------------------

    @staticmethod
    def _enumerate_months(start: str, end: str) -> list[str]:
        """连续枚举 ``[start, end]`` 闭区间内的所有月份 ``'YYYY-MM'``（纯函数）。

        从 ``start`` 起逐月递增直到 ``end``（含两端），保证无遗漏、无重复、无越界、
        严格升序。当 ``end < start`` 时返回空列表。

        Args:
            start: 起始月 ``'YYYY-MM'``（含）。
            end: 截止月 ``'YYYY-MM'``（含）。

        Returns:
            连续的月份字符串列表，形如 ``['2024-01', '2024-02', ...]``。
        """
        start_year, start_month = int(start[:4]), int(start[5:7])
        end_year, end_month = int(end[:4]), int(end[5:7])

        months: list[str] = []
        year, month = start_year, start_month
        while (year, month) <= (end_year, end_month):
            months.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                month = 1
                year += 1
        return months

    # ------------------------------------------------------------------
    # 数据覆盖探测 + 全量枚举
    # ------------------------------------------------------------------

    def _existing_trading_tables(
        self, conn: sqlite3.Connection
    ) -> list[tuple[int, str]]:
        """返回数据库中存在的 ``trading_price_{year}`` 表 ``(year, table_name)`` 列表。

        按年份升序排列。用于探测数据覆盖范围，跳过缺失年份。
        """
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'trading_price_%'
            ORDER BY name
            """
        ).fetchall()
        tables: list[tuple[int, str]] = []
        for (name,) in rows:
            suffix = name.rsplit("_", 1)[-1]
            if suffix.isdigit():
                tables.append((int(suffix), name))
        tables.sort(key=lambda t: t[0])
        return tables

    def latest_complete_month(self) -> str | None:
        """探测 AEMO_Database 中数据覆盖到月末的最新完整日历月 (Req 1.4)。

        实现思路：取所有 ``trading_price_{year}`` 表中（限 NEM 五区域，排除 WEM）
        最大的 ``settlement_date``，判断该月是否完整——即最新数据是否覆盖到该日历月
        的最后一天。若最新月不完整（最大日期早于月末最后一天），则回退到上一个完整月。

        Returns:
            最新完整月 ``'YYYY-MM'``；数据库不可达或无任何可用数据时返回 None。
        """
        # Req 9.1: 文件不存在时 sqlite3.connect 会静默新建空库，先显式检查
        if not Path(self.db_path).exists():
            logger.warning("AEMO 数据库文件不可达: %s", self.db_path)
            return None

        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error:
            logger.warning("无法连接 AEMO 数据库: %s", self.db_path)
            return None

        try:
            tables = self._existing_trading_tables(conn)
            placeholders = ",".join("?" for _ in self.NEM_REGIONS)
            max_date: str | None = None
            for _year, table in tables:
                row = conn.execute(
                    f"SELECT MAX(settlement_date) FROM {table} "
                    f"WHERE region_id IN ({placeholders})",
                    self.NEM_REGIONS,
                ).fetchone()
                if row and row[0] and (max_date is None or row[0] > max_date):
                    max_date = row[0]
        finally:
            conn.close()

        if not max_date:
            logger.warning("AEMO 数据库中无可用 trading_price 数据")
            return None

        # max_date 形如 'YYYY-MM-DD HH:MM:SS'
        latest_year = int(max_date[0:4])
        latest_month = int(max_date[5:7])
        latest_day = int(max_date[8:10])

        last_day_of_month = calendar.monthrange(latest_year, latest_month)[1]
        if latest_day >= last_day_of_month:
            # 最新月已覆盖到月末 → 该月即最新完整月
            return f"{latest_year:04d}-{latest_month:02d}"

        # 最新月不完整 → 回退到上一个完整月
        prev_month_last_day = date(latest_year, latest_month, 1) - timedelta(days=1)
        return f"{prev_month_last_day.year:04d}-{prev_month_last_day.month:02d}"

    def compute_all_benchmarks(
        self, end_month: str | None = None
    ) -> list[MonthlyBenchmark]:
        """从 START_MONTH 连续枚举到 ``end_month`` × 五区域，逐点计算月度基准 (Req 1.2, 1.4)。

        Args:
            end_month: 截止月 ``'YYYY-MM'``（含）。缺省时取 :meth:`latest_complete_month`
                （数据覆盖到月末的最新完整月）。

        Returns:
            所有非 None 的 :class:`MonthlyBenchmark` 列表。月份从 ``START_MONTH``
            (2024-01) 起连续覆盖到 ``end_month``，每月遍历全部五个 NEM 区域（排除 WEM）；
            无数据的 region-month（``compute_monthly_benchmark`` 返回 None）被跳过。
            当无法确定截止月（数据库无数据）时返回空列表。
        """
        # Req 9.1: 数据库文件不可达 -> 记 warning 返回空列表，不抛异常
        if not Path(self.db_path).exists():
            logger.warning(
                "AEMO 数据库文件不可达，compute_all_benchmarks 返回空列表: path=%s",
                self.db_path,
            )
            return []

        if end_month is None:
            end_month = self.latest_complete_month()
        if end_month is None:
            logger.warning("无法确定最新完整月，compute_all_benchmarks 返回空列表")
            return []

        results: list[MonthlyBenchmark] = []
        for year_month in self._enumerate_months(self.START_MONTH, end_month):
            for region in self.NEM_REGIONS:
                benchmark = self.compute_monthly_benchmark(region, year_month)
                if benchmark is not None:
                    results.append(benchmark)
        return results


# =============================================================================
# CaptureRateCalculator (Req 3, 4)
# =============================================================================


class CaptureRateCalculator:
    """基于 4 小时电池完美预见策略直算理论最优 capture rate (Req 3)。

    数据源同 :class:`MonthlyBenchmarkCalculator`：本地 ``data/aemo_data.db`` 的
    ``trading_price_{year}`` 表（``settlement_date`` / ``region_id`` / ``rrp_aud_mwh``）。

    完美预见策略：对每一天，先把 5 分钟价格按小时（``HH = substr(settlement_date, 12, 2)``）
    聚合为最多 24 个小时均价，再选价格最高的 4 个小时放电、最低的 4 个小时充电：

        daily_revenue = Σ(discharge_price × 1MW × 1h) - Σ(charge_price × 1MW × 1h / RTE)

    月度：

        monthly_actual_revenue = Σ daily_revenue（仅有效日）
        monthly_capture_rate   = monthly_actual_revenue
            / (monthly_mean_spread × days × BATTERY_HOURS × RTE)

    其中 ``monthly_mean_spread`` 复用 :class:`MonthlyBenchmarkCalculator` 算出的该
    region-month 月度基准（有效日均值），``capture_rate > 1.0`` 时封顶 1.0 且
    ``capped=True``（Req 3.5）。

    优雅降级原则：数据库 / 表 / 数据缺失或查询超时均记录日志后返回 None，绝不向上抛出
    （复用 §2.3 ``_install_timeout`` 与同款 ``OperationalError`` 处理，Req 9）。

    本任务（4.1）仅实现 :meth:`compute_perfect_foresight`；``compare_with_model`` /
    ``validate_all`` 由任务 4.2 实现。
    """

    RTE: float = 0.87                    # round-trip efficiency (与 bess_backtest 一致)
    BATTERY_HOURS: int = 4               # 4 小时电池 (Req 3.1)
    VIOLATION_MARGIN: float = 0.05       # 越界容差 (Req 3.6/4.1)
    LOW_EFFICIENCY_THRESHOLD: float = 0.40  # 低效率告警阈值 (Req 4.4)

    def __init__(self, db_path: str | None = None) -> None:
        """初始化计算器。

        Args:
            db_path: AEMO 数据库路径。缺省解析 ``AUS_ELE_DB_PATH`` 环境变量，
                再回退到 ``<repo>/data/aemo_data.db``（复用 ``_default_db_path()``，
                与 :class:`MonthlyBenchmarkCalculator` 同源）。
        """
        self.db_path: str = db_path if db_path is not None else _default_db_path()
        # 复用月度基准计算器获取 monthly_mean_spread（有效日均值）与有效日口径
        self._benchmark_calc = MonthlyBenchmarkCalculator(self.db_path)

    # ------------------------------------------------------------------
    # 纯计算逻辑（与 DB I/O 解耦，便于属性测试 — Property 7/8/9）
    # ------------------------------------------------------------------

    @staticmethod
    def compute_daily_revenue(hourly_prices: list[float]) -> float:
        """完美预见单日套利收入（纯函数，Req 3.1, 3.2）。

        选价格最高的 ``BATTERY_HOURS`` 个小时放电、最低的 ``BATTERY_HOURS`` 个小时充电，
        每小时按 1MW × 1h = 1MWh 计：

            daily_revenue = Σ(top4_price) - Σ(bottom4_price) / RTE

        负电价直接进入排序（不过滤不截断，Req 9.4）；充电价为负时
        ``- charge/RTE`` 自然转为正贡献，语义与实测一致。

        Args:
            hourly_prices: 当日各小时均价列表（最多 24 个）。

        Returns:
            当日完美预见套利收入；当可用小时数不足 ``2 × BATTERY_HOURS``
            （无法构成不重叠的充放电时段）时返回 ``0.0``。
        """
        hours = CaptureRateCalculator.BATTERY_HOURS
        if len(hourly_prices) < 2 * hours:
            return 0.0
        ordered = sorted(hourly_prices)
        charge_prices = ordered[:hours]      # 最低 hours 个小时 -> 充电
        discharge_prices = ordered[-hours:]  # 最高 hours 个小时 -> 放电
        return sum(discharge_prices) - sum(charge_prices) / CaptureRateCalculator.RTE

    @staticmethod
    def _cap_capture_rate(raw_capture_rate: float) -> tuple[float, bool]:
        """对 capture rate 原始值封顶到 ``[?, 1.0]``（纯函数，Req 3.5）。

        原始值 > 1.0 -> 返回 ``(1.0, True)``，否则返回 ``(raw, False)``。该操作幂等：
        对已封顶值再次封顶结果不变。

        Returns:
            ``(capped_value, capped_flag)``。
        """
        if raw_capture_rate > 1.0:
            return 1.0, True
        return raw_capture_rate, False

    @staticmethod
    def compute_monthly_capture_rate(
        monthly_actual_revenue: float,
        monthly_mean_spread: float,
        days: int,
        rte: float,
    ) -> tuple[float, bool]:
        """月度 capture rate 公式 + 封顶（纯函数，Req 3.3, 3.5）。

        封顶前：

            raw = monthly_actual_revenue
                / (monthly_mean_spread × days × BATTERY_HOURS × rte)

        随后经 :meth:`_cap_capture_rate` 封顶。当分母 ≤ 0（``mean_spread`` 或
        ``days`` 非正）时返回 ``(0.0, False)``，避免除零。

        Args:
            monthly_actual_revenue: 月度完美预见实际收入（有效日 daily_revenue 之和）。
            monthly_mean_spread: 月度基准 mean_spread（有效日均值，与分子同口径）。
            days: 参与计算的天数（本实现采用有效日 ``sample_days`` 口径，见
                :meth:`compute_perfect_foresight` docstring）。
            rte: round-trip efficiency。

        Returns:
            ``(capture_rate, capped)``：封顶后值与是否触发封顶标志。
        """
        denom = monthly_mean_spread * days * CaptureRateCalculator.BATTERY_HOURS * rte
        if denom <= 0:
            return 0.0, False
        raw = monthly_actual_revenue / denom
        return CaptureRateCalculator._cap_capture_rate(raw)


    # ------------------------------------------------------------------
    # DB I/O
    # ------------------------------------------------------------------

    def _query_hourly_prices(
        self, conn: sqlite3.Connection, region: str, year_month: str
    ) -> dict[str, dict[str, object]]:
        """查询单 region-month 每天的逐小时均价与日内 interval 计数。

        使用 ``region_id`` 列（schema 勘误），按 ``DATE`` 与 ``HH`` 双重分组：
        ``substr(settlement_date, 1, 10)`` 取日、``substr(settlement_date, 12, 2)``
        取小时，对 ``rrp_aud_mwh`` 求 ``AVG`` 得到每小时均价（5 分钟价格按小时算术平均），
        并以 ``COUNT(*)`` 累加得到每日总 interval 计数。负电价不过滤不截断（Req 9.4）。

        Returns:
            ``{day: {"prices": [hourly_avg, ...], "intervals": total_count}}``，
            其中 ``prices`` 为该日各小时均价（最多 24 个，按小时升序）。
        """
        year = year_month[:4]
        table = f"trading_price_{year}"
        rows = conn.execute(
            f"""
            SELECT substr(settlement_date, 1, 10) AS day,
                   substr(settlement_date, 12, 2) AS hh,
                   AVG(rrp_aud_mwh) AS price,
                   COUNT(*) AS n
            FROM {table}
            WHERE region_id = ? AND substr(settlement_date, 1, 7) = ?
            GROUP BY day, hh
            ORDER BY day, hh
            """,
            (region, year_month),
        ).fetchall()

        days: dict[str, dict[str, object]] = {}
        for day, _hh, price, n in rows:
            bucket = days.setdefault(day, {"prices": [], "intervals": 0})
            bucket["prices"].append(float(price))  # type: ignore[union-attr]
            bucket["intervals"] = int(bucket["intervals"]) + int(n)  # type: ignore[arg-type]
        return days

    def compute_perfect_foresight(
        self, region: str, year_month: str
    ) -> CaptureRateResult | None:
        """计算单个 region-month 的完美预见 capture rate (Req 3.1, 3.2, 3.3, 3.5, 9.x)。

        流程：

        1. 逐小时聚合：5 分钟价格按 ``HH`` 取算术平均得每天最多 24 个小时均价
           （:meth:`_query_hourly_prices`）。
        2. 有效日筛选：仅保留日内总 interval ≥ ``MIN_INTERVALS_PER_DAY`` (200) 的天，
           与 :class:`MonthlyBenchmarkCalculator` 同口径。
        3. 每个有效日：选 top-4 小时放电、bottom-4 小时充电，按
           :meth:`compute_daily_revenue` 求 ``Σtop4 - Σbottom4 / RTE``。
        4. ``monthly_actual_revenue = Σ daily_revenue``（有效日）。
        5. ``monthly_capture_rate = monthly_actual_revenue
           / (monthly_mean_spread × days × BATTERY_HOURS × RTE)``，
           经 :meth:`compute_monthly_capture_rate` 封顶（>1.0 → 1.0 且 ``capped=True``）。

        **days 口径说明（设计取舍）：** 公式中 ``days`` 采用**有效日 ``sample_days``** 口径
        （而非日历月天数）。因为 ``monthly_actual_revenue`` 仅累加有效日收入、
        ``monthly_mean_spread`` 亦为有效日价差均值，采用 ``sample_days`` 可保证分子与
        分母作用在同一有效日集合上，量纲与口径一致；若混入无效日的日历天数会系统性
        低估 capture rate。``monthly_mean_spread`` 复用
        :meth:`MonthlyBenchmarkCalculator.compute_monthly_benchmark` 的有效日均值结果。

        优雅降级（绝不向上抛出，复用 §2.3 机制，Req 9）：

        - 数据库文件不可达 → 记 warning 返回 None（Req 9.1）。
        - ``trading_price_{year}`` 表不存在 → 记 info 返回 None（Req 9.2）。
        - region-month 零行 / 无有效日 → 记 debug 返回 None（Req 9.3）。
        - 单查询超过 ``QUERY_TIMEOUT_SECONDS`` 秒 → 中止并记 warning 返回 None（Req 9.5）。

        Returns:
            CaptureRateResult；任一降级场景或无月度基准时返回 None。
        """
        # Req 9.1: 文件不存在时 sqlite3.connect 会静默新建空库，先显式检查
        if not Path(self.db_path).exists():
            logger.warning(
                "AEMO 数据库文件不可达，跳过 capture rate region-month: "
                "path=%s region=%s year_month=%s",
                self.db_path,
                region,
                year_month,
            )
            return None

        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error as exc:  # Req 9.1: 连接异常
            logger.warning(
                "连接 AEMO 数据库失败，跳过 capture rate region-month: "
                "path=%s region=%s year_month=%s err=%s",
                self.db_path,
                region,
                year_month,
                exc,
            )
            return None

        timeout_state = _install_timeout(
            conn, MonthlyBenchmarkCalculator.QUERY_TIMEOUT_SECONDS
        )
        try:
            daily = self._query_hourly_prices(conn, region, year_month)
        except sqlite3.OperationalError as exc:
            if timeout_state["timed_out"]:
                # Req 9.5: 单查询超时 -> 中止该 region-month，继续其余
                logger.warning(
                    "capture rate 查询超时（> %ss），跳过 region-month: "
                    "region=%s year_month=%s",
                    MonthlyBenchmarkCalculator.QUERY_TIMEOUT_SECONDS,
                    region,
                    year_month,
                )
                return None
            if "no such table" in str(exc).lower():
                # Req 9.2: trading_price_{year} 表缺失 -> 跳过
                logger.info(
                    "trading_price 表不存在，跳过 capture rate region-month: "
                    "region=%s year_month=%s err=%s",
                    region,
                    year_month,
                    exc,
                )
                return None
            raise
        finally:
            conn.set_progress_handler(None, _PROGRESS_HANDLER_INSTRUCTIONS)
            conn.close()

        if not daily:
            # Req 9.3: 区域-月零行 -> 排除该点
            logger.debug(
                "capture rate region-month 无数据，排除: region=%s year_month=%s",
                region,
                year_month,
            )
            return None

        # 有效日筛选（与 MonthlyBenchmarkCalculator 同口径：interval >= 200）
        min_intervals = MonthlyBenchmarkCalculator.MIN_INTERVALS_PER_DAY
        monthly_actual_revenue = 0.0
        sample_days = 0
        for bucket in daily.values():
            if int(bucket["intervals"]) < min_intervals:  # type: ignore[arg-type]
                continue
            sample_days += 1
            monthly_actual_revenue += self.compute_daily_revenue(
                bucket["prices"]  # type: ignore[arg-type]
            )

        if sample_days == 0:
            # 无有效日 -> 排除该点（Req 9.3 同款语义）
            logger.debug(
                "capture rate region-month 无有效日，排除: region=%s year_month=%s",
                region,
                year_month,
            )
            return None

        # monthly_mean_spread 复用 MonthlyBenchmarkCalculator 月度基准（有效日均值）
        benchmark = self._benchmark_calc.compute_monthly_benchmark(region, year_month)
        if benchmark is None:
            logger.debug(
                "capture rate 无可用月度基准，排除: region=%s year_month=%s",
                region,
                year_month,
            )
            return None

        capture_rate, capped = self.compute_monthly_capture_rate(
            monthly_actual_revenue=monthly_actual_revenue,
            monthly_mean_spread=benchmark.mean_spread_aud_mwh,
            days=sample_days,
            rte=self.RTE,
        )

        return CaptureRateResult(
            region=region,
            year_month=year_month,
            monthly_actual_revenue=monthly_actual_revenue,
            perfect_foresight_capture_rate=capture_rate,
            capped=capped,
            sample_days=sample_days,
        )

    # ------------------------------------------------------------------
    # 模型对比逻辑（compare_with_model 为纯逻辑，便于 Property 10/11 复用）
    # ------------------------------------------------------------------

    def compare_with_model(
        self,
        model_capture_rate: float,
        perfect_foresight_rate: float,
        region: str = "",
        year_month: str = "",
    ) -> CaptureRateComparison:
        """对比模型 capture rate 与完美预见 capture rate（纯逻辑，Req 3.6/4.1/4.3/4.4）。

        判定规则（不触碰 DB / 引擎，便于属性测试 Property 10/11 直接复用）：

        - ``violation = model_capture_rate > perfect_foresight_rate + VIOLATION_MARGIN``
          （越界当且仅当模型显著高于理论最优，Req 4.1）。
        - ``efficiency_ratio``（Req 4.3）：
            * 越界（``violation`` 为真）时置 ``None``——越界时比值无意义；
            * 非越界且 ``perfect_foresight_rate > 0`` 时 = ``model / perfect_foresight``；
            * 非越界但 ``perfect_foresight_rate <= 0`` 时置 ``None`` 并记 info（避免除零 /
              负基准产生误导性比值）。
        - ``low_efficiency_warning``（Req 4.4）：``efficiency_ratio is not None and
          efficiency_ratio < LOW_EFFICIENCY_THRESHOLD``；为真时 ``logger.warning``，
          提示模型可能低估了该 region-month 的 capture 潜力。

        Args:
            model_capture_rate: 引擎模型预测的 capture rate。
            perfect_foresight_rate: 完美预见理论最优 capture rate（已封顶 [?, 1.0]）。
            region: 区域代码（仅用于结果标注 / 日志，缺省空串）。
            year_month: 目标月份 ``'YYYY-MM'``（仅用于结果标注 / 日志，缺省空串）。

        Returns:
            CaptureRateComparison：含 region、year_month、model_capture_rate、
            perfect_foresight_capture_rate、efficiency_ratio、violation、
            low_efficiency_warning 全部字段。
        """
        violation = (
            model_capture_rate > perfect_foresight_rate + self.VIOLATION_MARGIN
        )

        efficiency_ratio: float | None
        if violation:
            # 越界时比值无意义（Req 4.3）
            efficiency_ratio = None
        elif perfect_foresight_rate > 0:
            efficiency_ratio = model_capture_rate / perfect_foresight_rate
        else:
            # 非越界但完美预见 <= 0：无法计算有意义比值，置 None 并记日志
            efficiency_ratio = None
            logger.info(
                "完美预见 capture rate <= 0，efficiency_ratio 置 None: "
                "region=%s year_month=%s pf=%s model=%s",
                region,
                year_month,
                perfect_foresight_rate,
                model_capture_rate,
            )

        low_efficiency_warning = (
            efficiency_ratio is not None
            and efficiency_ratio < self.LOW_EFFICIENCY_THRESHOLD
        )
        if low_efficiency_warning:
            # Req 4.4: 模型可能低估该 region-month 的 capture 潜力
            logger.warning(
                "efficiency_ratio (%.4f) 低于阈值 %.2f，模型可能低估 capture 潜力: "
                "region=%s year_month=%s model=%.4f pf=%.4f",
                efficiency_ratio,
                self.LOW_EFFICIENCY_THRESHOLD,
                region,
                year_month,
                model_capture_rate,
                perfect_foresight_rate,
            )

        return CaptureRateComparison(
            region=region,
            year_month=year_month,
            model_capture_rate=model_capture_rate,
            perfect_foresight_capture_rate=perfect_foresight_rate,
            efficiency_ratio=efficiency_ratio,
            violation=violation,
            low_efficiency_warning=low_efficiency_warning,
        )

    @staticmethod
    def _summarize_comparisons(
        comparisons: list[CaptureRateComparison],
    ) -> dict:
        """将逐点对比折叠为汇总报告（纯函数，Req 4.2，便于 Property 11 复用）。

        Args:
            comparisons: 逐 region-month 的 :class:`CaptureRateComparison` 列表。

        Returns:
            ``{"comparisons": [...], "violation_count": int, "violations": [...]}``，
            其中 ``violations`` 为越界明细列表，每项含 ``region`` / ``year_month`` /
            ``model_capture_rate`` / ``perfect_foresight_capture_rate``；
            ``violation_count`` 恒等于 ``violations`` 列表长度（与 ``violation`` 为真的
            对比项一一对应）。
        """
        violations = [
            {
                "region": c.region,
                "year_month": c.year_month,
                "model_capture_rate": c.model_capture_rate,
                "perfect_foresight_capture_rate": c.perfect_foresight_capture_rate,
            }
            for c in comparisons
            if c.violation
        ]
        return {
            "comparisons": list(comparisons),
            "violation_count": len(violations),
            "violations": violations,
        }

    # ------------------------------------------------------------------
    # 引擎模型取数（只读调用既有受保护成员，Req 8.1）
    # ------------------------------------------------------------------

    def _model_capture_rate(self, engine, region: str, year_month: str) -> float:
        """只读调用引擎既有 ``_compute_capture_rate`` 取模型 capture rate (Req 8.1)。

        入参（``bess_capacity_ratio`` / ``fleet_size`` / ``compression_factor``）与
        引擎既有 :meth:`ForwardPriceEngine.validate_against_benchmarks` **同源**计算，
        保证月度对比口径与 Modo 16 时段验证一致：

        - ``reference_date`` 取该 region-month 的**月末**（容量积累以月末为截止）。
        - ``bess_capacity_ratio`` = ``_get_cumulative_bess_capacity`` / ``_get_dynamic_peak_demand``。
        - ``compression_factor`` 取自 ``calculate_price_distribution``。
        - ``fleet_size`` 为该年（含）前已投运的 BESS_COMMISSIONING 事件计数。
        - 传入 ``region`` / ``month`` 启用引擎的季节修正（与 backtest 主路径一致）。

        本方法**只读**调用引擎方法，绝不修改任何受保护成员（Req 8.1）。任一引擎调用
        抛错时由调用方 :meth:`validate_all` 的 try/except 捕获并跳过该点（优雅降级）。

        Args:
            engine: ForwardPriceEngine 实例（仅做只读调用）。
            region: 区域代码。
            year_month: 目标月份 ``'YYYY-MM'``。

        Returns:
            模型预测的 capture rate。
        """
        # 延迟 import：避免对引擎模型包形成 import-time 硬依赖（与既有委托模式一致）
        from models.forward_price_models import EventType, ScenarioType

        year = int(year_month[:4])
        month = int(year_month[5:7])
        last_day = calendar.monthrange(year, month)[1]
        reference_date = date(year, month, last_day)

        bess_capacity = engine._get_cumulative_bess_capacity(
            region, ScenarioType.CENTRAL, year, reference_date=reference_date
        )
        peak_demand = engine._get_dynamic_peak_demand(region, year)
        bess_ratio = bess_capacity / peak_demand if peak_demand else 0.0

        dist = engine.calculate_price_distribution(
            region=region,
            scenario=ScenarioType.CENTRAL,
            year=year,
            bess_capacity_ratio=bess_ratio,
        )

        fleet_size = sum(
            1
            for ev in engine.event_registry.events
            if ev.region == region
            and ev.event_type == EventType.BESS_COMMISSIONING
            and engine._get_effective_event_date(ev, ScenarioType.CENTRAL).year <= year
        )

        return engine._compute_capture_rate(
            compression_factor=dist.compression_factor,
            year=year,
            bess_capacity_ratio=bess_ratio,
            fleet_size=fleet_size,
            region=region,
            month=month,
        )

    def validate_all(self, engine, end_month: str | None = None) -> dict:
        """逐 region-month 对比模型 capture rate 与完美预见值并汇总 (Req 3.4, 4.2)。

        遍历五个 NEM 区域 × 从 ``START_MONTH`` (2024-01) 连续到 ``end_month`` 的全部
        region-month（覆盖 Req 3.4 的全区域全月份迭代），逐点：

        1. 调 :meth:`compute_perfect_foresight` 取完美预见 capture rate；无数据则跳过。
        2. 只读调引擎既有 ``_compute_capture_rate``（经 :meth:`_model_capture_rate`）取
           模型 capture rate（Req 8.1）。
        3. 经 :meth:`compare_with_model` 判定 violation / efficiency_ratio。

        优雅降级：单点取数失败（引擎调用抛错 / 完美预见无数据）记日志后跳过该点，
        不中断整体迭代（Req 9 同款语义）。

        Args:
            engine: ForwardPriceEngine 实例（仅做只读调用）。
            end_month: 截止月 ``'YYYY-MM'``（含）。缺省取
                :meth:`MonthlyBenchmarkCalculator.latest_complete_month`。

        Returns:
            汇总报告 ``{"comparisons": [...], "violation_count": int, "violations": [...]}``
            （见 :meth:`_summarize_comparisons`）。无法确定截止月时返回空报告。
        """
        if end_month is None:
            end_month = self._benchmark_calc.latest_complete_month()
        if end_month is None:
            logger.warning("无法确定最新完整月，validate_all 返回空报告")
            return {"comparisons": [], "violation_count": 0, "violations": []}

        comparisons: list[CaptureRateComparison] = []
        months = MonthlyBenchmarkCalculator._enumerate_months(
            MonthlyBenchmarkCalculator.START_MONTH, end_month
        )
        for year_month in months:
            for region in MonthlyBenchmarkCalculator.NEM_REGIONS:
                pf_result = self.compute_perfect_foresight(region, year_month)
                if pf_result is None:
                    # 无完美预见数据（无数据 / 表缺失 / 超时 / 无月度基准）-> 跳过
                    continue
                try:
                    model_capture_rate = self._model_capture_rate(
                        engine, region, year_month
                    )
                except Exception as exc:  # noqa: BLE001 — 优雅降级，单点失败不中断
                    logger.warning(
                        "模型 capture rate 取数失败，跳过 region-month: "
                        "region=%s year_month=%s err=%s",
                        region,
                        year_month,
                        exc,
                    )
                    continue
                comparisons.append(
                    self.compare_with_model(
                        model_capture_rate=model_capture_rate,
                        perfect_foresight_rate=pf_result.perfect_foresight_capture_rate,
                        region=region,
                        year_month=year_month,
                    )
                )

        return self._summarize_comparisons(comparisons)


# =============================================================================
# 月度基准验证 (Req 2)
# =============================================================================

# Hit Rate 命中阈值：|deviation_pct| <= 30% 视为命中 (Req 2.4)
_HIT_RATE_THRESHOLD_PCT: float = 30.0


def _deviation_pct(model: float, benchmark: float) -> float:
    """偏差百分比纯函数 (Req 2.3，便于 Property 5 复用)。

    ``deviation_pct = (model - benchmark) / benchmark × 100``

    当 ``model > benchmark`` 时符号为正、``model < benchmark`` 时为负。本函数与
    DB / 引擎完全解耦，便于属性测试（Property 5）直接复用。

    Args:
        model: 模型预测值。
        benchmark: 基准值（调用方须保证非零；为零时会抛 ZeroDivisionError，
            由调用方在循环中预先过滤，见 :func:`validate_against_monthly_benchmarks_impl`）。

    Returns:
        偏差百分比（浮点）。
    """
    return (model - benchmark) / benchmark * 100.0


def _aggregate_deviation_metrics(deviations: list[float]) -> dict:
    """聚合偏差指标纯函数 (Req 2.4，便于 Property 6 复用)。

    对一组 ``deviation_pct`` 计算：

    - ``mape`` = ``mean(|d|)``           —— 始终 ≥ 0
    - ``rmse`` = ``sqrt(mean(d²))``      —— 始终 ≥ ``|bias|``
    - ``bias`` = ``mean(d)``
    - ``hit_rate`` = ``|d| ≤ 30`` 的元素占比百分比 —— 落在 ``[0, 100]``

    本函数不做任何取整，保留完整精度以满足 Property 6 的数学不变量断言；
    调用方如需展示可在边界处自行取整。

    Args:
        deviations: 各数据点的 ``deviation_pct`` 列表。

    Returns:
        ``{"mape": float, "rmse": float, "bias": float, "hit_rate": float, "count": int}``；
        空列表时各指标为 ``0.0``、``count`` 为 ``0``。
    """
    count = len(deviations)
    if count == 0:
        return {"mape": 0.0, "rmse": 0.0, "bias": 0.0, "hit_rate": 0.0, "count": 0}
    abs_devs = [abs(d) for d in deviations]
    mape = sum(abs_devs) / count
    rmse = (sum(d * d for d in deviations) / count) ** 0.5
    bias = sum(deviations) / count
    hits = sum(1 for d in abs_devs if d <= _HIT_RATE_THRESHOLD_PCT)
    hit_rate = hits / count * 100.0
    return {
        "mape": mape,
        "rmse": rmse,
        "bias": bias,
        "hit_rate": hit_rate,
        "count": count,
    }


def _model_mean_spread(engine, region: str, year_month: str) -> float:
    """只读调用引擎既有方法取该 region-month 的模型 mean_spread (Req 2.2, 8.1)。

    入参（``bess_capacity_ratio``）与引擎既有
    :meth:`ForwardPriceEngine.validate_against_benchmarks` 及本模块
    :meth:`CaptureRateCalculator._model_capture_rate` **同源**构造，保证月度验证口径
    与 Modo 16 时段验证一致：

    - ``reference_date`` 取该 region-month 的**月末**（容量积累以月末为截止）。
    - ``bess_capacity_ratio`` = ``_get_cumulative_bess_capacity`` / ``_get_dynamic_peak_demand``。
    - 调 ``calculate_price_distribution(region, CENTRAL, year, bess_ratio)`` 取
      ``mean_spread``（含 ML 校准与 BESS 压缩）。

    本函数**只读**调用引擎方法，绝不修改任何受保护成员（Req 8.1）。引擎调用抛错时
    由调用方 :func:`validate_against_monthly_benchmarks_impl` 的 try/except 捕获并跳过
    该点（Req 9 优雅降级）。

    **模型粒度说明：** ``calculate_price_distribution`` 是年度粒度，对同年各月仅随容量
    参考日略变，故同年不同月返回的 ``mean_spread`` 接近一致；月度验证因此度量"年度模型
    预测 vs 各月实测"的偏差，能暴露模型缺失的季节性（设计已知限制）。

    Args:
        engine: ForwardPriceEngine 实例（仅做只读调用）。
        region: 区域代码（NSW1 / QLD1 / SA1 / TAS1 / VIC1）。
        year_month: 目标月份 ``'YYYY-MM'``。

    Returns:
        模型预测的 ``mean_spread``（AUD/MWh）。
    """
    # 延迟 import：避免对引擎模型包形成 import-time 硬依赖（与既有委托模式一致）
    from models.forward_price_models import ScenarioType

    year = int(year_month[:4])
    month = int(year_month[5:7])
    last_day = calendar.monthrange(year, month)[1]
    reference_date = date(year, month, last_day)

    bess_capacity = engine._get_cumulative_bess_capacity(
        region, ScenarioType.CENTRAL, year, reference_date=reference_date
    )
    peak_demand = engine._get_dynamic_peak_demand(region, year)
    bess_ratio = bess_capacity / peak_demand if peak_demand else 0.0

    dist = engine.calculate_price_distribution(
        region=region,
        scenario=ScenarioType.CENTRAL,
        year=year,
        bess_capacity_ratio=bess_ratio,
    )
    return dist.mean_spread


def validate_against_monthly_benchmarks_impl(
    engine, end_month: str | None = None, target_month: str | None = None
) -> dict:
    """月度基准验证实现：对比模型 mean_spread 与 AEMO 月度基准 (Req 2.2-2.5)。

    流程：

    1. 用 :meth:`MonthlyBenchmarkCalculator.compute_all_benchmarks` 取所有基准，过滤掉
       ``data_quality_flag == "insufficient_data"`` 的月（Req 1.5、2.2）。给定
       ``target_month`` 时只对该月的五区域逐点计算基准（供任务 7 reconciliation 复用）。
    2. 对每个有效 region-month，经 :func:`_model_mean_spread` 只读调用引擎既有
       ``calculate_price_distribution`` 取模型 ``mean_spread``（``bess_ratio`` 与
       ``validate_against_benchmarks`` 同源，Req 2.2）。
    3. ``deviation_pct = (model - benchmark) / benchmark × 100``（经 :func:`_deviation_pct`，
       Req 2.3）。
    4. 聚合 MAPE、RMSE、Bias、Hit Rate（经 :func:`_aggregate_deviation_metrics`，Req 2.4）。
    5. 返回与引擎既有 ``validate_against_benchmarks`` **兼容**的结构：顶层含 ``results``
       （per-point 列表）、``all_within_threshold``、``max_deviation_pct``，并附加
       ``summary``（MAPE/RMSE/Bias/Hit Rate/count）供月度验证使用（Req 2.5）。

    优雅降级（Req 9）：单点 ``calculate_price_distribution`` 抛错或基准为零时记日志后
    跳过该点继续聚合，绝不中断整体验证。

    Args:
        engine: ForwardPriceEngine 实例（仅做只读调用）。
        end_month: 截止月 ``'YYYY-MM'``（含）。缺省取最新完整月；当 ``target_month``
            给定时本参数被忽略。
        target_month: 给定时只验证该月（``'YYYY-MM'``，供 reconciliation 复用）。

    Returns:
        {
            "results": [{"region", "year_month", "model_mean_spread",
                         "benchmark_mean_spread", "deviation_pct"}, ...],
            "all_within_threshold": bool,   # 全部点 |deviation| <= 30%
            "max_deviation_pct": float,     # 最大 |deviation|
            "summary": {"mape", "rmse", "bias", "hit_rate", "count"},
        }
    """
    calc = MonthlyBenchmarkCalculator()

    # Step 1: 取基准。target_month 给定时只算该月五区域；否则枚举全量。
    if target_month is not None:
        benchmarks: list[MonthlyBenchmark] = []
        for region in calc.NEM_REGIONS:
            benchmark = calc.compute_monthly_benchmark(region, target_month)
            if benchmark is not None:
                benchmarks.append(benchmark)
    else:
        benchmarks = calc.compute_all_benchmarks(end_month)

    # 过滤 insufficient_data 月（Req 1.5、2.2），不参与对比
    valid_benchmarks = [
        b for b in benchmarks if b.data_quality_flag != "insufficient_data"
    ]

    results: list[dict] = []
    deviations: list[float] = []

    for b in valid_benchmarks:
        benchmark_spread = b.mean_spread_aud_mwh
        if benchmark_spread == 0:
            # 基准为零无法计算偏差百分比 -> 跳过该点（Req 9 优雅降级）
            logger.debug(
                "月度基准 mean_spread 为零，跳过 region-month: region=%s year_month=%s",
                b.region,
                b.year_month,
            )
            continue

        # Step 2: 只读调引擎取模型 mean_spread；单点抛错跳过继续聚合（Req 9）
        try:
            model_spread = _model_mean_spread(engine, b.region, b.year_month)
        except Exception as exc:  # noqa: BLE001 — 优雅降级，单点失败不中断聚合
            logger.warning(
                "模型 mean_spread 取数失败，跳过 region-month: "
                "region=%s year_month=%s err=%s",
                b.region,
                b.year_month,
                exc,
            )
            continue

        # Step 3: deviation_pct
        dev = _deviation_pct(model_spread, benchmark_spread)
        deviations.append(dev)

        point = MonthlyValidationResult(
            region=b.region,
            year_month=b.year_month,
            model_mean_spread=model_spread,
            benchmark_mean_spread=benchmark_spread,
            deviation_pct=dev,
        )
        results.append(
            {
                "region": point.region,
                "year_month": point.year_month,
                "model_mean_spread": round(point.model_mean_spread, 2),
                "benchmark_mean_spread": round(point.benchmark_mean_spread, 2),
                "deviation_pct": round(point.deviation_pct, 1),
            }
        )

    # Step 4: 聚合指标（纯函数，保留完整精度）
    summary = _aggregate_deviation_metrics(deviations)

    # Step 5: 与 validate_against_benchmarks 兼容的顶层字段
    max_deviation = max((abs(d) for d in deviations), default=0.0)
    all_within = all(abs(d) <= _HIT_RATE_THRESHOLD_PCT for d in deviations)

    return {
        "results": results,
        "all_within_threshold": all_within,
        "max_deviation_pct": round(max_deviation, 1),
        "summary": summary,
    }


# =============================================================================
# 月度 Reconciliation 入口 (Req 5, 6)
# =============================================================================

# 偏差告警阈值：``|deviation_pct| > 40%`` 触发告警 (Req 5.5)。抽为模块级常量并配套
# 纯函数 :func:`is_deviation_alert`，便于任务 7.4 单元测试断言与回测脚本 Section I
# (Req 7) 复用同一阈值口径，避免魔法数字散落。
DEVIATION_ALERT_THRESHOLD_PCT: float = 40.0


def is_deviation_alert(deviation_pct: float) -> bool:
    """判定单点偏差是否触发告警（纯函数，Req 5.5）。

    ``alert_triggered = abs(deviation_pct) > DEVIATION_ALERT_THRESHOLD_PCT``
    （**严格大于** 40%，恰好 40% 不触发）。本函数与 DB / 引擎完全解耦，便于单元测试
    （任务 7.4 的 40% 边界断言）与回测脚本复用同一判定口径。

    Args:
        deviation_pct: 单 region-month 的偏差百分比（可正可负）。

    Returns:
        ``True`` 当且仅当偏差绝对值严格超过 ``DEVIATION_ALERT_THRESHOLD_PCT``。
    """
    return abs(deviation_pct) > DEVIATION_ALERT_THRESHOLD_PCT


def _previous_calendar_month(today: date | None = None) -> str:
    """返回相对 ``today``（默认当前系统日期）的上一个日历月 ``'YYYY-MM'``（纯函数）。

    取本月 1 日减一天即落入上月，再格式化为 ``'YYYY-MM'``，天然跨年正确
    （1 月 → 上年 12 月）。
    """
    if today is None:
        today = date.today()
    last_of_prev_month = date(today.year, today.month, 1) - timedelta(days=1)
    return f"{last_of_prev_month.year:04d}-{last_of_prev_month.month:02d}"


def _resolve_target_month(calc: MonthlyBenchmarkCalculator) -> str:
    """解析 reconciliation 默认目标月——"上一个完整日历月"（含口径取舍说明）。

    需求 5.2 将默认目标月定义为"上一个日历月"，但实测数据可能滞后于日历（如月初对账
    时上月数据尚未入库完整）。为兼顾"日历语义"与"数据可得性"，本实现取以下两者中
    **较早**者（按 ``'YYYY-MM'`` 字典序，零填充等价于时间序）：

    - ``_previous_calendar_month()``：相对当前系统日期的日历上月（Req 5.2 字面语义）；
    - ``MonthlyBenchmarkCalculator.latest_complete_month()``：AEMO_Database 中数据覆盖
      到月末的最新完整月（数据可得性下界）。

    取较早者可保证目标月既不晚于日历上月、又不超出已有完整数据范围，使对账始终落在
    "有实测可比"的月份上；若无法探测数据覆盖（``latest_complete_month`` 返回 None），
    则回退到纯日历上月。

    Args:
        calc: 复用的 :class:`MonthlyBenchmarkCalculator`（用于探测数据覆盖）。

    Returns:
        目标月 ``'YYYY-MM'``。
    """
    prev_calendar = _previous_calendar_month()
    latest_complete = calc.latest_complete_month()
    if latest_complete is None:
        return prev_calendar
    return min(prev_calendar, latest_complete)


def _build_capture_rate_comparison(
    capture_calc: "CaptureRateCalculator",
    engine,
    region: str,
    year_month: str,
) -> dict | None:
    """为单区域组装 model vs perfect_foresight 的 capture rate 对比 (Req 5.3, 6.3)。

    复用 :class:`CaptureRateCalculator` 既有能力：

    1. :meth:`CaptureRateCalculator.compute_perfect_foresight` 取完美预见 capture rate；
    2. :meth:`CaptureRateCalculator._model_capture_rate` 只读调引擎取模型 capture rate
       （Req 8.1，绝不修改受保护成员）；
    3. :meth:`CaptureRateCalculator.compare_with_model` 判定 violation / efficiency_ratio。

    优雅降级（Req 9）：完美预见无数据（返回 None）或模型取数 / 对比抛错时，记日志后
    返回 ``None``——该区域 ``capture_rate_comparison`` 字段置 None，不中断整体对账。

    Returns:
        ``{"model", "perfect_foresight", "efficiency_ratio", "violation"}`` 字典；
        无法计算时返回 ``None``。
    """
    try:
        pf_result = capture_calc.compute_perfect_foresight(region, year_month)
        if pf_result is None:
            logger.debug(
                "无完美预见 capture rate，capture_rate_comparison 置 None: "
                "region=%s year_month=%s",
                region,
                year_month,
            )
            return None
        model_capture_rate = capture_calc._model_capture_rate(
            engine, region, year_month
        )
        comparison = capture_calc.compare_with_model(
            model_capture_rate=model_capture_rate,
            perfect_foresight_rate=pf_result.perfect_foresight_capture_rate,
            region=region,
            year_month=year_month,
        )
    except Exception as exc:  # noqa: BLE001 — 优雅降级，单点失败不中断对账
        logger.warning(
            "capture rate 对比取数失败，capture_rate_comparison 置 None: "
            "region=%s year_month=%s err=%s",
            region,
            year_month,
            exc,
        )
        return None

    return {
        "model": round(comparison.model_capture_rate, 4),
        "perfect_foresight": round(
            comparison.perfect_foresight_capture_rate, 4
        ),
        "efficiency_ratio": (
            round(comparison.efficiency_ratio, 4)
            if comparison.efficiency_ratio is not None
            else None
        ),
        "violation": comparison.violation,
    }


# =============================================================================
# JSON 归档 append 写入 (Req 5.4, 6.1, 6.2, 6.3, 6.4)
# =============================================================================

# 归档文件相对仓库根的路径片段；实际绝对路径经 :func:`_reconciliation_report_path`
# 基于 ``_REPO_ROOT`` 推导，保证与既有 ``reports/`` 产物同源、与运行工作目录无关。
_RECONCILIATION_REPORT_RELPATH = ("reports", "monthly_reconciliation.json")


def _reconciliation_report_path() -> Path:
    """解析对账归档文件的绝对路径 ``<repo>/reports/monthly_reconciliation.json``。

    参照模块内既有 ``_REPO_ROOT`` 推导，使归档落点与运行时工作目录无关，
    与 ``reports/`` 下其他回测产物同源。

    Returns:
        归档文件的绝对 :class:`Path`。
    """
    return _REPO_ROOT.joinpath(*_RECONCILIATION_REPORT_RELPATH)


def _append_reconciliation_record(existing: list, record: dict) -> list:
    """将新对账记录追加到既有数组末尾（纯函数，Req 5.4, 6.2）。

    返回 ``existing + [record]``：长度恰好加一、所有历史记录按原顺序原值保留、
    新记录追加在末尾。本函数与文件 I/O 完全解耦，便于任务 7.3（Property 12）属性测试
    直接复用，且不修改入参 ``existing``（返回新列表）。

    Args:
        existing: 既有历史记录数组（可为空列表起点）。
        record: 本次新对账记录。

    Returns:
        追加新记录后的新列表 ``existing + [record]``。
    """
    return [*existing, record]


def _load_existing_records(report_path: Path) -> list:
    """读取既有归档数组；文件缺失或损坏时返回空列表（Req 6.2, 6.4）。

    - 文件不存在 → 返回 ``[]``（由调用方 append 后写出，等价于"初始化空数组再 append"，
      Req 6.4）。
    - JSON 损坏（``json.JSONDecodeError``）→ 记 ``logger.warning``，以空数组重建（保护性，
      保证本次新记录不因历史文件损坏而丢失，Req 6.2）。
    - 顶层不是数组（既有文件结构异常）→ 同样记 warning 以空数组重建。

    Args:
        report_path: 归档文件绝对路径。

    Returns:
        既有记录列表；缺失 / 损坏 / 结构异常时为空列表。
    """
    if not report_path.exists():
        return []
    try:
        with report_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.warning(
            "对账归档 JSON 损坏，以空数组重建（不丢失本次新记录）: path=%s err=%s",
            report_path,
            exc,
        )
        return []
    if not isinstance(data, list):
        logger.warning(
            "对账归档顶层非数组，以空数组重建: path=%s type=%s",
            report_path,
            type(data).__name__,
        )
        return []
    return data


def _write_reconciliation_record(
    record: dict, report_path: str | Path | None = None
) -> Path:
    """将单条对账记录 append 写入归档文件，保留全部历史记录 (Req 5.4, 6.1-6.4)。

    读改写流程：

    1. 解析归档路径：``report_path`` 缺省取 :func:`_reconciliation_report_path`
       （``<repo>/reports/monthly_reconciliation.json``）。
    2. ``reports`` 目录不存在 → ``mkdir(parents=True, exist_ok=True)`` 创建（Req 6.4）。
    3. 读取既有数组（经 :func:`_load_existing_records`，文件缺失→空数组、损坏→空数组重建）。
    4. 经纯函数 :func:`_append_reconciliation_record` 追加本次记录。
    5. 以 UTF-8 / ``ensure_ascii=False``（保留中文可读性）/ ``indent=2`` 写回。

    Args:
        record: 本次对账记录（结构见 :func:`run_monthly_reconciliation` 返回值）。
        report_path: 归档文件路径。缺省写入 ``<repo>/reports/monthly_reconciliation.json``；
            测试可传入临时路径以隔离写入位置。

    Returns:
        实际写入的归档文件绝对 :class:`Path`。
    """
    path = Path(report_path) if report_path is not None else _reconciliation_report_path()

    # Req 6.4: reports 目录不存在时创建（含多级父目录）
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_existing_records(path)
    updated = _append_reconciliation_record(existing, record)

    with path.open("w", encoding="utf-8") as fh:
        json.dump(updated, fh, ensure_ascii=False, indent=2)

    return path


def run_monthly_reconciliation(
    target_month: str | None = None, report_path: str | Path | None = None
) -> dict:
    """月度对账主入口：组装单月 reconciliation 记录 (Req 5.2, 5.3, 5.5, 6.1, 6.3)。

    流程：

    1. 解析目标月：``target_month`` 缺省取**上一个完整日历月**（见
       :func:`_resolve_target_month` 的口径取舍——取"日历上月"与"数据可得最新完整月"
       中较早者）。
    2. 构造 :class:`ForwardPriceEngine` 实例（延迟 import，避免 import-time 硬依赖，
       与引擎委托方法同款风格）。
    3. 调 :func:`validate_against_monthly_benchmarks_impl`（限定 ``target_month``）取该月
       逐区域 deviation 结果（model vs actual mean_spread，Req 5.3）。
    4. 逐区域附加 capture rate 对比（model vs perfect_foresight / efficiency_ratio /
       violation，经 :func:`_build_capture_rate_comparison`，Req 5.3, 6.3）。
    5. 计算 summary：``mape`` / ``max_deviation`` / ``violation_count``（Req 6.1）。
    6. ``|deviation| > 40%`` → 该区域 ``alert_triggered=True`` 且 ``logger.warning``
       （含 region、month、model、actual、deviation%，Req 5.5）。
    7. 经 :func:`_write_reconciliation_record` 将记录 **append 写入**
       ``reports/monthly_reconciliation.json``，保留全部历史记录（Req 5.4, 6.2, 6.4）；
       文件不存在则初始化空数组再 append、JSON 损坏则以空数组重建（不丢失本次记录）。
       写盘后**仍返回**该记录 dict（结构不变，供测试断言与调用方使用）。

    优雅降级（Req 9）：单区域 capture rate 取数失败时该区域 ``capture_rate_comparison``
    置 None 并记日志，不中断其余区域；deviation 取数失败由
    :func:`validate_against_monthly_benchmarks_impl` 内部 try/except 跳过。

    Args:
        target_month: 目标月 ``'YYYY-MM'``。缺省取上一个完整日历月。
        report_path: 归档文件路径。缺省写入
            ``<repo>/reports/monthly_reconciliation.json``（默认行为必写盘）；
            测试可传入临时路径以隔离写入位置。

    Returns:
        reconciliation 记录 dict：

        - ``run_date``：对账运行时刻（ISO8601，UTC 时区）。
        - ``target_month``：目标月 ``'YYYY-MM'``。
        - ``results``：per-region 列表，每项含 ``region`` / ``model_mean_spread`` /
          ``actual_mean_spread`` / ``deviation_pct`` / ``capture_rate_comparison`` /
          ``alert_triggered``（Req 6.3）。
        - ``summary``：``{"mape", "max_deviation", "violation_count"}``（Req 6.1）。
    """
    benchmark_calc = MonthlyBenchmarkCalculator()
    if target_month is None:
        target_month = _resolve_target_month(benchmark_calc)

    # Step 2: 构造引擎实例（延迟 import，零 import-time 硬依赖）
    from engines.forward_price_engine import ForwardPriceEngine

    engine = ForwardPriceEngine()

    # Step 3: 月度基准验证，限定 target_month（逐区域 deviation：model vs actual）
    validation = validate_against_monthly_benchmarks_impl(
        engine, target_month=target_month
    )

    # Step 4 + 6: 逐区域附 capture rate 对比并判定告警
    capture_calc = CaptureRateCalculator()
    results: list[dict] = []
    violation_count = 0

    for point in validation["results"]:
        region = point["region"]
        model_mean_spread = point["model_mean_spread"]
        actual_mean_spread = point["benchmark_mean_spread"]
        deviation_pct = point["deviation_pct"]

        capture_rate_comparison = _build_capture_rate_comparison(
            capture_calc, engine, region, target_month
        )
        if capture_rate_comparison is not None and capture_rate_comparison["violation"]:
            violation_count += 1

        alert_triggered = is_deviation_alert(deviation_pct)
        if alert_triggered:
            # Req 5.5: |deviation| > 40% → 告警，含 region / month / model / actual / dev%
            logger.warning(
                "月度对账偏差超阈值 (>%.0f%%)：region=%s month=%s model=%.2f "
                "actual=%.2f deviation=%.1f%%",
                DEVIATION_ALERT_THRESHOLD_PCT,
                region,
                target_month,
                model_mean_spread,
                actual_mean_spread,
                deviation_pct,
            )

        results.append(
            {
                "region": region,
                "model_mean_spread": model_mean_spread,
                "actual_mean_spread": actual_mean_spread,
                "deviation_pct": deviation_pct,
                "capture_rate_comparison": capture_rate_comparison,
                "alert_triggered": alert_triggered,
            }
        )

    # Step 5: summary（MAPE / max_deviation / violation_count，Req 6.1）
    summary = {
        "mape": round(validation["summary"]["mape"], 1),
        "max_deviation": validation["max_deviation_pct"],
        "violation_count": violation_count,
    }

    # 组装 reconciliation 记录（结构见 docstring，Req 6.1/6.3）
    record = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "target_month": target_month,
        "results": results,
        "summary": summary,
    }

    # Step 7: append 写入归档文件，保留全部历史记录（Req 5.4, 6.2, 6.4）；
    # 写盘后仍返回该记录 dict（结构不变，供测试断言与调用方使用）。
    _write_reconciliation_record(record, report_path)

    return record
