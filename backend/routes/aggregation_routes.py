"""Aggregation API routes — market-summary and stage-summary endpoints.

Provides aggregated metrics for the Executive Summary and Decision Funnel
stages, reducing frontend request count and enabling single-call data loading.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from deps import get_cache, get_db
from network_fees import get_default_fee, get_settlement_interval
from result_metadata import build_result_metadata

logger = logging.getLogger(__name__)

router = APIRouter(tags=["aggregation"])

# ---------------------------------------------------------------------------
# Pydantic Response Models
# ---------------------------------------------------------------------------


class KpiMetric(BaseModel):
    """A single KPI metric with semantic sentiment."""

    label: str
    value: float | str
    unit: str
    sentiment: Literal["positive", "negative", "neutral", "warning"]


class Warning(BaseModel):
    """A warning indicating partial data or computation failure."""

    stage: str
    metric: str | None = None
    reason: str
    severity: Literal["degraded", "error"]


class StageSummaryData(BaseModel):
    """Summary data for a single funnel stage."""

    summary_text: str
    sentiment: Literal["positive", "negative", "neutral"]
    kpis: list[KpiMetric]


class BessParams(BaseModel):
    """BESS parameters included in the response."""

    power_mw: float
    duration_hours: float
    round_trip_efficiency: float


class MarketSummaryResponse(BaseModel):
    """Full market-summary response conforming to the API contract."""

    market: str
    region: str
    year: int
    bess_params: BessParams
    stages: dict[str, StageSummaryData | None]
    overall_rating: Literal[
        "strong_opportunity", "moderate_opportunity", "weak_opportunity", "unfavorable"
    ]
    metadata: dict[str, Any]
    warnings: list[Warning]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MARKETS = {"NEM", "WEM"}
VALID_NEM_REGIONS = {"NSW1", "QLD1", "VIC1", "SA1", "TAS1"}
VALID_WEM_REGIONS = {"WEM"}

# Valid stage IDs (hyphenated URL form → underscore registry key)
VALID_STAGE_IDS = {
    "market-opportunity",
    "opportunity-identification",
    "revenue-estimation",
    "investment-decision",
}

# Cache configuration
CACHE_SCOPE_MARKET_SUMMARY = "api_market_summary_v1"
CACHE_SCOPE_STAGE_SUMMARY = "api_stage_summary_v1"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours

REGION_TIMEZONES = {
    "NSW1": "Australia/Sydney",
    "QLD1": "Australia/Brisbane",
    "VIC1": "Australia/Melbourne",
    "SA1": "Australia/Adelaide",
    "TAS1": "Australia/Hobart",
    "WEM": "Australia/Perth",
}


# ---------------------------------------------------------------------------
# Stage Computation Functions
# ---------------------------------------------------------------------------


def _compute_market_opportunity(
    market: str,
    region: str,
    year: int,
    bess_duration_hours: float,
) -> StageSummaryData:
    """Stage 1: Compute market opportunity metrics from price data.

    Queries price data for the year/region, computes avg spread,
    max spread, and negative price ratio.
    """
    db = get_db()
    table_name = f"trading_price_{year}"

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Check table exists
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (table_name,),
        )
        if not cursor.fetchone():
            raise DataUnavailableError(
                f"No price data for year {year}", metric_name="price_spread"
            )

        # Determine region filter
        if market == "WEM":
            region_clause = "1=1"
            region_params: list = []
        else:
            region_clause = "region_id = ?"
            region_params = [region]

        # Get basic price statistics
        stats_query = f"""
            SELECT
                AVG(rrp_aud_mwh) as avg_price,
                MAX(rrp_aud_mwh) as max_price,
                MIN(rrp_aud_mwh) as min_price,
                COUNT(*) as total_intervals,
                SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as neg_count
            FROM {table_name}
            WHERE {region_clause}
        """
        cursor.execute(stats_query, tuple(region_params))
        row = cursor.fetchone()

        if not row or row[3] == 0:
            raise DataUnavailableError(
                f"No price data for {region} in {year}", metric_name="price_spread"
            )

        avg_price, max_price, min_price, total_intervals, neg_count = row

        # Compute approximate 4h spread using daily max-min as proxy
        # (Full sliding window is too expensive for summary endpoint)
        spread_query = f"""
            SELECT AVG(daily_spread), MAX(daily_spread)
            FROM (
                SELECT
                    substr(settlement_date, 1, 10) as day,
                    MAX(rrp_aud_mwh) - MIN(rrp_aud_mwh) as daily_spread
                FROM {table_name}
                WHERE {region_clause}
                GROUP BY day
            )
        """
        cursor.execute(spread_query, tuple(region_params))
        spread_row = cursor.fetchone()

        avg_spread = round(spread_row[0], 1) if spread_row and spread_row[0] else 0.0
        max_spread = round(spread_row[1], 1) if spread_row and spread_row[1] else 0.0
        neg_ratio = round((neg_count / total_intervals) * 100, 1) if total_intervals > 0 else 0.0

    # Determine sentiment based on spread magnitude
    if avg_spread >= 40:
        sentiment = "positive"
    elif avg_spread >= 20:
        sentiment = "neutral"
    else:
        sentiment = "negative"

    summary_text = (
        f"{region} {year}年平均日价差 ${avg_spread}/MWh，"
        f"{'存在显著套利机会' if sentiment == 'positive' else '套利空间有限' if sentiment == 'neutral' else '套利机会较弱'}"
    )

    kpis = [
        KpiMetric(
            label="平均日价差",
            value=avg_spread,
            unit="$/MWh",
            sentiment="positive" if avg_spread >= 40 else "neutral" if avg_spread >= 20 else "negative",
        ),
        KpiMetric(
            label="最大日价差",
            value=max_spread,
            unit="$/MWh",
            sentiment="positive" if max_spread >= 100 else "neutral",
        ),
        KpiMetric(
            label="负电价占比",
            value=neg_ratio,
            unit="%",
            sentiment="positive" if neg_ratio >= 5 else "neutral",
        ),
    ]

    return StageSummaryData(summary_text=summary_text, sentiment=sentiment, kpis=kpis)


def _compute_opportunity_identification(
    market: str,
    region: str,
    year: int,
    bess_power_mw: float,
    bess_duration_hours: float,
) -> StageSummaryData:
    """Stage 2: Identify best charge/discharge windows and FCAS potential.

    Uses price data to identify optimal trading windows.
    """
    db = get_db()
    table_name = f"trading_price_{year}"

    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (table_name,),
        )
        if not cursor.fetchone():
            raise DataUnavailableError(
                f"No price data for year {year}", metric_name="opportunity_windows"
            )

        # Determine region filter
        if market == "WEM":
            region_clause = "1=1"
            region_params: list = []
        else:
            region_clause = "region_id = ?"
            region_params = [region]

        # Find cheapest hours (best charging windows)
        hourly_avg_query = f"""
            SELECT
                EXTRACT(HOUR FROM settlement_date::timestamp - INTERVAL '1 second')::integer as hour,
                AVG(rrp_aud_mwh) as avg_price
            FROM {table_name}
            WHERE {region_clause}
            GROUP BY hour
            ORDER BY avg_price ASC
        """
        cursor.execute(hourly_avg_query, tuple(region_params))
        hourly_rows = cursor.fetchall()

        if not hourly_rows:
            raise DataUnavailableError(
                f"No hourly data for {region} in {year}",
                metric_name="opportunity_windows",
            )

        # Best charging window: cheapest consecutive hours matching duration
        cheapest_hour = hourly_rows[0][0] if hourly_rows else 2
        charge_window_start = f"{cheapest_hour:02d}:00"
        charge_window_end = f"{(cheapest_hour + int(bess_duration_hours)) % 24:02d}:00"

        # Estimate FCAS revenue potential (simplified: based on price volatility)
        volatility_query = f"""
            SELECT
                AVG(ABS(rrp_aud_mwh - (
                    SELECT AVG(rrp_aud_mwh) FROM {table_name} WHERE {region_clause}
                ))) as avg_deviation
            FROM {table_name}
            WHERE {region_clause}
        """
        cursor.execute(volatility_query, tuple(region_params * 2))
        vol_row = cursor.fetchone()
        price_volatility = vol_row[0] if vol_row and vol_row[0] else 0.0

    # Estimate annual FCAS revenue based on volatility and capacity
    # Higher volatility = more FCAS opportunity
    fcas_annual_estimate = round(bess_power_mw * price_volatility * 365 * 0.3, 0)

    sentiment = "positive" if fcas_annual_estimate > 1_000_000 else "neutral" if fcas_annual_estimate > 500_000 else "negative"

    summary_text = (
        f"最佳充电窗口集中在{charge_window_start}-{charge_window_end}，"
        f"FCAS年收入潜力约${fcas_annual_estimate:,.0f}"
    )

    kpis = [
        KpiMetric(
            label="FCAS年收入潜力",
            value=fcas_annual_estimate,
            unit="$",
            sentiment=sentiment,
        ),
        KpiMetric(
            label="最优充电时段",
            value=f"{charge_window_start}-{charge_window_end}",
            unit="",
            sentiment="neutral",
        ),
    ]

    return StageSummaryData(summary_text=summary_text, sentiment=sentiment, kpis=kpis)


def _compute_revenue_estimation(
    market: str,
    region: str,
    year: int,
    bess_power_mw: float,
    bess_duration_hours: float,
    bess_efficiency: float,
) -> StageSummaryData:
    """Stage 3: Estimate BESS revenue using simplified backtest.

    Uses daily spread data to estimate revenue without running full LP optimization.
    """
    db = get_db()
    table_name = f"trading_price_{year}"

    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (table_name,),
        )
        if not cursor.fetchone():
            raise DataUnavailableError(
                f"No price data for year {year}", metric_name="revenue_estimation"
            )

        # Determine region filter
        if market == "WEM":
            region_clause = "1=1"
            region_params: list = []
        else:
            region_clause = "region_id = ?"
            region_params = [region]

        # Compute daily revenue estimate from daily spreads
        # Revenue ≈ spread × energy_capacity × efficiency × capture_rate
        energy_mwh = bess_power_mw * bess_duration_hours
        capture_rate = 0.7  # Typical capture rate for 1-cycle-per-day strategy

        daily_revenue_query = f"""
            SELECT
                substr(settlement_date, 1, 10) as day,
                MAX(rrp_aud_mwh) - MIN(rrp_aud_mwh) as daily_spread
            FROM {table_name}
            WHERE {region_clause}
            GROUP BY day
        """
        cursor.execute(daily_revenue_query, tuple(region_params))
        daily_rows = cursor.fetchall()

        if not daily_rows:
            raise DataUnavailableError(
                f"No daily data for {region} in {year}",
                metric_name="revenue_estimation",
            )

    # Calculate estimated revenues
    daily_revenues = [
        row[1] * energy_mwh * bess_efficiency * capture_rate
        for row in daily_rows
        if row[1] is not None
    ]

    if not daily_revenues:
        raise DataUnavailableError(
            f"Could not compute revenue for {region} in {year}",
            metric_name="revenue_estimation",
        )

    avg_daily_revenue = round(sum(daily_revenues) / len(daily_revenues), 0)
    annual_revenue = round(avg_daily_revenue * 365, 0)

    # Estimate cycle cost as percentage of revenue
    network_fee = get_default_fee(region)
    daily_network_cost = energy_mwh * network_fee / 1000  # Convert $/MWh to cost
    cycle_cost_ratio = round((daily_network_cost / avg_daily_revenue) * 100, 1) if avg_daily_revenue > 0 else 0.0

    sentiment = "positive" if annual_revenue > 3_000_000 else "neutral" if annual_revenue > 1_000_000 else "negative"

    summary_text = (
        f"{bess_power_mw:.0f}MW/{energy_mwh:.0f}MWh BESS 预计日均收入 "
        f"${avg_daily_revenue:,.0f}，年化 ${annual_revenue:,.0f}"
    )

    kpis = [
        KpiMetric(
            label="日均收入",
            value=avg_daily_revenue,
            unit="$",
            sentiment="positive" if avg_daily_revenue > 10000 else "neutral",
        ),
        KpiMetric(
            label="年化收入",
            value=annual_revenue,
            unit="$",
            sentiment=sentiment,
        ),
        KpiMetric(
            label="网络费占比",
            value=cycle_cost_ratio,
            unit="%",
            sentiment="neutral" if cycle_cost_ratio < 15 else "warning",
        ),
    ]

    return StageSummaryData(summary_text=summary_text, sentiment=sentiment, kpis=kpis)


def _compute_investment_decision(
    market: str,
    region: str,
    year: int,
    bess_power_mw: float,
    bess_duration_hours: float,
    bess_efficiency: float,
) -> StageSummaryData:
    """Stage 4: Compute investment indicators (NPV, IRR, payback).

    Uses simplified financial model based on estimated annual revenue.
    """
    # First get revenue estimate to feed into investment model
    revenue_stage = _compute_revenue_estimation(
        market, region, year, bess_power_mw, bess_duration_hours, bess_efficiency
    )

    # Extract annual revenue from stage 3 KPIs
    annual_revenue = 0.0
    for kpi in revenue_stage.kpis:
        if kpi.label == "年化收入":
            annual_revenue = float(kpi.value)
            break

    if annual_revenue <= 0:
        raise DataUnavailableError(
            "Cannot compute investment metrics without revenue estimate",
            metric_name="investment_indicators",
        )

    # Simplified investment calculation
    energy_mwh = bess_power_mw * bess_duration_hours
    capex_per_kwh = 350  # $/kWh typical 2024-2025 BESS cost
    total_capex = capex_per_kwh * energy_mwh * 1000  # Convert MWh to kWh
    project_life = 20
    discount_rate = 0.08
    degradation_rate = 0.025  # 2.5% annual capacity degradation

    # Build simplified cash flows
    cash_flows = [-total_capex]
    for yr in range(1, project_life + 1):
        degraded_revenue = annual_revenue * (1 - degradation_rate) ** yr
        opex = bess_power_mw * 12_000  # ~$12k/MW/year fixed O&M
        net_cf = degraded_revenue - opex
        cash_flows.append(net_cf)

    # Calculate NPV
    npv = sum(cf / (1 + discount_rate) ** i for i, cf in enumerate(cash_flows))

    # Calculate IRR using bisection method
    irr = _calculate_irr(cash_flows)

    # Calculate payback period
    cumulative = 0.0
    payback_years = None
    for i, cf in enumerate(cash_flows):
        cumulative += cf
        if cumulative >= 0 and i > 0:
            payback_years = float(i)
            break

    if payback_years is None:
        payback_years = float(project_life)

    # Determine sentiment
    if npv > 0 and irr is not None and irr > 0.10:
        sentiment = "positive"
    elif npv > 0:
        sentiment = "neutral"
    else:
        sentiment = "negative"

    npv_display = round(npv, 0)
    irr_display = round(irr * 100, 1) if irr is not None else 0.0

    summary_text = (
        f"NPV ${npv_display:,.0f} ({'正' if npv > 0 else '负'}), "
        f"IRR {irr_display}%, 回收期 {payback_years:.1f}年"
    )

    kpis = [
        KpiMetric(
            label="NPV",
            value=npv_display,
            unit="$",
            sentiment="positive" if npv > 0 else "negative",
        ),
        KpiMetric(
            label="IRR",
            value=irr_display,
            unit="%",
            sentiment="positive" if irr_display > 10 else "neutral" if irr_display > 5 else "negative",
        ),
        KpiMetric(
            label="回收期",
            value=payback_years,
            unit="年",
            sentiment="positive" if payback_years <= 7 else "warning" if payback_years <= 12 else "negative",
        ),
    ]

    return StageSummaryData(summary_text=summary_text, sentiment=sentiment, kpis=kpis)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


class DataUnavailableError(Exception):
    """Raised when data required for a stage computation is unavailable."""

    def __init__(self, message: str, metric_name: str = "unknown"):
        super().__init__(message)
        self.metric_name = metric_name


def _calculate_irr(cash_flows: list[float], tolerance: float = 1e-6, max_iter: int = 100) -> float | None:
    """Calculate IRR using bisection method."""
    if not cash_flows or len(cash_flows) < 2:
        return None

    # Check if there's a sign change (necessary for IRR to exist)
    has_negative = any(cf < 0 for cf in cash_flows)
    has_positive = any(cf > 0 for cf in cash_flows)
    if not (has_negative and has_positive):
        return None

    low, high = -0.99, 5.0

    for _ in range(max_iter):
        mid = (low + high) / 2.0
        npv = sum(cf / (1 + mid) ** i for i, cf in enumerate(cash_flows))

        if abs(npv) < tolerance:
            return mid
        elif npv > 0:
            low = mid
        else:
            high = mid

    return (low + high) / 2.0


def _derive_overall_rating(
    stages: dict[str, StageSummaryData | None],
) -> Literal["strong_opportunity", "moderate_opportunity", "weak_opportunity", "unfavorable"]:
    """Derive overall rating from available stage sentiments."""
    sentiments = [
        stage.sentiment
        for stage in stages.values()
        if stage is not None
    ]

    if not sentiments:
        return "unfavorable"

    positive_count = sentiments.count("positive")
    negative_count = sentiments.count("negative")
    total = len(sentiments)

    if positive_count >= 3:
        return "strong_opportunity"
    elif positive_count >= 2 and negative_count == 0:
        return "moderate_opportunity"
    elif negative_count >= 2:
        return "unfavorable"
    else:
        return "weak_opportunity"


def _build_cache_key(
    market: str,
    region: str,
    year: int,
    bess_power_mw: float,
    bess_duration_hours: float,
    bess_efficiency: float,
    stage_id: str | None = None,
) -> str:
    """Build a stable cache key from request parameters using SHA-256.

    Key format: market-summary:{market}:{region}:{year}:{bess_params_hash}
    or stage-summary:{market}:{region}:{year}:{stage_id}:{bess_params_hash}
    """
    # Create a stable hash of BESS parameters
    params_str = f"{bess_power_mw:.2f}:{bess_duration_hours:.2f}:{bess_efficiency:.4f}"
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]

    if stage_id:
        return f"stage-summary:{market}:{region}:{year}:{stage_id}:{params_hash}"
    return f"market-summary:{market}:{region}:{year}:{params_hash}"


# ---------------------------------------------------------------------------
# Stage computation registry
# ---------------------------------------------------------------------------

STAGE_COMPUTERS = {
    "market_opportunity": lambda market, region, year, params: _compute_market_opportunity(
        market, region, year, params["duration_hours"]
    ),
    "opportunity_identification": lambda market, region, year, params: _compute_opportunity_identification(
        market, region, year, params["power_mw"], params["duration_hours"]
    ),
    "revenue_estimation": lambda market, region, year, params: _compute_revenue_estimation(
        market, region, year, params["power_mw"], params["duration_hours"], params["efficiency"]
    ),
    "investment_decision": lambda market, region, year, params: _compute_investment_decision(
        market, region, year, params["power_mw"], params["duration_hours"], params["efficiency"]
    ),
}


# ---------------------------------------------------------------------------
# Route: /api/market-summary/{market}/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/api/market-summary/{market}/{region}",
    summary="Get aggregated market summary for executive view",
    description=(
        "Returns aggregated metrics across all four decision funnel stages "
        "in a single response. Supports partial results on data unavailability."
    ),
    response_model=MarketSummaryResponse,
)
def get_market_summary(
    market: str,
    region: str,
    year: int = Query(default=None, description="Analysis year (defaults to current year)"),
    bess_power_mw: float = Query(default=100.0, description="Battery power capacity in MW"),
    bess_duration_hours: float = Query(default=4.0, description="Battery duration in hours"),
    bess_efficiency: float = Query(default=0.87, description="Round-trip efficiency (0-1)"),
) -> MarketSummaryResponse:
    """Aggregated market summary endpoint for the Executive Summary view."""
    start_time = time.time()

    # Default year to current year
    if year is None:
        year = datetime.now(timezone.utc).year

    # Normalize market
    market = market.upper()

    # --- Cache lookup ---
    cache = get_cache()
    cache_key = _build_cache_key(market, region, year, bess_power_mw, bess_duration_hours, bess_efficiency)
    cached = cache.get_json(CACHE_SCOPE_MARKET_SUMMARY, cache_key)
    if cached is not None:
        return MarketSummaryResponse(**cached)

    # Build params dict for stage computers
    params = {
        "power_mw": bess_power_mw,
        "duration_hours": bess_duration_hours,
        "efficiency": bess_efficiency,
    }

    # Compute each stage independently with fault tolerance
    warnings: list[Warning] = []
    stages: dict[str, StageSummaryData | None] = {}

    for stage_id, compute_fn in STAGE_COMPUTERS.items():
        try:
            stages[stage_id] = compute_fn(market, region, year, params)
        except DataUnavailableError as e:
            stages[stage_id] = None
            warnings.append(
                Warning(
                    stage=stage_id,
                    metric=e.metric_name,
                    reason=str(e),
                    severity="degraded",
                )
            )
        except Exception as e:
            logger.error(f"Stage {stage_id} computation failed: {e}", exc_info=True)
            stages[stage_id] = None
            warnings.append(
                Warning(
                    stage=stage_id,
                    metric=None,
                    reason="computation_failed",
                    severity="error",
                )
            )

    # Derive overall rating
    overall_rating = _derive_overall_rating(stages)

    # Build metadata
    elapsed_ms = int((time.time() - start_time) * 1000)
    tz = REGION_TIMEZONES.get(region, "Australia/Sydney")
    metadata = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=tz,
        currency="AUD",
        unit="mixed",
        interval_minutes=get_settlement_interval(region),
        data_grade="analytical",
        data_quality_score=None,
        coverage=None,
        freshness={"last_updated_at": datetime.now(timezone.utc).isoformat()},
        source_name="aggregation_engine",
        source_version=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        methodology_version="market_summary_v1",
    )
    metadata["computation_time_ms"] = elapsed_ms

    response = MarketSummaryResponse(
        market=market,
        region=region,
        year=year,
        bess_params=BessParams(
            power_mw=bess_power_mw,
            duration_hours=bess_duration_hours,
            round_trip_efficiency=bess_efficiency,
        ),
        stages=stages,
        overall_rating=overall_rating,
        metadata=metadata,
        warnings=warnings,
    )

    # --- Cache store: only cache full results (no warnings) ---
    if not warnings:
        cache.set_json(
            CACHE_SCOPE_MARKET_SUMMARY,
            cache_key,
            response.model_dump(),
            CACHE_TTL_SECONDS,
        )

    return response


# ---------------------------------------------------------------------------
# Route: /api/stage-summary/{market}/{region}/{stage_id}
# ---------------------------------------------------------------------------


class StageSummaryResponse(BaseModel):
    """Response model for the stage-summary endpoint."""

    stage_id: str
    market: str
    region: str
    summary_text: str
    sentiment: Literal["positive", "negative", "neutral"]
    kpis: list[KpiMetric]
    metadata: dict[str, Any]
    warnings: list[Warning]


@router.get(
    "/api/stage-summary/{market}/{region}/{stage_id}",
    summary="Get summary data for a single decision funnel stage",
    description=(
        "Returns the stage conclusion text and 2-4 key metrics for a specific "
        "decision funnel stage. Faster than market-summary as it queries only "
        "the relevant stage's data sources."
    ),
    response_model=StageSummaryResponse,
)
def get_stage_summary(
    market: str,
    region: str,
    stage_id: str,
    year: int = Query(default=None, description="Analysis year (defaults to current year)"),
    bess_power_mw: float = Query(default=100.0, description="Battery power capacity in MW"),
    bess_duration_hours: float = Query(default=4.0, description="Battery duration in hours"),
    bess_efficiency: float = Query(default=0.87, description="Round-trip efficiency (0-1)"),
) -> StageSummaryResponse:
    """Stage-level summary endpoint for individual funnel stage conclusions."""
    start_time = time.time()

    # Validate stage_id
    if stage_id not in VALID_STAGE_IDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid stage_id '{stage_id}'. "
                f"Allowed values: {sorted(VALID_STAGE_IDS)}"
            ),
        )

    # Default year to current year
    if year is None:
        year = datetime.now(timezone.utc).year

    # Normalize market
    market = market.upper()

    # --- Cache lookup ---
    cache = get_cache()
    cache_key = _build_cache_key(
        market, region, year, bess_power_mw, bess_duration_hours, bess_efficiency,
        stage_id=stage_id,
    )
    cached = cache.get_json(CACHE_SCOPE_STAGE_SUMMARY, cache_key)
    if cached is not None:
        return StageSummaryResponse(**cached)

    # Map hyphenated stage_id to underscore key in STAGE_COMPUTERS
    registry_key = stage_id.replace("-", "_")

    compute_fn = STAGE_COMPUTERS.get(registry_key)
    if compute_fn is None:
        raise HTTPException(
            status_code=500,
            detail=f"Stage '{stage_id}' has no registered computation function.",
        )

    # Build params dict for stage computers
    params = {
        "power_mw": bess_power_mw,
        "duration_hours": bess_duration_hours,
        "efficiency": bess_efficiency,
    }

    # Compute the single stage
    warnings: list[Warning] = []
    try:
        stage_data = compute_fn(market, region, year, params)
    except DataUnavailableError as e:
        stage_data = None
        warnings.append(
            Warning(
                stage=stage_id,
                metric=e.metric_name,
                reason=str(e),
                severity="degraded",
            )
        )
    except Exception as e:
        logger.error(f"Stage {stage_id} computation failed: {e}", exc_info=True)
        stage_data = None
        warnings.append(
            Warning(
                stage=stage_id,
                metric=None,
                reason="computation_failed",
                severity="error",
            )
        )

    # Build metadata
    elapsed_ms = int((time.time() - start_time) * 1000)
    tz = REGION_TIMEZONES.get(region, "Australia/Sydney")
    metadata = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=tz,
        currency="AUD",
        unit="mixed",
        interval_minutes=get_settlement_interval(region),
        data_grade="analytical",
        data_quality_score=None,
        coverage=None,
        freshness={"last_updated_at": datetime.now(timezone.utc).isoformat()},
        source_name="aggregation_engine",
        source_version=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        methodology_version="stage_summary_v1",
    )
    metadata["computation_time_ms"] = elapsed_ms

    # If computation failed, return empty summary with warnings
    if stage_data is None:
        return StageSummaryResponse(
            stage_id=stage_id,
            market=market,
            region=region,
            summary_text="数据暂不可用",
            sentiment="neutral",
            kpis=[],
            metadata=metadata,
            warnings=warnings,
        )

    response = StageSummaryResponse(
        stage_id=stage_id,
        market=market,
        region=region,
        summary_text=stage_data.summary_text,
        sentiment=stage_data.sentiment,
        kpis=stage_data.kpis,
        metadata=metadata,
        warnings=warnings,
    )

    # --- Cache store: only cache full results (no warnings) ---
    if not warnings:
        cache.set_json(
            CACHE_SCOPE_STAGE_SUMMARY,
            cache_key,
            response.model_dump(),
            CACHE_TTL_SECONDS,
        )

    return response
