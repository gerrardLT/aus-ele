"""Agent Tool Registry.

Wraps existing AEMO Intelligence analysis engines as callable tools
in OpenAI function-calling format. Each tool maps to an existing engine
or route-level function, preserving the project's current architecture.

Tools are organized by decision funnel stage:
- Stage 1: Market Screening (market_screening, price_trend, regional_ranking)
- Stage 2: Revenue Deep Dive (spike_profit, peak_analysis, fcas_analysis)
- Stage 3: Saturation & Competition (saturation_check)
- Stage 4: Investment Outlook (cannibalization, fcas_collapse, regional_timing, merchant_risk, forward_spread)
- Stage 5: Co-Optimized Backtest (co_optimized_backtest)
- Stage 6: Financial Modeling (investment_analysis, risk_stratification, cross_validation, narrative)
- Global: grid_forecast, data_quality_check
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from typing import Any, Callable, Dict, List, Optional

from agent.schemas import AgentContext, ToolDefinition, ToolResult, ToolStatus
from agent.tools_whitelist import _exec_data_query_safe

logger = logging.getLogger(__name__)


def _safe_year(year: Any) -> int:
    """Coerce ``year`` to a plausible 4-digit int.

    Guards against SQL injection: ``year`` is interpolated into the
    ``trading_price_<year>`` table name (not a bound parameter), so any
    non-integer or out-of-range value must be rejected before it reaches SQL.
    Raises ValueError so the tool is marked ERROR rather than executing
    tainted SQL.
    """
    try:
        y = int(year)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid year parameter: {year!r}")
    if not (2000 <= y <= 2100):
        raise ValueError(f"Year out of range: {y}")
    return y


def _price_table_exists(db, table_name: str) -> bool:
    """检查分年价格表是否存在（P0：目标年表缺失容错）。

    基线计量（2026-08-06）发现线上失败 Top1 是 trading_price_<year> 表缺失时
    抛出裸 SQL 错误进入工具错误流。提前检查并让工具返回结构化 no_data，
    使 LLM 与综合器能优雅处理（orchestrator 会将其提取为风险标记）而非报错。
    检测自身失败时返回 True，交由原查询暴露真实错误，避免连接性问题被误判为缺数据。
    """
    try:
        with db.get_connection() as conn:
            return db._table_exists(conn, table_name)
    except Exception:
        return True


# =============================================================================
# Tool Executor Type
# =============================================================================

# Each tool executor takes (params: dict, context: AgentContext) and returns dict
ToolExecutor = Callable[[Dict[str, Any], AgentContext], Dict[str, Any]]


# =============================================================================
# Tool Registry
# =============================================================================


class ToolRegistry:
    """Registry of all available agent tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._executors: Dict[str, ToolExecutor] = {}

    def register(
        self,
        definition: ToolDefinition,
        executor: ToolExecutor,
    ) -> None:
        """Register a tool with its definition and executor function."""
        self._tools[definition.name] = definition
        self._executors[definition.name] = executor

    def get_definition(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_executor(self, name: str) -> Optional[ToolExecutor]:
        return self._executors.get(name)

    def list_definitions(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def to_openai_tools(self, visible: Optional[set] = None) -> List[Dict[str, Any]]:
        """Convert all tool definitions to OpenAI tools format.

        Args:
            visible: 可选可见集（PoC 按阶段子集暴露）。为 None 时返回全量；
                非 None 时仅返回名称在集合内的工具 schema。
        """
        tools = self._tools.values()
        if visible is not None:
            tools = [t for t in tools if t.name in visible]
        return [tool.to_openai_schema() for tool in tools]

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: AgentContext,
        call_id: str = "",
        timeout_seconds: float = 30.0,
    ) -> ToolResult:
        """Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool parameters.
            context: Agent execution context.
            call_id: Tool call ID for LLM conversation tracking.
            timeout_seconds: Maximum execution time.

        Returns:
            ToolResult with status, data, and timing.
        """
        executor = self._executors.get(tool_name)
        if executor is None:
            return ToolResult(
                tool_name=tool_name,
                call_id=call_id,
                status=ToolStatus.ERROR,
                error_message=f"Unknown tool: {tool_name}",
            )

        start = time.perf_counter()
        
        # Create task and shield it from cancellation to prevent thread leak
        if asyncio.iscoroutinefunction(executor):
            async def _exec_coro():
                return await executor(arguments, context)
            task = asyncio.create_task(_exec_coro())
        else:
            loop = asyncio.get_running_loop()
            async def _exec_sync():
                return await loop.run_in_executor(None, executor, arguments, context)
            task = asyncio.create_task(_exec_sync())
        
        try:
            # Use asyncio.wait with timeout for explicit cancellation control
            data, _ = await asyncio.wait(
                {task},
                timeout=timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            if not data:
                raise asyncio.TimeoutError(f"Tool {tool_name} exceeded {timeout_seconds}s")
                
            result_task = data.pop()
            if isinstance(result_task.exception(), asyncio.CancelledError):
                # Task was cancelled due to timeout - mark as TIMEOUT instead of ERROR
                duration_ms = (time.perf_counter() - start) * 1000
                logger.warning("Tool %s timed out after %.1fs", tool_name, timeout_seconds)
                return ToolResult(
                    tool_name=tool_name,
                    call_id=call_id,
                    status=ToolStatus.TIMEOUT,
                    error_message=f"Tool execution timed out after {timeout_seconds}s",
                    duration_ms=round(duration_ms, 1),
                )
                
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                call_id=call_id,
                status=ToolStatus.SUCCESS,
                data=result_task.result(),
                metadata={"duration_ms": round(duration_ms, 1)},
                duration_ms=round(duration_ms, 1),
            )
            
        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning("Tool %s timed out after %.1fs", tool_name, timeout_seconds)
            # Cancel the task explicitly (this is now safe because we created it ourselves)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # Expected
            
            return ToolResult(
                tool_name=tool_name,
                call_id=call_id,
                status=ToolStatus.TIMEOUT,
                error_message=f"Tool execution timed out after {timeout_seconds}s",
                duration_ms=round(duration_ms, 1),
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
            return ToolResult(
                tool_name=tool_name,
                call_id=call_id,
                status=ToolStatus.ERROR,
                error_message=str(exc),
                duration_ms=round(duration_ms, 1),
            )


# =============================================================================
# Tool Executor Implementations
# =============================================================================


# =============================================================================
# Chart builders（图表功能激活，2026-08-10）
# 工具结果自动附带 chart 负载，编排器经 tool_result.chart 透传到前端
# ChartRenderer（line/bar/scatter/area，≤200 点）。构建器均防御式：
# 数据不足返回 None，绝不抛错，不影响工具主流程。
# =============================================================================

_CHART_MAX_POINTS = 200


def _downsample_chart_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """等间距降采样保序（与回测降采样同策略）。"""
    if len(points) <= _CHART_MAX_POINTS:
        return points
    stride = math.ceil(len(points) / _CHART_MAX_POINTS)
    return points[::stride]


def _chart_price_trend(rows, region: str, year: int) -> Optional[Dict[str, Any]]:
    """30 分钟价格 → 日均价折线图。rows: [(settlement_date, rrp_aud_mwh), ...]"""
    if not rows:
        return None
    daily: Dict[str, list] = {}
    for r in rows:
        day = str(r[0])[:10]
        try:
            daily.setdefault(day, []).append(float(r[1] or 0.0))
        except (TypeError, ValueError):
            continue
    points = [
        {"x": day, "y": round(sum(v) / len(v), 2)}
        for day, v in sorted(daily.items())
    ]
    points = _downsample_chart_points(points)
    if len(points) < 2:
        return None
    return {
        "type": "line",
        "title": f"{region} {year} 日均价趋势",
        "x_label": "日期",
        "y_label": "AUD/MWh",
        "data": points,
    }


def _chart_market_screening(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """区域筛选评分条形图（按得分降序取前 8）。"""
    from agent.tool_contracts import SCREENING_ITEMS_KEY

    items = payload.get(SCREENING_ITEMS_KEY) or []
    rows = []
    for it in items:
        score = it.get("overall_score")
        if score is None:
            continue
        label = str(it.get("label") or it.get("region") or "?")
        rows.append({"x": label, "y": round(float(score), 1)})
    rows.sort(key=lambda r: r["y"], reverse=True)
    rows = rows[:8]
    if len(rows) < 2:
        return None
    return {
        "type": "bar",
        "title": "区域投资筛选评分",
        "x_label": "区域",
        "y_label": "综合得分",
        "data": rows,
    }


_FCAS_SERVICE_COLS = [
    "raise1sec_rrp", "raise6sec_rrp", "raise60sec_rrp", "raise5min_rrp", "raisereg_rrp",
    "lower1sec_rrp", "lower6sec_rrp", "lower60sec_rrp", "lower5min_rrp", "lowerreg_rrp",
]


def _chart_fcas_services(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """FCAS 各服务均价条形图（防御式：无有效列返回 None）。"""
    if not rows:
        return None
    points = []
    for col in _FCAS_SERVICE_COLS:
        vals = [float(r.get(col) or 0.0) for r in rows if r.get(col) is not None]
        if not vals:
            continue
        points.append({"x": col.replace("_rrp", ""), "y": round(sum(vals) / len(vals), 2)})
    if not any(p["y"] != 0 for p in points):
        return None
    return {
        "type": "bar",
        "title": "FCAS 各服务均价",
        "x_label": "服务",
        "y_label": "AUD/MWh",
        "data": points,
    }


def _chart_coopt_monthly(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """联合优化回测月度净收益条形图（month_index → M1..Mn）。"""
    mb = payload.get("monthly_breakdown") or []
    points = []
    for m in mb:
        total = m.get("total_net_revenue")
        if total is None:
            total = (m.get("energy_revenue") or 0.0) + (m.get("fcas_revenue") or 0.0)
        try:
            points.append({"x": f"M{m.get('month_index', len(points) + 1)}", "y": round(float(total), 0)})
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return None
    return {
        "type": "bar",
        "title": "联合优化回测月度净收益",
        "x_label": "月份",
        "y_label": "AUD",
        "data": points,
    }


def _exec_market_screening(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute market screening across all regions."""
    from deps import get_db
    from market_screening import build_market_screening_payload

    db = get_db()
    year = params.get("year", ctx.effective_year)
    payload = build_market_screening_payload(db, year=year)
    chart = _chart_market_screening(payload)
    if chart:
        payload = {**payload, "chart": chart}
    return payload


def _exec_price_trend(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute price trend analysis for a region."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    year = _safe_year(year)
    table_name = f"trading_price_{year}"

    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "note": f"价格表 trading_price_{year} 尚未同步"}

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
            f"WHERE region_id = ? ORDER BY settlement_date ASC",
            (region,),
        )
        rows = cursor.fetchall()

    if not rows:
        return {"region": region, "year": year, "total_points": 0, "stats": {}, "data": []}

    prices = [float(r[1] or 0.0) for r in rows]
    from statistics import mean, stdev

    stats = {
        "avg_price": round(mean(prices), 2),
        "max_price": round(max(prices), 2),
        "min_price": round(min(prices), 2),
        "std_dev": round(stdev(prices), 2) if len(prices) > 1 else 0.0,
        "negative_ratio_pct": round(sum(1 for p in prices if p < 0) / len(prices) * 100, 2),
        "total_points": len(prices),
    }
    result = {"region": region, "year": year, "stats": stats}
    chart = _chart_price_trend(rows, region, year)
    if chart:
        result["chart"] = chart
    return result


def _exec_regional_ranking(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute regional investment ranking."""
    from deps import get_db
    from market_screening import build_market_screening_payload

    db = get_db()
    year = params.get("year", ctx.effective_year)
    payload = build_market_screening_payload(db, year=year)
    # Filter to NEM regions only for ranking.
    # bug 修复 2026-07-29：build_market_screening_payload 返回的键是 "items"，
    # 之前误取 "candidates" 导致永远返回空列表（candidates=0）。
    # P1：现改用 tool_contracts 契约常量，生产者/消费者单一来源，根除字段漂移。
    from agent.tool_contracts import (
        REGIONAL_RANKING_KEY,
        REGIONAL_TOTAL_KEY,
        SCREENING_ITEMS_KEY,
        SCREENING_MARKET_KEY,
    )
    candidates = payload.get(SCREENING_ITEMS_KEY, [])
    nem_ranked = [c for c in candidates if c.get(SCREENING_MARKET_KEY) == "NEM"]
    return {
        "year": year,
        REGIONAL_RANKING_KEY: nem_ranked,
        REGIONAL_TOTAL_KEY: len(candidates),
    }


def _exec_spike_profit(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute spike profit analysis."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    threshold = params.get("threshold_aud_mwh", 300.0)
    year = _safe_year(year)
    table_name = f"trading_price_{year}"

    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "spike_count": 0, "note": f"价格表 trading_price_{year} 尚未同步"}

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
            f"WHERE region_id = ? AND rrp_aud_mwh > ? ORDER BY rrp_aud_mwh DESC",
            (region, threshold),
        )
        rows = cursor.fetchall()

    spike_count = len(rows)
    total_potential = sum(float(r[1]) for r in rows) if rows else 0.0
    return {
        "region": region,
        "year": year,
        "threshold_aud_mwh": threshold,
        "spike_count": spike_count,
        "total_price_above_threshold": round(total_potential, 2),
        "top_5_spikes": [
            {"settlement_date": r[0], "price": round(float(r[1]), 2)} for r in rows[:5]
        ],
    }


def _exec_peak_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute peak/valley spread analysis."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    window_hours = params.get("window_hours", 4)
    year = _safe_year(year)
    table_name = f"trading_price_{year}"

    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "windows": [], "summary": {}, "note": f"价格表 trading_price_{year} 尚未同步"}

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
            f"WHERE region_id = ? ORDER BY settlement_date ASC",
            (region,),
        )
        rows = cursor.fetchall()

    if not rows:
        return {"region": region, "year": year, "windows": [], "summary": {}}

    prices = [float(r[1] or 0.0) for r in rows]
    # Simple spread calculation: top N% avg vs bottom N% avg
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    window_pct = min(window_hours * 2, n // 4)  # approximate window size
    if window_pct < 1:
        window_pct = 1
    charge_avg = sum(sorted_prices[:window_pct]) / window_pct
    discharge_avg = sum(sorted_prices[-window_pct:]) / window_pct
    gross_spread = discharge_avg - charge_avg

    return {
        "region": region,
        "year": year,
        "window_hours": window_hours,
        "summary": {
            "charge_avg_price": round(charge_avg, 2),
            "discharge_avg_price": round(discharge_avg, 2),
            "gross_spread": round(gross_spread, 2),
            "total_intervals": n,
        },
    }


def _exec_fcas_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute FCAS opportunity analysis (NEM) or ESS analysis (WEM)."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    capacity_mw = params.get("capacity_mw", 100.0)

    # WEM uses ESS (Essential System Services) instead of NEM FCAS
    if region == "WEM" or ctx.market.value == "WEM":
        return _exec_wem_ess_analysis(db, region, capacity_mw)

    year = _safe_year(year)
    table_name = f"trading_price_{year}"

    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "has_fcas_data": False, "summary": {},
                "note": f"价格表 trading_price_{year} 尚未同步"}

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT settlement_date, region_id, rrp_aud_mwh, "
            f"raise1sec_rrp, raise6sec_rrp, raise60sec_rrp, raise5min_rrp, raisereg_rrp, "
            f"lower1sec_rrp, lower6sec_rrp, lower60sec_rrp, lower5min_rrp, lowerreg_rrp "
            f"FROM {table_name} WHERE region_id = ? ORDER BY settlement_date ASC",
            (region,),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if not rows:
        return {"region": region, "year": year, "has_fcas_data": False, "summary": {}}

    from fcas_opportunity import summarize_nem_fcas_opportunity
    result = summarize_nem_fcas_opportunity(rows, capacity_mw=capacity_mw, duration_hours=2.0)
    payload = {"region": region, "year": year, "has_fcas_data": True, **result}
    chart = _chart_fcas_services(rows)
    if chart:
        payload["chart"] = chart
    return payload


def _exec_wem_ess_analysis(db, region: str, capacity_mw: float) -> Dict[str, Any]:
    """WEM Essential System Services analysis (frequency control equivalent)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # Check if WEM ESS price data exists
        cursor.execute("SELECT COUNT(*) FROM wem_ess_market_price")
        count = cursor.fetchone()[0]

    if count == 0:
        return {
            "region": region,
            "market": "WEM",
            "has_fcas_data": False,
            "service_type": "ESS (Essential System Services)",
            "summary": {
                "note": "WEM ESS 价格数据尚未导入，无法量化辅助服务收入",
                "total_net_incremental_revenue_k": 0.0,
                "viable_service_count": 0,
            },
        }

    # Calculate ESS service revenues similar to fcas_opportunity logic
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dispatch_interval, energy_price,
                   regulation_raise_price, regulation_lower_price,
                   contingency_raise_price, contingency_lower_price,
                   rocof_price
            FROM wem_ess_market_price 
            ORDER BY dispatch_interval DESC 
            LIMIT 1000  -- Use 1000 intervals for revenue estimation
        """)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if not rows:
        return {
            "region": region,
            "market": "WEM",
            "has_fcas_data": True,
            "service_type": "ESS (Essential System Services)",
            "data_points": 0,
            "summary": {"total_net_incremental_revenue_k": 0.0, "viable_service_count": 0},
            "raw_sample": [],
        }

    from statistics import median
    energy_prices = [float(row.get('energy_price') or 0.0) for row in rows]
    median_energy_price = median(energy_prices) if energy_prices else 0.0
    
    # Calculate interval durations from timestamps
    from datetime import datetime
    def parse_ts(ts):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except:
            return None
    
    timestamps = [parse_ts(str(row.get('dispatch_interval', ''))) for row in rows]
    intervals = []
    valid_ts = [t for t in timestamps if t is not None]
    for i in range(len(valid_ts) - 1):
        delta_hrs = (valid_ts[i+1] - valid_ts[i]).total_seconds() / 3600.0
        intervals.append(delta_hrs if delta_hrs > 0 else 0.5)  # Default 30min
    intervals.append(0.5)  # Last interval default
    
    # ESS services mapping
    ess_services = [
        ('regulation_raise_price', 'Regulation Raise'),
        ('regulation_lower_price', 'Regulation Lower'),
        ('contingency_raise_price', 'Contingency Raise'),
        ('contingency_lower_price', 'Contingency Lower'),
        ('rocof_price', 'RoCoF'),
    ]
    
    total_gross_revenue = 0.0
    total_net_revenue = 0.0
    viable_services = []
    service_breakdown = []
    
    for price_col, service_name in ess_services:
        prices = [float(row.get(price_col) or 0.0) for row in rows]
        positive_prices = [(p, h) for p, h in zip(prices, intervals) if p > 0]
        
        if not positive_prices:
            continue
            
        avg_price = sum(p for p, _ in positive_prices) / len(positive_prices)
        total_duration = sum(h for _, h in positive_prices)
        
        # Gross revenue = avg_price * capacity_mw * total_duration
        gross_revenue = avg_price * capacity_mw * total_duration
        total_gross_revenue += gross_revenue
        
        # Opportunity cost：粗略估计——用该服务有价区间的能量价与全窗口中位价的
        # 偏离度 × 20% 保守因子，近似预留容量损失的套利价值
        pos_energy_prices = [
            float(row.get('energy_price') or 0.0)
            for row, p in zip(rows, prices)
            if p > 0
        ]
        avg_energy = median(pos_energy_prices) if pos_energy_prices else 0.0
        opportunity_price = max(abs(median_energy_price - avg_energy), 0.0) * 0.2  # Conservative 20% factor
        opportunity_cost = opportunity_price * capacity_mw * total_duration
        net_revenue = gross_revenue - opportunity_cost
        total_net_revenue += net_revenue
        
        viable_services.append(service_name)
        service_breakdown.append({
            "service": service_name,
            "average_price_aud_mwh": round(avg_price, 2),
            "positive_intervals": len(positive_prices),
            "gross_revenue_aud": round(gross_revenue, 2),
            "net_revenue_aud": round(net_revenue, 2),
        })
    
    return {
        "region": region,
        "market": "WEM",
        "has_fcas_data": True,
        "service_type": "ESS (Essential System Services)",
        "data_points": len(rows),
        "median_energy_price_aud_mwh": round(median_energy_price, 2),
        "summary": {
            "note": f"{len(viable_services)} active services analyzed over {len(rows)} intervals",
            "total_gross_revenue_aud": round(total_gross_revenue, 2),
            "total_net_incremental_revenue_aud": round(total_net_revenue, 2),
            "viable_service_count": len(viable_services),
            "services_analyzed": viable_services,
        },
        "service_breakdown": service_breakdown[:5],  # Top 5 services
        "raw_sample": rows[:5],
    }


def _exec_saturation_check(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute BESS saturation check."""
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    capacity_path = data_dir / "capacity_data.json"

    region = params.get("region", ctx.effective_region)
    if not capacity_path.exists():
        return {"region": region, "available": False, "message": "Capacity data not found"}

    with open(capacity_path, "r", encoding="utf-8") as f:
        capacity_data = json.load(f)

    # Extract region-specific saturation info
    region_data = capacity_data.get(region, capacity_data.get("all", {}))
    return {"region": region, "available": True, "capacity_data": region_data}


def _exec_cannibalization_forecast(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute BESS cannibalization forecast."""
    from engines.cannibalization_engine import CannibalizationEngine
    from models.capacity_models import CapacityDataLoader

    region = params.get("region", ctx.effective_region)
    years = params.get("years", 10)

    capacity_loader = CapacityDataLoader()
    engine = CannibalizationEngine(capacity_loader)
    result = engine.simulate(
        region=region,
        projection_years=min(years, 5),
    )
    if hasattr(result, "model_dump"):
        return {"region": region, **result.model_dump()}
    return {"region": region, **result} if isinstance(result, dict) else {"region": region, "result": str(result)}


def _exec_fcas_collapse_forecast(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute FCAS collapse forecast."""
    from engines.fcas_collapse_engine import FcasCollapseEngine
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    engine = FcasCollapseEngine(db)
    result = engine.forecast(region=region)
    if hasattr(result, "model_dump"):
        return {"region": region, **result.model_dump()}
    return {"region": region, **result} if isinstance(result, dict) else {"region": region, "result": str(result)}


def _exec_regional_timing_score(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute regional timing scorer."""
    from engines.regional_timing_engine import RegionalTimingEngine
    from models.capacity_models import CapacityDataLoader
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    capacity_loader = CapacityDataLoader()
    engine = RegionalTimingEngine(db, capacity_loader)
    target_year = params.get("year", ctx.effective_year)
    result = engine.score_regions(target_year=target_year)
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    elif isinstance(result, dict):
        data = result
    else:
        data = {"result": str(result)}
    # Filter to requested region if specified
    if region and "rankings" in data:
        region_scores = [r for r in data["rankings"] if r.get("region") == region]
        if region_scores:
            data["rankings"] = region_scores
    return {"region": region, **data}


def _exec_merchant_risk(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute merchant risk Monte Carlo simulation."""
    from engines.merchant_risk_engine import MerchantRiskEngine
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)
    n_simulations = params.get("n_simulations", 500)

    engine = MerchantRiskEngine(db)
    result = engine.simulate(
        region=region,
        power_mw=power_mw,
        duration_hours=duration_hours,
        n_simulations=n_simulations,
    )
    # Convert Pydantic model to dict if needed
    if hasattr(result, "model_dump"):
        return result.model_dump()
    elif hasattr(result, "dict"):
        return result.dict()
    return {"region": region, "result": str(result)}


def _exec_forward_spread(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute forward price spread projection."""
    from engines.forward_price_engine import ForwardPriceEngine
    from models.financial_params import BatterySpecs
    from models.forward_price_models import ScenarioType

    region = params.get("region", ctx.effective_region)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)

    engine = ForwardPriceEngine()
    battery = BatterySpecs(power_mw=power_mw, duration_hours=duration_hours)
    result = engine.generate_20year_projection(
        region=region,
        scenario=ScenarioType.CENTRAL,
        battery=battery,
    )
    if hasattr(result, "model_dump"):
        return result.model_dump()
    elif isinstance(result, dict):
        return result
    return {"region": region, "result": str(result)}


# 联合优化回测区间数上限（OOM 修复，2026-08-09）。PuLP 逐区间构建 MILP
# 变量/约束，全量 8760 步在生产导致 CBC 求解器撑爆容器 cgroup 内存
# （dmesg："cbc invoked oom-killer"，backend worker 被杀 → 前端 network error）。
# 等间距降采样到 ≤2160 区间：价格覆盖范围不变、仅时间分辨率下降，
# 内存与建模耗时随区间数线性下降。可通过 params_override 的
# max_intervals 字段按需覆盖（影响结果代表性，谨慎）。
_COPT_MAX_INTERVALS = 2160


def _downsample_backtest_rows(rows: List[Dict[str, Any]], max_intervals: int):
    """等间距降采样，返回 (采样后行, stride)；stride=1 表示未降采样。"""
    if max_intervals <= 0 or len(rows) <= max_intervals:
        return rows, 1
    stride = math.ceil(len(rows) / max_intervals)
    return rows[::stride], stride


def _exec_co_optimized_backtest(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute co-optimized energy + FCAS backtest."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)

    # Use the co-optimization engine
    from engines.co_optimization_engine import CoOptimizationEngine, CoOptConfig
    from models.financial_params import BatterySpecs

    battery = BatterySpecs(power_mw=power_mw, duration_hours=duration_hours)
    config = CoOptConfig(
        fcas_services=["raisereg", "lowerreg", "raise5min", "lower5min"],
        time_limit_seconds=30,
    )

    # Fetch price data for backtest
    year = _safe_year(year)
    table_name = f"trading_price_{year}"
    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "note": f"价格表 trading_price_{year} 尚未同步"}
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT settlement_date, rrp_aud_mwh, "
            f"raisereg_rrp, lowerreg_rrp, raise5min_rrp, lower5min_rrp "
            f"FROM {table_name} WHERE region_id = ? ORDER BY settlement_date ASC LIMIT 8760",
            (region,),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if not rows:
        return {"region": region, "year": year, "status": "no_data"}

    # OOM 防护：降采样控制求解器内存占用（见 _COPT_MAX_INTERVALS 注释）
    max_intervals = int(params.get("max_intervals") or _COPT_MAX_INTERVALS)
    rows, stride = _downsample_backtest_rows(rows, max_intervals)
    interval_hours = (5.0 / 60.0) * stride

    engine = CoOptimizationEngine(battery, config)

    # Transform row data to engine expected format
    energy_prices = [
        {
            "timestamp": r.get("settlement_date", ""),
            "price": float(r.get("rrp_aud_mwh") or 0.0),
            "interval_hours": interval_hours,
        }
        for r in rows
    ]
    fcas_prices = {}
    for svc in config.fcas_services:
        col = f"{svc}_rrp"
        fcas_prices[svc] = [float(r.get(col) or 0.0) for r in rows]

    result = engine.optimize(energy_prices=energy_prices, fcas_prices=fcas_prices)
    if hasattr(result, "__dict__"):
        payload = {k: v for k, v in vars(result).items() if not k.startswith("_")}
    else:
        payload = {"region": region, "year": year, "result": str(result)}
    if stride > 1:
        # 透明性：报告中注明降采样，避免误读为全分辨率回测
        payload["note"] = (
            f"为控制求解器内存占用已降采样至 {len(rows)} 个区间"
            f"（stride={stride}，价格覆盖范围不变，时间分辨率下降）"
        )
    chart = _chart_coopt_monthly(payload)
    if chart:
        payload["chart"] = chart
    return payload


def _exec_investment_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute investment NPV/IRR analysis - **now calls main financial_model pipeline**."""
    from models.financial_params import (
        InvestmentParams, BatterySpecs, FinancialAssumptions,
        ScenarioConfig
    )
    from engines.financial_model import FinancialModel

    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)
    capex_per_kwh = params.get("capex_per_kwh", 350.0)
    discount_rate = params.get("discount_rate", 0.08)

    # Build BatterySpecs from params
    battery = BatterySpecs(
        power_mw=power_mw,
        duration_hours=duration_hours,
        round_trip_efficiency=0.87,  # Default RTE
        calendar_degradation_rate=0.02,  # 2%/yr
        base_cycle_degradation_rate=0.00003,
    )

    # Build FinancialAssumptions
    financial = FinancialAssumptions(
        capex_per_kwh=capex_per_kwh,
        discount_rate=discount_rate,
        fixed_om_per_mw_year=15000,  # $15k/MW/yr default
    )

    # Build InvestmentParams
    params_invest = InvestmentParams(
        region=region,
        battery=battery,
        financial=financial,
        dispatch_mode="hindsight_optimized",  # Use backtest baseline
        revenue_baseline_mode="co_optimized",
    )

    # 收入底座：用目标年真实价格估算套利/FCAS 基线（非占位拍脑袋），
    # 财务计算（退化/增强/NPV/IRR/回收期）则全部交给主管线 FinancialModel。
    from deps import get_db

    db = get_db()
    safe_yr = _safe_year(year)
    table_name = f"trading_price_{safe_yr}"
    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "note": f"价格表 trading_price_{safe_yr} 尚未同步"}
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT rrp_aud_mwh FROM {table_name} "
            f"WHERE region_id = ? ORDER BY settlement_date ASC",
            (region,),
        )
        prices = [float(r[0] or 0.0) for r in cursor.fetchall()]

    if not prices:
        return {"region": region, "year": year, "status": "no_data"}

    # 日内窗口价差估算（与主管线 peak-analysis 同思路的简化版）
    sorted_p = sorted(prices)
    n = len(sorted_p)
    intervals_per_day = 48 if region == "WEM" else 288
    window_per_day = max(1, int(duration_hours * (intervals_per_day / 24)))
    window = max(1, min(window_per_day * 365, n // 4))
    spread = sum(sorted_p[-window:]) / window - sum(sorted_p[:window]) / window

    annual_cycles = 350.0
    rte = 0.87
    baseline_arbitrage = spread * power_mw * duration_hours * annual_cycles * rte

    # FCAS 基线：用目标年真实 reg FCAS 均价估算（WEM 无此列时为 0）
    # Phase 2（2026-08-12）：显式下调 FCAS 默认权重——调研事实：NEM BESS
    # 收入中 FCAS 占比已降至约 3%（同比 -43%），不再隐含全额计入。
    # 压缩因子从假设登记库读取（fallback 0.3），变更历史见 data/assumptions_registry.json
    from services.assumptions_registry import get_assumption_value

    FCAS_COMPRESSION_FACTOR = float(
        get_assumption_value("fcas_compression_factor", default=0.3)
    )
    baseline_fcas = 0.0
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT AVG(raisereg_rrp), AVG(lowerreg_rrp) FROM {table_name} "
                f"WHERE region_id = ? AND raisereg_rrp IS NOT NULL AND raisereg_rrp > 0",
                (region,),
            )
            fcas_row = cursor.fetchone()
            if fcas_row and fcas_row[0]:
                avg_fcas_price = (float(fcas_row[0] or 0) + float(fcas_row[1] or 0)) / 2
                baseline_fcas = (
                    avg_fcas_price * (power_mw * 0.3) * (6 * 365) * 0.5
                ) * FCAS_COMPRESSION_FACTOR
    except Exception:
        pass

    annual_cycles_history = [annual_cycles] * 20
    dod_severity_history = [1.0] * 20

    scenario = ScenarioConfig(
        name="base",
        capex_multiplier=1.0,
        arbitrage_multiplier=1.0,
        fcas_multiplier=1.0,
    )

    try:
        result = FinancialModel.run_scenario(
            params_invest, scenario, baseline_arbitrage, baseline_fcas,
            annual_cycles_history, dod_severity_history,
        )

        # Phase 3（2026-08-12）：CIS floor 价值流（include_cis=true 时生效）
        # floor 高于 merchant 基线时把套利桶抬升至 floor 重算，产出前后 NPV 对照
        cis_block: Dict[str, Any] = {"included": False}
        if bool(params.get("include_cis", False)) and region != "WEM":
            try:
                from services.contract_revenue import get_cis_floor_params

                cis = get_cis_floor_params(region)
                if cis.get("available"):
                    floor_revenue = float(cis["floor_aud_per_mw_year"]) * power_mw
                    total_baseline = baseline_arbitrage + baseline_fcas
                    if floor_revenue > total_baseline:
                        lifted_arbitrage = baseline_arbitrage + (floor_revenue - total_baseline)
                        result_cis = FinancialModel.run_scenario(
                            params_invest, scenario, lifted_arbitrage, baseline_fcas,
                            annual_cycles_history, dod_severity_history,
                        )
                        cis_block = {
                            "included": True,
                            "binding": True,
                            "npv_before_cis_aud": round(result.metrics.npv, 0),
                            "npv_with_cis_floor_aud": round(result_cis.metrics.npv, 0),
                            "floor_aud_per_mw_year": cis["floor_aud_per_mw_year"],
                            "term_years": cis.get("term_years"),
                            "uplift_aud_yr": round(floor_revenue - total_baseline, 0),
                            "caveat": cis.get("caveat"),
                        }
                    else:
                        cis_block = {
                            "included": True,
                            "binding": False,
                            "note": "merchant 基线已高于 CIS floor，floor 不构成抬升",
                            "floor_aud_per_mw_year": cis["floor_aud_per_mw_year"],
                            "caveat": cis.get("caveat"),
                        }
                else:
                    cis_block = {"included": False, "note": "CIS 配置不可用"}
            except Exception as cis_exc:  # noqa: BLE001 — best-effort 降级
                cis_block = {"included": False, "note": f"CIS 计算失败: {cis_exc}"}

        # P1: use tool_contracts constants for drift-prone output keys so the
        # producer and consumers (synthesizer) share a single source of truth.
        from agent.tool_contracts import (
            INVEST_IRR_KEY,
            INVEST_NPV_KEY,
            INVEST_PAYBACK_KEY,
            INVEST_RESULTS_KEY,
            INVEST_ROI_KEY,
        )

        return {
            "region": region,
            "year": year,
            "params": {
                "power_mw": power_mw,
                "duration_hours": duration_hours,
                "capex_per_kwh": capex_per_kwh,
                "discount_rate": discount_rate,
            },
            INVEST_RESULTS_KEY: {
                "total_capex_aud": round(result.metrics.total_capex, 0),
                INVEST_NPV_KEY: round(result.metrics.npv, 0),
                INVEST_IRR_KEY: round(float(result.metrics.irr) * 100, 2) if result.metrics.irr else None,
                INVEST_ROI_KEY: round(result.metrics.roi_pct, 2),
                INVEST_PAYBACK_KEY: round(result.metrics.payback_years, 1) if result.metrics.payback_years else None,
                "baseline_arbitrage_aud_yr": round(baseline_arbitrage, 0),
                "baseline_fcas_aud_yr": round(baseline_fcas, 0),
                "fcas_compression_factor": FCAS_COMPRESSION_FACTOR,
                "avg_spread_aud_mwh": round(spread, 2),
                "model_type": "financial_model_pipeline",
                "note": (
                    "财务计算由主管线 FinancialModel.run_scenario 完成（含退化/增强/费用）；"
                    "收入底座为目标年真实价格的简化窗口估算，非完整回测，方向参考级；"
                    "FCAS 基线已按压缩因子 0.3 显式下调（FCAS 占 BESS 收入约 3%，持续压缩）"
                ),
            },
            "cis_floor": cis_block,
        }

    except Exception as e:
        logger.error(f"FinancialModel.run_scenario failed: {e}")
        # Fallback to placeholder calculation if pipeline fails
        capacity_mwh = power_mw * duration_hours
        total_capex = capacity_mwh * 1000 * capex_per_kwh
        return {
            "region": region,
            "year": year,
            "status": "fallback",
            "error": str(e),
            "results": {
                "total_capex_aud": round(total_capex, 0),
                "note": "Pipeline failed, using fallback placeholders",
            },
        }


def _exec_compare_regions(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """U6: Compare investment metrics across multiple regions."""
    regions = params.get("regions", ["SA1", "QLD1", "NSW1"])
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)

    results = []
    for region in regions:
        region_params = {
            "region": region,
            "power_mw": power_mw,
            "duration_hours": duration_hours,
        }
        try:
            result = _exec_investment_analysis(region_params, ctx)
            results.append(result)
        except Exception as e:
            results.append({"region": region, "status": "error", "error": str(e)})

    # Rank by NPV
    from agent.tool_contracts import INVEST_NPV_KEY, INVEST_RESULTS_KEY
    ranked = sorted(
        [r for r in results if r.get(INVEST_RESULTS_KEY, {}).get(INVEST_NPV_KEY) is not None],
        key=lambda r: r[INVEST_RESULTS_KEY][INVEST_NPV_KEY],
        reverse=True,
    )

    return {
        "comparison": ranked,
        "best_region": ranked[0]["region"] if ranked else None,
        "regions_analyzed": len(regions),
        "params": {"power_mw": power_mw, "duration_hours": duration_hours},
    }


def _exec_multi_market_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Run investment analysis across NEM + WEM and compare."""
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)
    year = params.get("year", ctx.effective_year)

    # Analyze NEM regions + WEM
    from agent.tool_contracts import INVEST_IRR_KEY, INVEST_NPV_KEY, INVEST_RESULTS_KEY
    all_regions = ["NSW1", "QLD1", "SA1", "VIC1", "WEM"]
    results = []
    for region in all_regions:
        region_params = {
            "region": region,
            "year": year,
            "power_mw": power_mw,
            "duration_hours": duration_hours,
        }
        try:
            result = _exec_investment_analysis(region_params, ctx)
            if result.get(INVEST_RESULTS_KEY):
                results.append(result)
            else:
                results.append({"region": region, "status": result.get("status", "no_data")})
        except Exception as e:
            results.append({"region": region, "status": "error", "error": str(e)})

    # Separate NEM and WEM
    nem_results = [r for r in results if r.get("region") != "WEM" and r.get(INVEST_RESULTS_KEY)]
    wem_result = next((r for r in results if r.get("region") == "WEM" and r.get(INVEST_RESULTS_KEY)), None)

    # Best NEM region
    best_nem = max(nem_results, key=lambda r: r[INVEST_RESULTS_KEY][INVEST_NPV_KEY]) if nem_results else None

    comparison = {
        "markets_analyzed": ["NEM", "WEM"],
        "year": year,
        "params": {"power_mw": power_mw, "duration_hours": duration_hours},
        "nem_best": {
            "region": best_nem["region"],
            **best_nem[INVEST_RESULTS_KEY],
        } if best_nem else None,
        "wem": wem_result.get(INVEST_RESULTS_KEY) if wem_result else {"status": "no_data"},
        "all_regions": [
            {"region": r.get("region"), "npv": r.get(INVEST_RESULTS_KEY, {}).get(INVEST_NPV_KEY), "irr": r.get(INVEST_RESULTS_KEY, {}).get(INVEST_IRR_KEY)}
            for r in results
        ],
        "recommendation": "",
    }

    # Generate recommendation
    if best_nem and wem_result and wem_result.get(INVEST_RESULTS_KEY):
        nem_npv = best_nem[INVEST_RESULTS_KEY][INVEST_NPV_KEY]
        wem_npv = wem_result[INVEST_RESULTS_KEY][INVEST_NPV_KEY]
        if nem_npv > wem_npv:
            comparison["recommendation"] = f"NEM {best_nem['region']} NPV ({nem_npv:,.0f}) 优于 WEM ({wem_npv:,.0f})"
        else:
            comparison["recommendation"] = f"WEM NPV ({wem_npv:,.0f}) 优于 NEM 最优区域 {best_nem['region']} ({nem_npv:,.0f})"

    return comparison


# =============================================================================
# Phase 1: Data Query / Timeseries / Export
# =============================================================================

# SQL keywords that are NEVER allowed in user-generated queries
_SQL_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|EXECUTE|INTO|SET|LOAD|CALL)\b",
    re.IGNORECASE,
)


def _exec_data_query(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute a safe read-only SQL query generated by the LLM."""
    import re as _re
    from deps import get_db

    sql = params.get("sql", "").strip()
    if not sql:
        return {"status": "error", "error": "未提供 SQL 查询"}

    # Safety: only SELECT allowed
    if not sql.upper().startswith("SELECT"):
        return {"status": "error", "error": "只允许 SELECT 查询"}
    if _SQL_FORBIDDEN.search(sql):
        return {"status": "error", "error": "SQL 包含禁止关键词（INSERT/UPDATE/DELETE/DROP/SET/INTO等）"}
    # Block multi-statement injection
    if ";" in sql.rstrip(";").rstrip():
        return {"status": "error", "error": "不允许多条 SQL 语句（禁止分号）"}

    # Force LIMIT if not present
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 500"
    else:
        # Cap existing LIMIT at 500
        limit_match = _re.search(r"LIMIT\s+(\d+)", sql, _re.IGNORECASE)
        if limit_match and int(limit_match.group(1)) > 500:
            sql = _re.sub(r"LIMIT\s+\d+", "LIMIT 500", sql, flags=_re.IGNORECASE)

    db = get_db()
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            # Convert to list of dicts (cap at 500 rows)
            data = [dict(zip(columns, row)) for row in rows[:500]]
            return {
                "status": "success",
                "sql": sql,
                "columns": columns,
                "row_count": len(data),
                "data": data,
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "sql": sql}


def _exec_timeseries_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Time series analysis: duration curve, hourly profile, monthly aggregation."""
    from deps import get_db
    from statistics import mean, stdev

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    analysis_type = params.get("analysis_type", "duration_curve")  # duration_curve | hourly_profile | monthly_avg
    metric = params.get("metric", "rrp_aud_mwh")

    year = _safe_year(year)
    table_name = f"trading_price_{year}"

    if not _price_table_exists(db, table_name):
        return {"status": "no_data", "region": region, "year": year,
                "note": f"价格表 trading_price_{year} 尚未同步"}

    # Whitelist metric columns
    allowed_metrics = {
        "rrp_aud_mwh", "raisereg_rrp", "lowerreg_rrp",
        "raise5min_rrp", "lower5min_rrp",
    }
    if metric not in allowed_metrics:
        metric = "rrp_aud_mwh"

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT settlement_date, {metric} FROM {table_name} "
                f"WHERE region_id = ? ORDER BY settlement_date ASC",
                (region,),
            )
            rows = cursor.fetchall()
    except Exception as e:
        return {"status": "error", "error": str(e)}

    if not rows:
        return {"status": "no_data", "region": region, "year": year}

    values = [float(r[1] or 0.0) for r in rows]
    dates = [str(r[0]) for r in rows]
    n = len(values)

    # Basic statistics
    stats = {
        "count": n,
        "mean": round(mean(values), 2),
        "std": round(stdev(values), 2) if n > 1 else 0,
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "p10": round(sorted(values)[n // 10], 2),
        "p25": round(sorted(values)[n // 4], 2),
        "p50": round(sorted(values)[n // 2], 2),
        "p75": round(sorted(values)[3 * n // 4], 2),
        "p90": round(sorted(values)[9 * n // 10], 2),
    }

    result = {
        "region": region,
        "year": year,
        "metric": metric,
        "analysis_type": analysis_type,
        "stats": stats,
    }

    if analysis_type == "duration_curve":
        # Sorted descending (price duration curve)
        sorted_desc = sorted(values, reverse=True)
        # Sample to max 200 points for frontend rendering
        step = max(1, n // 200)
        result["duration_curve"] = [
            {"rank": i, "value": round(sorted_desc[i], 2)}
            for i in range(0, n, step)
        ]

    elif analysis_type == "hourly_profile":
        # Average by hour of day
        from collections import defaultdict
        hourly = defaultdict(list)
        for d, v in zip(dates, values):
            try:
                hour = int(d[11:13]) if len(d) > 13 else int(d.split(" ")[1].split(":")[0])
                hourly[hour].append(v)
            except (IndexError, ValueError):
                pass
        result["hourly_profile"] = [
            {"hour": h, "avg": round(mean(vals), 2), "count": len(vals)}
            for h, vals in sorted(hourly.items())
        ]

    elif analysis_type == "monthly_avg":
        from collections import defaultdict
        monthly = defaultdict(list)
        for d, v in zip(dates, values):
            try:
                month = int(d[5:7])
                monthly[month].append(v)
            except (IndexError, ValueError):
                pass
        result["monthly_avg"] = [
            {"month": m, "avg": round(mean(vals), 2), "count": len(vals)}
            for m, vals in sorted(monthly.items())
        ]

    return result


def _exec_export_data(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Export query results as CSV/JSON download."""
    import csv
    import io
    import tempfile
    from pathlib import Path

    sql = params.get("sql", "")
    fmt = params.get("format", "csv")  # csv | json

    # First execute the query
    query_result = _exec_data_query({"sql": sql}, ctx)
    if query_result.get("status") != "success":
        return query_result

    data = query_result.get("data", [])
    columns = query_result.get("columns", [])

    if not data:
        return {"status": "error", "error": "查询结果为空，无法导出"}

    # Generate file
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    import uuid
    file_id = str(uuid.uuid4())[:8]

    if fmt == "json":
        import json as _json
        filename = f"export_{file_id}.json"
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, default=str, indent=2)
    else:
        filename = f"export_{file_id}.csv"
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in data:
                writer.writerow({k: str(v) if v is not None else "" for k, v in row.items()})

    return {
        "status": "success",
        "format": fmt,
        "filename": filename,
        "row_count": len(data),
        "download_path": f"/api/v1/agent/download/{filename}",
        "preview": data[:5],
    }


def _exec_read_artifact(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Read a persisted tool-result artifact (B1: 可恢复压缩的读取端).

    只允许读 output/ 目录下的 artifact_* 文件（路径穿越防护与
    download 路由一致）；超大文件截断返回前 20k 字符。
    """
    import json as _json
    from pathlib import Path

    filename = (params.get("filename") or "").strip()
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return {"status": "error", "error": "非法的 artifact 文件名"}
    if not filename.startswith("artifact_") or not filename.endswith(".json"):
        return {"status": "error", "error": "只允许读取 artifact_*.json 文件"}

    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    filepath = (output_dir / filename).resolve()
    if not str(filepath).startswith(str(output_dir.resolve())):
        return {"status": "error", "error": "非法的 artifact 路径"}
    if not filepath.exists():
        return {"status": "error", "error": f"artifact 不存在: {filename}"}

    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "error": f"读取失败: {exc}"}

    if len(text) > 20000:
        return {
            "status": "success",
            "truncated": True,
            "total_chars": len(text),
            "note": "文件过大，返回前 20000 字符；如需其他部分请说明",
            "data_preview": text[:20000],
        }
    try:
        return {"status": "success", "truncated": False, "data": _json.loads(text)}
    except _json.JSONDecodeError:
        return {"status": "success", "truncated": False, "raw": text}


def _exec_risk_stratification(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute revenue risk stratification."""
    from engines.risk_stratification_engine import RiskStratificationEngine
    from models.financial_params import BatterySpecs
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)
    year = _safe_year(year)
    table_name = f"trading_price_{year}"

    if not _price_table_exists(db, table_name):
        return {"region": region, "year": year, "status": "no_data",
                "note": f"价格表 trading_price_{year} 尚未同步"}

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
            f"WHERE region_id = ? ORDER BY settlement_date ASC",
            (region,),
        )
        rows = [{"price": float(r[1] or 0.0), "interval_hours": 5.0 / 60.0} for r in cursor.fetchall()]

    if not rows:
        return {"region": region, "status": "no_data"}

    battery = BatterySpecs(power_mw=power_mw, duration_hours=duration_hours)
    engine = RiskStratificationEngine()
    result = engine.stratify_historical_revenue(rows, fcas_revenue=0.0, battery=battery)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    elif isinstance(result, dict):
        return result
    return {"region": region, "result": str(result)}


def _exec_grid_forecast(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute grid forecast (24h outlook)."""
    from deps import get_db
    import grid_forecast

    db = get_db()
    region = params.get("region", ctx.effective_region)
    market = params.get("market", ctx.market.value)
    horizon = params.get("horizon", "24h")

    result = grid_forecast.get_grid_forecast_response(
        db, market=market, region=region, horizon=horizon
    )
    return result if isinstance(result, dict) else {"region": region, "result": str(result)}


def _exec_data_quality(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute data quality check."""
    from deps import get_db
    from data_quality import compute_quality_snapshots, summarize_quality_snapshots

    db = get_db()
    snapshots = compute_quality_snapshots(db)
    summary = summarize_quality_snapshots(snapshots)
    return summary


def _exec_cross_validation(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute multi-source cross validation."""
    from datetime import date as _date
    from pathlib import Path
    from engines.cross_validation_service import CrossValidationService
    from models.forward_price_models import EventRegistry

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    evidence_path = data_dir / "financial_evidence.json"
    registry = EventRegistry(events=[], last_updated=_date.today())

    service = CrossValidationService(evidence_path=evidence_path, event_registry=registry)
    category = params.get("category", "revenue_benchmarks")
    region = params.get("region", ctx.effective_region)
    result = service.get_cross_validation_response(category=category, region=region)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    elif isinstance(result, dict):
        return result
    return {"result": str(result)}


def _exec_narrative_attribution(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute narrative causal attribution."""
    from datetime import date as _date
    from engines.narrative_engine import NarrativeEngine
    from models.forward_price_models import EventRegistry

    region = params.get("region", ctx.effective_region)
    module_name = params.get("module_name", "investment_analysis")
    metric_name = params.get("metric_name", "npv")
    metric_value = params.get("metric_value", 0.0)

    registry = EventRegistry(events=[], last_updated=_date.today())
    engine = NarrativeEngine(registry)
    result = engine.generate_module_conclusion(
        module_name=module_name,
        region=region,
        metrics={metric_name: metric_value},
    )
    if hasattr(result, "model_dump"):
        return result.model_dump()
    elif isinstance(result, dict):
        return result
    return {"region": region, "result": str(result)}


# =============================================================================
# Registry Builder
# =============================================================================


def _exec_bess_revenue_benchmark(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute NEM BESS revenue benchmark (rolling monthly index).

    Phase 1（2026-08-12）：对标 Modo 指数的内部 derived 基准，
    复用 benchmark_engine 与 /api/benchmark 同一计算入口。
    """
    from deps import get_db
    from engines.benchmark_engine import (
        NEM_BENCHMARK_REGIONS,
        build_nem_bess_benchmark,
    )

    region = (params.get("region") or ctx.effective_region or "NSW1").upper()
    if region not in NEM_BENCHMARK_REGIONS:
        return {
            "region": region,
            "status": "unsupported_region",
            "note": f"Benchmark 仅覆盖 NEM 大陆区域 {NEM_BENCHMARK_REGIONS}",
        }
    try:
        months = int(params.get("months", 12))
    except (TypeError, ValueError):
        months = 12
    months = max(1, min(months, 24))

    result = build_nem_bess_benchmark(get_db(), region, months)
    summary = result.get("summary", {})
    if summary.get("latest_month"):
        result["headline"] = (
            f"{region} 最近完整月 {summary.get('latest_month')} 基准收益 "
            f"{summary.get('latest_index_k_aud_per_mw_year')} kAUD/MW/年"
            f"（滚动均值 {summary.get('avg_index_k_aud_per_mw_year')}，"
            f"偏离 {summary.get('latest_vs_avg_pct')}%）"
        )
    else:
        result["headline"] = f"{region} 窗口内无结算数据，无法计算基准收益"
    return result


def _exec_grid_knowledge_lookup(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """检索电网规则与制度知识库（规则卡片 + 政策时间线）。

    规则知识库（2026-08-12）：常识/规则类问题从 LLM 裸答升级为
    知识库检索 + 来源引用（source_url / effective_date / confidence）。
    """
    from services.grid_knowledge import get_timeline, search_rules

    query = (params.get("query") or "").strip() or None
    market = params.get("market")
    include_timeline = bool(params.get("timeline", False)) or not query

    result = search_rules(query=query, market=market, limit=5)
    if include_timeline:
        result["timeline"] = get_timeline(10)
    return result


def _exec_market_event_lookup(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """检索市场事件案例库（重大事件因果卡片）。

    事件案例库（2026-08-13）：归因叙事与"历史相似情景"引用从
    即兴描述升级为案例库检索 + 来源引用。
    """
    from services.market_events import search_events

    query = (params.get("query") or "").strip() or None
    return search_events(
        query=query,
        market=params.get("market"),
        category=params.get("category"),
        limit=5,
    )


def _exec_asset_pipeline_lookup(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """检索资产与管线知识库（项目级档案 + 市场级管线锚点）。

    管线知识库（2026-08-13）：饱和/蚕食/崩塌判断的供给端事实基础，
    支持区域汇总与项目级检索；数据陈旧时自动提示季度更新。
    """
    from services.pipeline_knowledge import search_projects, summarize_pipeline

    region = params.get("region")
    mode = params.get("mode", "summary")
    if mode == "projects":
        return search_projects(
            region=region,
            status=params.get("status"),
            name_contains=params.get("name_contains"),
            limit=int(params.get("limit", 20)),
        )
    return summarize_pipeline(region=region)


def build_tool_registry() -> ToolRegistry:
    """Build and populate the complete tool registry."""
    registry = ToolRegistry()

    # --- Stage 1: Market Screening ---
    registry.register(
        ToolDefinition(
            name="market_screening",
            description="Screen all markets (NEM regions + WEM) for BESS investment potential. Returns ranked candidates with spread, volatility, FCAS opportunity, and data quality scores.",
            parameters={
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Analysis year (e.g. 2025)"},
                },
            },
            stage="Stage 1 - Market Screening",
        ),
        _exec_market_screening,
    )

    registry.register(
        ToolDefinition(
            name="price_trend_analysis",
            description="Analyze price trends for a specific region: average, max, min, volatility, negative price ratio.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code (NSW1, QLD1, VIC1, SA1, TAS1, WEM)"},
                    "year": {"type": "integer", "description": "Analysis year"},
                },
                "required": ["region"],
            },
            stage="Stage 1 - Market Screening",
        ),
        _exec_price_trend,
    )

    registry.register(
        ToolDefinition(
            name="regional_ranking",
            description="Rank NEM regions by BESS investment potential based on multi-dimensional scoring.",
            parameters={
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Analysis year"},
                },
            },
            stage="Stage 1 - Market Screening",
        ),
        _exec_regional_ranking,
    )

    registry.register(
        ToolDefinition(
            name="grid_knowledge_lookup",
            description=(
                "Search the curated grid rules & market-design knowledge base (NEM/WEM): "
                "5-minute settlement, IESS registration, price bounds (MPC/CPT), FCAS services, "
                "PFR obligation, WEM RCM/BRCP & ESS services, plus a policy timeline. Returns "
                "rule cards with source_url, effective_date and confidence — cite them when "
                "answering rule/mechanism/concept questions instead of relying on generic knowledge."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword query, e.g. 'FCAS', '价格上限', 'IESS 注册', '容量机制'"},
                    "market": {"type": "string", "description": "Optional market filter (NEM or WEM)"},
                    "timeline": {"type": "boolean", "description": "Include policy timeline (default true when query is empty)"},
                },
            },
            stage="Global - Knowledge",
        ),
        _exec_grid_knowledge_lookup,
    )

    registry.register(
        ToolDefinition(
            name="market_event_lookup",
            description=(
                "Search the curated market event case library (NEM/WEM): SA black system 2016, "
                "Liddell coal retirement, negative price wave 2025Q4-2026, FCAS collapse 2024-2026, "
                "BESS revenue record lows 2026. Returns causal case cards (event -> price/FCAS/BESS "
                "impact -> lessons) with source_url — cite them when explaining market moves or "
                "reasoning about similar historical scenarios."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword query, e.g. '大停电', '负价', 'FCAS 崩塌', '收益新低', '煤电退役'"},
                    "market": {"type": "string", "description": "Optional market filter (NEM or WEM)"},
                    "category": {"type": "string", "description": "Optional category filter (black_system, coal_retirement, negative_price_wave, fcas_collapse, revenue_compression)"},
                },
            },
            stage="Global - Knowledge",
        ),
        _exec_market_event_lookup,
    )

    # --- Stage 2: Revenue Deep Dive ---
    registry.register(
        ToolDefinition(
            name="bess_revenue_benchmark",
            description=(
                "NEM BESS revenue benchmark: rolling monthly index in kAUD/MW/year for a "
                "reference 100MW/200MWh battery (RTE 0.85). Derived ideal-discharge caliber — "
                "FCAS/capacity not included, not directly comparable to third-party indices "
                "(e.g. Modo). Use to anchor market-entry and revenue expectations."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "NEM mainland region (NSW1, QLD1, SA1, VIC1)"},
                    "months": {"type": "integer", "description": "Rolling window size in months (1-24, default 12)"},
                },
                "required": ["region"],
            },
            stage="Stage 2 - Revenue Deep Dive",
        ),
        _exec_bess_revenue_benchmark,
    )

    registry.register(
        ToolDefinition(
            name="spike_profit_analysis",
            description="Analyze extreme price spike events and potential profit from capturing spikes above a threshold.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Analysis year"},
                    "threshold_aud_mwh": {"type": "number", "description": "Price threshold for spike definition (default 300)"},
                },
                "required": ["region"],
            },
            stage="Stage 2 - Revenue Deep Dive",
        ),
        _exec_spike_profit,
    )

    registry.register(
        ToolDefinition(
            name="peak_analysis",
            description="Analyze charge/discharge price spread (arbitrage window) for a region. Returns gross spread between peak and trough prices.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Analysis year"},
                    "window_hours": {"type": "integer", "description": "Window size in hours (1, 2, 4, 6)"},
                },
                "required": ["region"],
            },
            stage="Stage 2 - Revenue Deep Dive",
        ),
        _exec_peak_analysis,
    )

    registry.register(
        ToolDefinition(
            name="fcas_analysis",
            description="Analyze FCAS (Frequency Control Ancillary Services) revenue opportunity for a region. Returns per-service breakdown and total incremental revenue.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Analysis year"},
                    "capacity_mw": {"type": "number", "description": "BESS capacity in MW (default 100)"},
                },
                "required": ["region"],
            },
            stage="Stage 2 - Revenue Deep Dive",
        ),
        _exec_fcas_analysis,
    )

    # --- Stage 3: Saturation ---
    registry.register(
        ToolDefinition(
            name="saturation_check",
            description="Check BESS capacity saturation level and competition risk for a region.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                },
                "required": ["region"],
            },
            stage="Stage 3 - Saturation & Competition",
        ),
        _exec_saturation_check,
    )

    registry.register(
        ToolDefinition(
            name="asset_pipeline_lookup",
            description=(
                "Look up the BESS asset & pipeline knowledge base: region-level pipeline "
                "summary by status (registered/committed/construction/planning, active supply MW) "
                "plus market-level AEMO pipeline anchors, or project-level search "
                "(name/region/status). Use for saturation, cannibalization and competition "
                "reasoning. Note: project archive is a maintained sample, market totals come "
                "from official anchors — do not mix the two calibers."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "description": "'summary' (default, region aggregation + market anchors) or 'projects' (project-level search)"},
                    "region": {"type": "string", "description": "Optional region filter (NSW1, QLD1, VIC1, SA1, TAS1, WEM)"},
                    "status": {"type": "string", "description": "projects mode only: status filter (registered, committed, construction, planning)"},
                    "name_contains": {"type": "string", "description": "projects mode only: project name substring"},
                    "limit": {"type": "integer", "description": "projects mode only: max results (default 20)"},
                },
            },
            stage="Stage 3 - Saturation & Competition",
        ),
        _exec_asset_pipeline_lookup,
    )

    # --- Stage 4: Investment Outlook ---
    registry.register(
        ToolDefinition(
            name="cannibalization_forecast",
            description="Forecast revenue dilution from BESS capacity growth (cannibalization effect) over N years.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "current_capacity_mw": {"type": "number", "description": "Current installed BESS capacity (MW)"},
                    "growth_rate_pct": {"type": "number", "description": "Annual capacity growth rate (%)"},
                    "years": {"type": "integer", "description": "Projection horizon (years)"},
                },
                "required": ["region"],
            },
            stage="Stage 4 - Investment Outlook",
        ),
        _exec_cannibalization_forecast,
    )

    registry.register(
        ToolDefinition(
            name="fcas_collapse_forecast",
            description="Forecast FCAS price ceiling collapse risk based on supply-demand dynamics.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                },
                "required": ["region"],
            },
            stage="Stage 4 - Investment Outlook",
        ),
        _exec_fcas_collapse_forecast,
    )

    registry.register(
        ToolDefinition(
            name="regional_timing_score",
            description="Score regional investment timing across 4 dimensions: market readiness, policy environment, competition window, infrastructure.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                },
                "required": ["region"],
            },
            stage="Stage 4 - Investment Outlook",
        ),
        _exec_regional_timing_score,
    )

    registry.register(
        ToolDefinition(
            name="merchant_risk_simulate",
            description="Run Monte Carlo simulation to generate revenue probability distribution (P10/P50/P90) and bank financing contract coverage requirements.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "power_mw": {"type": "number", "description": "BESS power (MW)"},
                    "duration_hours": {"type": "number", "description": "BESS duration (hours)"},
                    "n_simulations": {"type": "integer", "description": "Number of Monte Carlo iterations (default 500)"},
                },
                "required": ["region"],
            },
            stage="Stage 4 - Investment Outlook",
        ),
        _exec_merchant_risk,
    )

    registry.register(
        ToolDefinition(
            name="forward_spread_projection",
            description="Project 20-year forward price spread under Central/High/Low scenarios based on supply-demand events (coal retirement, BESS saturation).",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "projection_years": {"type": "integer", "description": "Projection horizon (default 20)"},
                },
                "required": ["region"],
            },
            stage="Stage 4 - Investment Outlook",
        ),
        _exec_forward_spread,
    )

    # --- Stage 5: Co-Optimized Backtest ---
    registry.register(
        ToolDefinition(
            name="co_optimized_backtest",
            description="Run co-optimized energy + FCAS joint dispatch backtest using MILP solver. Returns revenue breakdown between energy arbitrage and FCAS services.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Backtest year"},
                    "power_mw": {"type": "number", "description": "BESS power (MW)"},
                    "duration_hours": {"type": "number", "description": "BESS duration (hours)"},
                },
                "required": ["region"],
            },
            stage="Stage 5 - Co-Optimized Backtest",
        ),
        _exec_co_optimized_backtest,
    )

    # --- Stage 6: Financial Modeling ---
    registry.register(
        ToolDefinition(
            name="investment_analysis",
            description=(
                "Run BESS investment NPV/IRR analysis with given parameters. Returns capex, "
                "annual revenue, NPV, and payback period. FCAS baseline is explicitly "
                "compressed (factor 0.3). Set include_cis=true to add the CIS revenue-floor "
                "value stream and get before/after-floor NPV comparison (NEM only)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Base year for revenue estimation"},
                    "power_mw": {"type": "number", "description": "BESS power (MW)"},
                    "duration_hours": {"type": "number", "description": "BESS duration (hours)"},
                    "capex_per_kwh": {"type": "number", "description": "CAPEX per kWh (AUD)"},
                    "discount_rate": {"type": "number", "description": "Discount rate (e.g. 0.08)"},
                    "include_cis": {"type": "boolean", "description": "Include CIS revenue-floor value stream with before/after NPV comparison (NEM only, default false)"},
                },
                "required": ["region"],
            },
            stage="Stage 6 - Financial Modeling",
        ),
        _exec_investment_analysis,
    )

    registry.register(
        ToolDefinition(
            name="risk_stratification",
            description="Stratify revenue into 3 risk layers (base arbitrage, FCAS, extreme events) with independent discount rates and NPV calculation.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Analysis year"},
                    "power_mw": {"type": "number", "description": "BESS power (MW)"},
                },
                "required": ["region"],
            },
            stage="Stage 6 - Financial Modeling",
        ),
        _exec_risk_stratification,
    )

    registry.register(
        ToolDefinition(
            name="cross_validation",
            description="Cross-validate platform estimates against external sources (coal retirement dates, revenue benchmarks, price forecasts).",
            parameters={
                "type": "object",
                "properties": {},
            },
            stage="Stage 6 - Financial Modeling",
        ),
        _exec_cross_validation,
    )

    registry.register(
        ToolDefinition(
            name="narrative_attribution",
            description="Generate causal attribution narrative explaining why a metric has its current value (coal closures, BESS saturation, network augmentation).",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "module_name": {"type": "string", "description": "Analysis module name"},
                    "metric_name": {"type": "string", "description": "Metric to explain (e.g. npv, spread)"},
                    "metric_value": {"type": "number", "description": "Current metric value"},
                },
                "required": ["region", "metric_name"],
            },
            stage="Stage 6 - Financial Modeling",
        ),
        _exec_narrative_attribution,
    )

    # --- Global Tools ---
    registry.register(
        ToolDefinition(
            name="grid_forecast",
            description="Generate 24h/7d/30d grid forecast based on supply-demand-network-reserve factors. Returns risk signals and opportunity windows.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "market": {"type": "string", "enum": ["NEM", "WEM"], "description": "Market type"},
                    "horizon": {"type": "string", "enum": ["24h", "7d", "30d"], "description": "Forecast horizon"},
                },
                "required": ["region"],
            },
            stage="24h Outlook",
        ),
        _exec_grid_forecast,
    )

    registry.register(
        ToolDefinition(
            name="data_quality_check",
            description="Check data quality across all markets. Returns quality scores, coverage, freshness, and identified issues.",
            parameters={
                "type": "object",
                "properties": {},
            },
            stage="Global",
        ),
        _exec_data_quality,
    )

    # U6: compare_regions — convenience tool for multi-region investment comparison
    registry.register(
        ToolDefinition(
            name="compare_regions",
            description="Compare investment metrics across multiple NEM regions. Runs investment_analysis for each region and returns a ranked comparison table.",
            parameters={
                "type": "object",
                "properties": {
                    "regions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of regions to compare (e.g. ['SA1', 'QLD1', 'NSW1'])",
                    },
                    "power_mw": {"type": "number", "description": "Battery power in MW", "default": 100},
                    "duration_hours": {"type": "number", "description": "Battery duration in hours", "default": 4},
                },
                "required": ["regions"],
            },
            stage="Investment Decision",
        ),
        _exec_compare_regions,
    )

    # Multi-market analysis: NEM + WEM joint comparison
    registry.register(
        ToolDefinition(
            name="multi_market_analysis",
            description="Run investment analysis across ALL markets (NEM 4 regions + WEM) simultaneously and compare NPV/IRR. Returns best NEM region vs WEM side-by-side.",
            parameters={
                "type": "object",
                "properties": {
                    "power_mw": {"type": "number", "description": "Battery power in MW", "default": 100},
                    "duration_hours": {"type": "number", "description": "Battery duration in hours", "default": 4},
                    "year": {"type": "integer", "description": "Analysis year"},
                },
            },
            stage="Investment Decision",
        ),
        _exec_multi_market_analysis,
    )

    # --- Phase 1: Data Query / Timeseries / Export ---
    registry.register(
        ToolDefinition(
            name="data_query",
            description="Execute a safe read-only SQL query against the analysis database. Use this to answer any data question not covered by other tools. Only SELECT allowed, max 500 rows.",
            parameters={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL SELECT query to execute (whitelisted tables only)"},
                },
                "required": ["sql"],
            },
            stage="Data Exploration",
        ),
        _exec_data_query_safe,
    )

    registry.register(
        ToolDefinition(
            name="timeseries_analysis",
            description="Analyze time series data: price duration curve, hourly profile, or monthly averages for a region/year.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Analysis year"},
                    "analysis_type": {"type": "string", "enum": ["duration_curve", "hourly_profile", "monthly_avg"], "description": "Type of analysis"},
                    "metric": {"type": "string", "description": "Column to analyze (default: rrp_aud_mwh)"},
                },
                "required": ["region"],
            },
            stage="Data Exploration",
        ),
        _exec_timeseries_analysis,
    )

    registry.register(
        ToolDefinition(
            name="export_data",
            description="Export SQL query results as CSV or JSON file for download.",
            parameters={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL SELECT query whose results to export"},
                    "format": {"type": "string", "enum": ["csv", "json"], "description": "Export format (default: csv)"},
                },
                "required": ["sql"],
            },
            stage="Data Exploration",
        ),
        _exec_export_data,
    )

    # B1: read_artifact — 配套 artifact 落盘机制的按需读取端
    registry.register(
        ToolDefinition(
            name="read_artifact",
            description="Read the full persisted data of a tool result artifact. Use when a tool_output hint says 完整数据已落盘 and you need fields missing from the summary. Only filenames starting with 'artifact_' are allowed.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Artifact filename from the tool_output hint (artifact_*.json)"},
                },
                "required": ["filename"],
            },
            stage="Data Exploration",
        ),
        _exec_read_artifact,
    )

    # --- Phase 2: Chart / Scenario / Portfolio / Generation ---
    registry.register(
        ToolDefinition(
            name="generate_chart",
            description="Generate a chart (line/bar/scatter/area) from data or SQL query. Returns chart spec for frontend rendering.",
            parameters={
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["line", "bar", "scatter", "area"], "description": "Chart type"},
                    "title": {"type": "string", "description": "Chart title"},
                    "sql": {"type": "string", "description": "SQL query to get chart data (first col=x, second col=y)"},
                    "data": {"type": "array", "items": {"type": "object"}, "description": "Direct data [{x,y}...]"},
                    "x_label": {"type": "string"},
                    "y_label": {"type": "string"},
                },
            },
            stage="Visualization",
        ),
        _exec_generate_chart,
    )

    registry.register(
        ToolDefinition(
            name="scenario_simulation",
            description="Run multi-scenario investment simulation (Bear/Central/Bull) with custom CAPEX, discount rate, and spread assumptions.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "year": {"type": "integer"},
                    "power_mw": {"type": "number"},
                    "duration_hours": {"type": "number"},
                    "scenarios": {"type": "array", "items": {"type": "object"}, "description": "Custom scenarios [{name, capex_per_kwh, discount_rate, spread_factor}]"},
                },
            },
            stage="Investment Decision",
        ),
        _exec_scenario_simulation,
    )

    registry.register(
        ToolDefinition(
            name="portfolio_analysis",
            description="Analyze a multi-project BESS portfolio: total NPV, risk diversification, and optimal allocation.",
            parameters={
                "type": "object",
                "properties": {
                    "projects": {"type": "array", "items": {"type": "object"}, "description": "[{region, power_mw, duration_hours}]"},
                    "year": {"type": "integer"},
                },
            },
            stage="Investment Decision",
        ),
        _exec_portfolio_analysis,
    )

    registry.register(
        ToolDefinition(
            name="generation_analysis",
            description="Analyze generation mix, renewable penetration, and supply adequacy for a region.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "analysis_type": {"type": "string", "enum": ["generation_mix", "renewable_penetration", "supply_adequacy"]},
                },
                "required": ["region"],
            },
            stage="Market Analysis",
        ),
        _exec_generation_analysis,
    )

    # --- Phase 3: Market Pulse / Weather / Report ---
    registry.register(
        ToolDefinition(
            name="market_pulse",
            description="Get current market state snapshot: latest prices (24h), demand, renewable penetration for a region.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "year": {"type": "integer"},
                },
            },
            stage="Real-time",
        ),
        _exec_market_pulse,
    )

    registry.register(
        ToolDefinition(
            name="weather_correlation",
            description="Analyze weather-to-price correlation: temperature extremes, heatwave frequency, and their impact on demand/prices.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                },
            },
            stage="Market Analysis",
        ),
        _exec_weather_correlation,
    )

    registry.register(
        ToolDefinition(
            name="generate_report",
            description="Generate an investment committee memo (Markdown) combining market analysis, financial model, and risk flags.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "year": {"type": "integer"},
                    "power_mw": {"type": "number"},
                    "duration_hours": {"type": "number"},
                    "capex_per_kwh": {"type": "number"},
                    "discount_rate": {"type": "number"},
                },
            },
            stage="Report",
        ),
        _exec_generate_report,
    )

    return registry


# =============================================================================
# Phase 2: Chart / Scenario / Portfolio / Generation
# =============================================================================


def _exec_generate_chart(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Generate chart specification for frontend rendering."""
    chart_type = params.get("chart_type", "line")  # line | bar | scatter | area
    title = params.get("title", "")
    data = params.get("data", [])  # [{x: ..., y: ...}, ...] or [{label: ..., value: ...}, ...]
    x_label = params.get("x_label", "")
    y_label = params.get("y_label", "")

    # If no data provided, try to generate from a SQL query
    if not data and params.get("sql"):
        query_result = _exec_data_query({"sql": params["sql"]}, ctx)
        if query_result.get("status") == "success":
            rows = query_result.get("data", [])
            cols = query_result.get("columns", [])
            if len(cols) >= 2:
                data = [{"x": str(r.get(cols[0], "")), "y": float(r.get(cols[1], 0) or 0)} for r in rows]

    if not data:
        return {"status": "error", "error": "未提供图表数据"}

    return {
        "status": "success",
        "chart": {
            "type": chart_type,
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "data": data[:200],  # Cap data points
        },
    }


def _exec_scenario_simulation(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Run multi-scenario investment simulation with custom assumptions."""
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)

    # Define scenarios
    scenarios = params.get("scenarios", [
        {"name": "悲观 (Bear)", "capex_per_kwh": 500, "discount_rate": 0.10, "spread_factor": 0.8},
        {"name": "中性 (Central)", "capex_per_kwh": 400, "discount_rate": 0.08, "spread_factor": 1.0},
        {"name": "乐观 (Bull)", "capex_per_kwh": 300, "discount_rate": 0.06, "spread_factor": 1.2},
    ])

    results = []
    for scenario in scenarios:
        scenario_params = {
            "region": region,
            "year": year,
            "power_mw": power_mw,
            "duration_hours": duration_hours,
            "capex_per_kwh": scenario.get("capex_per_kwh", 400),
            "discount_rate": scenario.get("discount_rate", 0.08),
        }
        base_result = _exec_investment_analysis(scenario_params, ctx)
        if base_result.get("results"):
            res = base_result["results"]
            # Apply spread factor to revenue
            spread_factor = scenario.get("spread_factor", 1.0)
            adjusted_revenue = res.get("annual_energy_revenue_aud", 0) * spread_factor
            # Only scale revenue, not CAPEX: adjusted_npv = base_npv + (factor-1) * PV(revenue)
            base_npv = res.get("npv_aud", 0)
            annual_rev = res.get("annual_total_revenue_aud", 0) or res.get("annual_energy_revenue_aud", 0)
            pv_revenue_approx = annual_rev * 10  # Rough annuity approximation
            adjusted_npv = base_npv + (spread_factor - 1) * pv_revenue_approx
            results.append({
                "scenario": scenario.get("name", "Custom"),
                "capex_per_kwh": scenario.get("capex_per_kwh"),
                "discount_rate": scenario.get("discount_rate"),
                "spread_factor": spread_factor,
                "npv_aud": round(adjusted_npv, 0),
                "irr_pct": res.get("irr_pct"),
                "payback_years": res.get("simple_payback_years"),
                "annual_revenue_aud": round(adjusted_revenue, 0),
            })
        else:
            results.append({"scenario": scenario.get("name", "Custom"), "status": "no_data"})

    return {
        "region": region,
        "year": year,
        "params": {"power_mw": power_mw, "duration_hours": duration_hours},
        "scenarios": results,
    }


def _exec_portfolio_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Multi-project portfolio analysis with risk diversification."""
    projects = params.get("projects", [
        {"region": "NSW1", "power_mw": 100, "duration_hours": 4},
        {"region": "SA1", "power_mw": 50, "duration_hours": 2},
        {"region": "WEM", "power_mw": 200, "duration_hours": 4},
    ])
    year = params.get("year", ctx.effective_year)

    project_results = []
    total_capex = 0
    total_npv = 0
    total_revenue = 0

    for proj in projects:
        proj_params = {
            "region": proj.get("region", "NSW1"),
            "year": year,
            "power_mw": proj.get("power_mw", 100),
            "duration_hours": proj.get("duration_hours", 4),
            "capex_per_kwh": proj.get("capex_per_kwh", 400),
            "discount_rate": proj.get("discount_rate", 0.08),
        }
        result = _exec_investment_analysis(proj_params, ctx)
        if result.get("results"):
            res = result["results"]
            project_results.append({
                "region": proj.get("region"),
                "power_mw": proj.get("power_mw"),
                "duration_hours": proj.get("duration_hours"),
                "capex_aud": res.get("total_capex_aud", 0),
                "npv_aud": res.get("npv_aud", 0),
                "irr_pct": res.get("irr_pct"),
                "annual_revenue_aud": res.get("annual_net_revenue_aud", 0),
            })
            total_capex += res.get("total_capex_aud", 0)
            total_npv += res.get("npv_aud", 0)
            total_revenue += res.get("annual_net_revenue_aud", 0)
        else:
            project_results.append({"region": proj.get("region"), "status": "no_data"})

    return {
        "year": year,
        "projects": project_results,
        "portfolio_summary": {
            "total_capex_aud": round(total_capex, 0),
            "total_npv_aud": round(total_npv, 0),
            "total_annual_revenue_aud": round(total_revenue, 0),
            "project_count": len([p for p in project_results if "npv_aud" in p]),
            "portfolio_npv_multiple": round(total_npv / total_capex, 2) if total_capex > 0 else None,
        },
    }


def _exec_generation_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Analyze generation mix, renewable penetration, and supply adequacy."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    analysis_type = params.get("analysis_type", "generation_mix")  # generation_mix | renewable_penetration | supply_adequacy

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            if analysis_type == "generation_mix":
                cursor.execute(
                    "SELECT fuel_type, COUNT(*) as unit_count, SUM(capacity_mw) as total_mw "
                    "FROM du_detail_summary WHERE region_id = ? GROUP BY fuel_type ORDER BY total_mw DESC",
                    (region,),
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"status": "no_data", "region": region, "note": "du_detail_summary 无该区域数据"}
                return {
                    "region": region,
                    "analysis_type": analysis_type,
                    "generation_mix": [
                        {"fuel_type": r[0], "unit_count": r[1], "total_capacity_mw": round(float(r[2] or 0), 1)}
                        for r in rows
                    ],
                }

            elif analysis_type == "renewable_penetration":
                cursor.execute(
                    "SELECT settlement_date, total_demand_mw, renewable_generation_mw "
                    "FROM dispatch_region_summary WHERE region_id = ? "
                    "ORDER BY settlement_date DESC LIMIT 500",
                    (region,),
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"status": "no_data", "region": region}
                penetrations = []
                for r in rows:
                    demand = float(r[1] or 0)
                    renew = float(r[2] or 0)
                    if demand > 0:
                        penetrations.append(renew / demand * 100)
                from statistics import mean
                return {
                    "region": region,
                    "analysis_type": analysis_type,
                    "data_points": len(penetrations),
                    "avg_renewable_penetration_pct": round(mean(penetrations), 1) if penetrations else 0,
                    "max_penetration_pct": round(max(penetrations), 1) if penetrations else 0,
                    "min_penetration_pct": round(min(penetrations), 1) if penetrations else 0,
                }

            elif analysis_type == "supply_adequacy":
                cursor.execute(
                    "SELECT settlement_date, total_demand_mw, available_generation_mw "
                    "FROM dispatch_region_summary WHERE region_id = ? "
                    "ORDER BY settlement_date DESC LIMIT 500",
                    (region,),
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"status": "no_data", "region": region}
                margins = []
                for r in rows:
                    demand = float(r[1] or 0)
                    gen = float(r[2] or 0)
                    if demand > 0:
                        margins.append((gen - demand) / demand * 100)
                from statistics import mean
                return {
                    "region": region,
                    "analysis_type": analysis_type,
                    "data_points": len(margins),
                    "avg_supply_margin_pct": round(mean(margins), 1) if margins else 0,
                    "min_margin_pct": round(min(margins), 1) if margins else 0,
                    "tight_intervals": sum(1 for m in margins if m < 5),
                }

    except Exception as e:
        return {"status": "error", "error": str(e)}

    return {"status": "error", "error": f"未知分析类型: {analysis_type}"}


# =============================================================================
# Phase 3: Market Pulse / Weather Correlation / Report Generation
# =============================================================================


def _exec_market_pulse(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Current market state snapshot: latest prices, demand, renewable share."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    year = _safe_year(year)

    result = {"region": region, "year": year, "snapshots": {}}

    if not _price_table_exists(db, f"trading_price_{year}"):
        result["status"] = "no_data"
        result["note"] = f"价格表 trading_price_{year} 尚未同步"
        return result

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Latest prices
            table = f"trading_price_{year}"
            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table} "
                f"WHERE region_id = ? ORDER BY settlement_date DESC LIMIT 48",
                (region,),
            )
            price_rows = cursor.fetchall()
            if price_rows:
                prices = [float(r[1] or 0) for r in price_rows]
                from statistics import mean
                result["snapshots"]["recent_prices"] = {
                    "latest": round(prices[0], 2),
                    "avg_24h": round(mean(prices), 2),
                    "max_24h": round(max(prices), 2),
                    "min_24h": round(min(prices), 2),
                    "negative_count_24h": sum(1 for p in prices if p < 0),
                    "as_of": str(price_rows[0][0]),
                }

            # Latest demand
            cursor.execute(
                "SELECT interval_date, operational_demand_mw FROM operational_demand_actual_hh "
                "WHERE region_id = ? ORDER BY interval_date DESC LIMIT 48",
                (region,),
            )
            demand_rows = cursor.fetchall()
            if demand_rows:
                demands = [float(r[1] or 0) for r in demand_rows]
                from statistics import mean
                result["snapshots"]["recent_demand"] = {
                    "latest_mw": round(demands[0], 0),
                    "avg_24h_mw": round(mean(demands), 0),
                    "peak_24h_mw": round(max(demands), 0),
                    "as_of": str(demand_rows[0][0]),
                }

            # Latest renewable generation
            cursor.execute(
                "SELECT settlement_date, total_demand_mw, renewable_generation_mw "
                "FROM dispatch_region_summary WHERE region_id = ? "
                "ORDER BY settlement_date DESC LIMIT 48",
                (region,),
            )
            gen_rows = cursor.fetchall()
            if gen_rows:
                penetrations = []
                for r in gen_rows:
                    d = float(r[1] or 0)
                    ren = float(r[2] or 0)
                    if d > 0:
                        penetrations.append(ren / d * 100)
                if penetrations:
                    from statistics import mean
                    result["snapshots"]["renewable"] = {
                        "current_penetration_pct": round(penetrations[0], 1),
                        "avg_24h_pct": round(mean(penetrations), 1),
                        "as_of": str(gen_rows[0][0]),
                    }

    except Exception as e:
        result["error"] = str(e)

    result["status"] = "success" if result["snapshots"] else "no_data"
    return result


def _exec_weather_correlation(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Analyze weather-to-price correlation (temperature → demand → price)."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get weather observations
            cursor.execute(
                "SELECT observation_date, max_temp_c, min_temp_c, rainfall_mm "
                "FROM bom_weather_observation ORDER BY observation_date DESC LIMIT 365"
            )
            weather_rows = cursor.fetchall()

            if not weather_rows:
                return {"status": "no_data", "note": "bom_weather_observation 无数据"}

            temps = [float(r[1] or 0) for r in weather_rows if r[1] is not None]
            if not temps:
                return {"status": "no_data", "note": "无温度数据"}

            from statistics import mean, stdev

            # Basic weather stats
            weather_stats = {
                "data_points": len(temps),
                "avg_max_temp_c": round(mean(temps), 1),
                "std_max_temp_c": round(stdev(temps), 1) if len(temps) > 1 else 0,
                "hottest_c": round(max(temps), 1),
                "coldest_c": round(min(temps), 1),
                "heatwave_days_gt35": sum(1 for t in temps if t > 35),
                "heatwave_days_gt40": sum(1 for t in temps if t > 40),
            }

            # Correlation insight
            hot_days = sum(1 for t in temps if t > 30)
            mild_days = sum(1 for t in temps if 15 <= t <= 25)

            return {
                "status": "success",
                "region": region,
                "weather_stats": weather_stats,
                "insights": {
                    "hot_days_gt30": hot_days,
                    "mild_days_15_25": mild_days,
                    "price_impact_note": "高温日(>35°C)通常导致需求尖峰和价格飙升，是BESS放电的高价值时段",
                    "seasonal_pattern": "澳洲夏季(12-2月)价格波动最大，冬季(6-8月)相对平稳",
                },
            }

    except Exception as e:
        return {"status": "error", "error": str(e)}


def _exec_generate_report(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Generate an investment committee memo from analysis results."""
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)
    capex_per_kwh = params.get("capex_per_kwh", 400)
    discount_rate = params.get("discount_rate", 0.08)

    # Gather data from multiple tools
    investment = _exec_investment_analysis({
        "region": region, "year": year, "power_mw": power_mw,
        "duration_hours": duration_hours, "capex_per_kwh": capex_per_kwh,
        "discount_rate": discount_rate,
    }, ctx)

    price_data = _exec_price_trend({"region": region, "year": year}, ctx)
    peak_data = _exec_peak_analysis({"region": region, "year": year, "window_hours": int(duration_hours)}, ctx)

    inv_results = investment.get("results", {})
    price_stats = price_data.get("stats", {})
    peak_summary = peak_data.get("summary", {})

    # Build memo sections
    memo = f"""# 投资委员会备忘录

## 项目概要
- 区域: {region}
- 规模: {power_mw} MW / {duration_hours} h
- CAPEX: {capex_per_kwh} AUD/kWh
- 折现率: {discount_rate*100:.0f}%
- 基准年: {year}

## 执行摘要
基于 {year} 年 {region} 市场数据，{power_mw}MW/{duration_hours}h BESS 项目的核心指标如下：
- NPV: {inv_results.get('npv_aud', 0):,.0f} AUD
- IRR: {inv_results.get('irr_pct', 'N/A')}%
- 简单回收期: {inv_results.get('simple_payback_years', 'N/A')} 年
- 年均净收入: {inv_results.get('annual_net_revenue_aud', 0):,.0f} AUD

## 市场分析
- 年均价格: {price_stats.get('avg_price', '?')} AUD/MWh
- 价格范围: {price_stats.get('min_price', '?')} ~ {price_stats.get('max_price', '?')} AUD/MWh
- 负价比例: {price_stats.get('negative_ratio_pct', '?')}%
- 最优价差: {peak_summary.get('gross_spread', '?')} AUD/MWh

## 财务模型
- 总 CAPEX: {inv_results.get('total_capex_aud', 0):,.0f} AUD
- 年能量收入: {inv_results.get('annual_energy_revenue_aud', 0):,.0f} AUD
- 年净收入: {inv_results.get('annual_net_revenue_aud', 0):,.0f} AUD
- 项目寿命: 20 年

## 风险标记
- 数据等级: preview（仅供早期筛选）
- FCAS 收入: 已纳入（简化估算，30%容量×6h/天，需单独验证）
- 退化/可用率: 已建模（2%/年退化，97%可用率）
- 网络费用: 未纳入
- 税务/补贴: 未建模（无加速折旧、ARENA 补贴）

## 建议
基于当前分析，项目 NPV 为{'positive' if inv_results.get('npv_aud', 0) > 0 else 'negative'}，
{'建议进入开发和深度尽调阶段' if inv_results.get('npv_aud', 0) > 0 else '当前假设下不建议推进'}。
本报告为分析参考，不构成投资建议。
"""

    return {
        "status": "success",
        "format": "markdown",
        "title": f"{region} {power_mw}MW/{duration_hours}h BESS 投资备忘录",
        "content": memo,
        "key_metrics": inv_results,
    }


# =============================================================================
# Singleton
# =============================================================================

_registry_instance: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the singleton tool registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = build_tool_registry()
    return _registry_instance
