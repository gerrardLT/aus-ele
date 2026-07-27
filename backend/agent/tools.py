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
import re
import time
from typing import Any, Callable, Dict, List, Optional

from agent.schemas import AgentContext, ToolDefinition, ToolResult, ToolStatus

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

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Convert all tool definitions to OpenAI tools format."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

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
        try:
            # Run synchronous executors in thread pool to avoid blocking
            if asyncio.iscoroutinefunction(executor):
                data = await asyncio.wait_for(
                    executor(arguments, context),
                    timeout=timeout_seconds,
                )
            else:
                loop = asyncio.get_running_loop()
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, executor, arguments, context),
                    timeout=timeout_seconds,
                )
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                call_id=call_id,
                status=ToolStatus.SUCCESS,
                data=data,
                metadata={"duration_ms": round(duration_ms, 1)},
                duration_ms=round(duration_ms, 1),
            )
        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning("Tool %s timed out after %.1fs", tool_name, timeout_seconds)
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


def _exec_market_screening(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute market screening across all regions."""
    from deps import get_db
    from market_screening import build_market_screening_payload

    db = get_db()
    year = params.get("year", ctx.effective_year)
    return build_market_screening_payload(db, year=year)


def _exec_price_trend(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute price trend analysis for a region."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    year = _safe_year(year)
    table_name = f"trading_price_{year}"

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
    return {"region": region, "year": year, "stats": stats}


def _exec_regional_ranking(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute regional investment ranking."""
    from deps import get_db
    from market_screening import build_market_screening_payload

    db = get_db()
    year = params.get("year", ctx.effective_year)
    payload = build_market_screening_payload(db, year=year)
    # Filter to NEM regions only for ranking
    candidates = payload.get("candidates", [])
    nem_ranked = [c for c in candidates if c.get("market") == "NEM"]
    return {"year": year, "ranking": nem_ranked}


def _exec_spike_profit(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute spike profit analysis."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    threshold = params.get("threshold_aud_mwh", 300.0)
    year = _safe_year(year)
    table_name = f"trading_price_{year}"

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
    return {"region": region, "year": year, "has_fcas_data": True, **result}


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
                "total_net_incremental_revenue_k": 0,
                "viable_service_count": 0,
            },
        }

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wem_ess_market_price ORDER BY 1 DESC LIMIT 100")
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {
        "region": region,
        "market": "WEM",
        "has_fcas_data": True,
        "service_type": "ESS (Essential System Services)",
        "data_points": len(rows),
        "summary": {
            "note": "WEM ESS 数据量有限，结果仅供参考",
            "total_net_incremental_revenue_k": 0,
            "viable_service_count": 0,
        },
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

    engine = CoOptimizationEngine(battery, config)

    # Transform row data to engine expected format
    energy_prices = [
        {
            "timestamp": r.get("settlement_date", ""),
            "price": float(r.get("rrp_aud_mwh") or 0.0),
            "interval_hours": 5.0 / 60.0,
        }
        for r in rows
    ]
    fcas_prices = {}
    for svc in config.fcas_services:
        col = f"{svc}_rrp"
        fcas_prices[svc] = [float(r.get(col) or 0.0) for r in rows]

    result = engine.optimize(energy_prices=energy_prices, fcas_prices=fcas_prices)
    if hasattr(result, "__dict__"):
        return {k: v for k, v in vars(result).items() if not k.startswith("_")}
    return {"region": region, "year": year, "result": str(result)}


def _exec_investment_analysis(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute investment NPV/IRR analysis."""
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    power_mw = params.get("power_mw", 100.0)
    duration_hours = params.get("duration_hours", 4.0)
    capex_per_kwh = params.get("capex_per_kwh", 350.0)
    discount_rate = params.get("discount_rate", 0.08)

    # Simplified investment calculation
    capacity_mwh = power_mw * duration_hours
    total_capex = capacity_mwh * 1000 * capex_per_kwh  # kWh * $/kWh

    # Get revenue estimate from price data
    year = _safe_year(year)
    table_name = f"trading_price_{year}"
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT rrp_aud_mwh FROM {table_name} "
            f"WHERE region_id = ? ORDER BY settlement_date ASC",
            (region,),
        )
        prices = [float(r[0] or 0.0) for r in cursor.fetchall()]

    if not prices:
        return {"region": region, "status": "no_data"}

    # Estimate annual arbitrage revenue (duration-aware model)
    # Window size scales with duration: longer battery captures wider spread
    sorted_p = sorted(prices)
    n = len(sorted_p)
    # Intervals per day: WEM uses 30-min (48/day), NEM uses 5-min (288/day)
    intervals_per_day = 48 if region == "WEM" else 288
    # Charge/discharge window = duration_hours worth of intervals per day
    window_per_day = max(1, int(duration_hours * (intervals_per_day / 24)))
    # Annual window = daily window * 365
    window = max(1, min(window_per_day * 365, n // 4))

    charge_cost = sum(sorted_p[:window]) / window
    discharge_rev = sum(sorted_p[-window:]) / window
    spread = discharge_rev - charge_cost

    rte = 0.87  # Round-trip efficiency
    availability = 0.97  # 3% downtime for maintenance
    degradation_rate = 0.02  # 2% annual capacity fade
    # Annual cycles: assume ~350 profitable cycles/year
    annual_cycles = 350
    # Energy per cycle constrained by duration
    energy_per_cycle_mwh = power_mw * duration_hours
    annual_energy_revenue = spread * energy_per_cycle_mwh * annual_cycles * rte * availability

    # FCAS revenue estimate (from FCAS price columns if available)
    fcas_annual_revenue = 0.0
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
                # Estimate: 30% of capacity in FCAS, 6h/day enabled, $/MW per interval
                avg_fcas_price = (float(fcas_row[0] or 0) + float(fcas_row[1] or 0)) / 2
                fcas_capacity_mw = power_mw * 0.3
                fcas_hours_per_year = 6 * 365
                fcas_annual_revenue = avg_fcas_price * fcas_capacity_mw * fcas_hours_per_year * 0.5
    except Exception:
        pass  # FCAS columns may not exist for WEM

    # NPV calculation with degradation (year-by-year)
    project_life = 20
    annual_om = power_mw * 15000  # $15k/MW/year
    total_revenue_y1 = annual_energy_revenue + fcas_annual_revenue
    npv = -total_capex
    yearly_cashflows = []
    for t in range(1, project_life + 1):
        # Apply degradation: capacity fades 2% per year
        degradation_factor = (1 - degradation_rate) ** (t - 1)
        year_revenue = total_revenue_y1 * degradation_factor
        year_net = year_revenue - annual_om
        npv += year_net / (1 + discount_rate) ** t
        yearly_cashflows.append(round(year_net, 0))

    net_annual = total_revenue_y1 - annual_om  # Year 1 net
    simple_payback = total_capex / net_annual if net_annual > 0 else float("inf")

    # IRR calculation (bisection method with degradation)
    irr = None
    if net_annual > 0:
        lo, hi = -0.5, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            irr_npv = -total_capex
            for t in range(1, project_life + 1):
                deg = (1 - degradation_rate) ** (t - 1)
                irr_npv += (total_revenue_y1 * deg - annual_om) / (1 + mid) ** t
            if irr_npv > 0:
                lo = mid
            else:
                hi = mid
        irr = round((lo + hi) / 2, 4)

    return {
        "region": region,
        "year": year,
        "params": {
            "power_mw": power_mw,
            "duration_hours": duration_hours,
            "capex_per_kwh": capex_per_kwh,
            "discount_rate": discount_rate,
        },
        "results": {
            "total_capex_aud": round(total_capex, 0),
            "annual_energy_revenue_aud": round(annual_energy_revenue, 0),
            "annual_fcas_revenue_aud": round(fcas_annual_revenue, 0),
            "annual_total_revenue_aud": round(total_revenue_y1, 0),
            "annual_net_revenue_aud": round(net_annual, 0),
            "npv_aud": round(npv, 0),
            "irr_pct": round(irr * 100, 2) if irr is not None else None,
            "simple_payback_years": round(simple_payback, 1) if simple_payback != float("inf") else None,
            "avg_spread_aud_mwh": round(spread, 2),
            "energy_per_cycle_mwh": round(energy_per_cycle_mwh, 1),
            "annual_cycles": annual_cycles,
            "model_assumptions": {
                "round_trip_efficiency": rte,
                "availability": availability,
                "degradation_rate_annual": degradation_rate,
                "fcas_capacity_pct": 0.3,
                "project_life_years": project_life,
            },
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
    ranked = sorted(
        [r for r in results if r.get("results", {}).get("npv_aud") is not None],
        key=lambda r: r["results"]["npv_aud"],
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
            if result.get("results"):
                results.append(result)
            else:
                results.append({"region": region, "status": result.get("status", "no_data")})
        except Exception as e:
            results.append({"region": region, "status": "error", "error": str(e)})

    # Separate NEM and WEM
    nem_results = [r for r in results if r.get("region") != "WEM" and r.get("results")]
    wem_result = next((r for r in results if r.get("region") == "WEM" and r.get("results")), None)

    # Best NEM region
    best_nem = max(nem_results, key=lambda r: r["results"]["npv_aud"]) if nem_results else None

    comparison = {
        "markets_analyzed": ["NEM", "WEM"],
        "year": year,
        "params": {"power_mw": power_mw, "duration_hours": duration_hours},
        "nem_best": {
            "region": best_nem["region"],
            **best_nem["results"],
        } if best_nem else None,
        "wem": wem_result.get("results") if wem_result else {"status": "no_data"},
        "all_regions": [
            {"region": r.get("region"), "npv": r.get("results", {}).get("npv_aud"), "irr": r.get("results", {}).get("irr_pct")}
            for r in results
        ],
        "recommendation": "",
    }

    # Generate recommendation
    if best_nem and wem_result and wem_result.get("results"):
        nem_npv = best_nem["results"]["npv_aud"]
        wem_npv = wem_result["results"]["npv_aud"]
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
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|EXECUTE)\b",
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
        return {"status": "error", "error": "SQL 包含禁止关键词（INSERT/UPDATE/DELETE/DROP等）"}

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

    # --- Stage 2: Revenue Deep Dive ---
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
            description="Run BESS investment NPV/IRR analysis with given parameters. Returns capex, annual revenue, NPV, and payback period.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region code"},
                    "year": {"type": "integer", "description": "Base year for revenue estimation"},
                    "power_mw": {"type": "number", "description": "BESS power (MW)"},
                    "duration_hours": {"type": "number", "description": "BESS duration (hours)"},
                    "capex_per_kwh": {"type": "number", "description": "CAPEX per kWh (AUD)"},
                    "discount_rate": {"type": "number", "description": "Discount rate (e.g. 0.08)"},
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
                    "sql": {"type": "string", "description": "SQL SELECT query to execute"},
                },
                "required": ["sql"],
            },
            stage="Data Exploration",
        ),
        _exec_data_query,
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
            adjusted_npv = res.get("npv_aud", 0) * spread_factor  # Simplified scaling
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
- FCAS 收入: 未纳入（需单独验证）
- 退化/可用率: 未建模
- 网络费用: 未纳入

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
