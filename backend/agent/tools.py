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
                loop = asyncio.get_event_loop()
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
    """Execute FCAS opportunity analysis."""
    from deps import get_db
    from fcas_opportunity import summarize_nem_fcas_opportunity

    db = get_db()
    region = params.get("region", ctx.effective_region)
    year = params.get("year", ctx.effective_year)
    capacity_mw = params.get("capacity_mw", 100.0)
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

    result = summarize_nem_fcas_opportunity(rows, capacity_mw=capacity_mw, duration_hours=2.0)
    return {"region": region, "year": year, "has_fcas_data": True, **result}


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

    region = params.get("region", ctx.effective_region)
    current_capacity_mw = params.get("current_capacity_mw", 500.0)
    growth_rate_pct = params.get("growth_rate_pct", 20.0)
    years = params.get("years", 10)

    engine = CannibalizationEngine()
    result = engine.project_revenue_dilution(
        region=region,
        current_capacity_mw=current_capacity_mw,
        annual_growth_rate_pct=growth_rate_pct,
        projection_years=years,
    )
    return {"region": region, **result} if isinstance(result, dict) else {"region": region, "result": str(result)}


def _exec_fcas_collapse_forecast(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute FCAS collapse forecast."""
    from engines.fcas_collapse_engine import FcasCollapseEngine

    region = params.get("region", ctx.effective_region)
    engine = FcasCollapseEngine()
    result = engine.forecast(region=region)
    return {"region": region, **result} if isinstance(result, dict) else {"region": region, "result": str(result)}


def _exec_regional_timing_score(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute regional timing scorer."""
    from engines.regional_timing_engine import RegionalTimingEngine
    from deps import get_db

    db = get_db()
    region = params.get("region", ctx.effective_region)
    engine = RegionalTimingEngine(db)
    result = engine.score(region=region)
    return {"region": region, **result} if isinstance(result, dict) else {"region": region, "result": str(result)}


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
    from models.forward_price_models import EventRegistry

    region = params.get("region", ctx.effective_region)
    years = params.get("projection_years", 20)

    registry = EventRegistry()
    engine = ForwardPriceEngine(registry)
    result = engine.project(region=region, projection_years=years)
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
    result = engine.run(price_data=rows)
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

    # Estimate annual arbitrage revenue (simplified)
    sorted_p = sorted(prices)
    n = len(sorted_p)
    window = max(1, n // 12)
    charge_cost = sum(sorted_p[:window]) / window
    discharge_rev = sum(sorted_p[-window:]) / window
    spread = discharge_rev - charge_cost
    intervals_per_year = 17520  # NEM 5-min intervals
    rte = 0.87
    annual_energy_revenue = spread * power_mw * (intervals_per_year / 12) * rte

    # Simple NPV
    project_life = 20
    annual_om = power_mw * 15000  # $15k/MW/year
    net_annual = annual_energy_revenue - annual_om
    npv = sum(net_annual / (1 + discount_rate) ** t for t in range(1, project_life + 1)) - total_capex
    simple_payback = total_capex / net_annual if net_annual > 0 else float("inf")

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
            "annual_net_revenue_aud": round(net_annual, 0),
            "npv_aud": round(npv, 0),
            "simple_payback_years": round(simple_payback, 1) if simple_payback != float("inf") else None,
            "avg_spread_aud_mwh": round(spread, 2),
        },
    }


def _exec_risk_stratification(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute revenue risk stratification."""
    from engines.risk_stratification_engine import RiskStratificationEngine
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
        rows = [{"settlement_date": r[0], "rrp_aud_mwh": float(r[1] or 0.0)} for r in cursor.fetchall()]

    if not rows:
        return {"region": region, "status": "no_data"}

    engine = RiskStratificationEngine()
    result = engine.stratify_historical_revenue(rows, power_mw=params.get("power_mw", 100.0))
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
    from pathlib import Path
    from engines.cross_validation_service import CrossValidationService
    from models.forward_price_models import EventRegistry

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    evidence_path = data_dir / "financial_evidence.json"
    registry = EventRegistry()

    service = CrossValidationService(evidence_path=evidence_path, event_registry=registry)
    result = service.validate()
    if hasattr(result, "model_dump"):
        return result.model_dump()
    elif isinstance(result, dict):
        return result
    return {"result": str(result)}


def _exec_narrative_attribution(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute narrative causal attribution."""
    from engines.narrative_engine import NarrativeEngine
    from models.forward_price_models import EventRegistry

    region = params.get("region", ctx.effective_region)
    module_name = params.get("module_name", "investment_analysis")
    metric_name = params.get("metric_name", "npv")
    metric_value = params.get("metric_value", 0.0)

    registry = EventRegistry()
    engine = NarrativeEngine(registry)
    result = engine.generate_attribution(
        region=region,
        module_name=module_name,
        metric_name=metric_name,
        metric_value=metric_value,
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

    return registry


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
