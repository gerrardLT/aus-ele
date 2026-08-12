"""Revenue analysis API routes.

Provides revenue analysis endpoints that integrate with the
RevenueAnalysisEngine. Revenue calculations use price data combined
with battery physical parameters to produce results in $ units.

Uses deps.py for dependency injection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from deps import get_db, get_cache
from engines.price_analysis_engine import AnalysisMetadata
from engines.revenue_analysis_engine import RevenueAnalysisEngine
from engines.exceptions import DimensionMismatchError
from network_fees import get_default_fee, get_settlement_interval
from sql_safe import trading_price_table
from result_metadata import build_result_metadata

logger = logging.getLogger(__name__)

router = APIRouter(tags=["revenue-analysis"])

# ---------------------------------------------------------------------------
# Cache scope constants
# ---------------------------------------------------------------------------

REVENUE_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_revenue_analysis_v1"
DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 6 * 60 * 60

# ---------------------------------------------------------------------------
# Shared engine instance
# ---------------------------------------------------------------------------

_revenue_engine = RevenueAnalysisEngine()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES = {
    404: {"description": "Data not found"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


def _region_timezone(region: str) -> str:
    region_timezones = {
        "NSW1": "Australia/Sydney",
        "QLD1": "Australia/Brisbane",
        "VIC1": "Australia/Melbourne",
        "SA1": "Australia/Adelaide",
        "TAS1": "Australia/Hobart",
        "WEM": "Australia/Perth",
    }
    return region_timezones.get(region, "Australia/Sydney")


def _market_data_version() -> str:
    db = get_db()
    return db.get_last_update_time() or "no_last_update"


def _stable_cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fetch_response_cache(scope: str, payload: dict):
    cache = get_cache()
    cache_key = _stable_cache_key(payload)
    return cache.get_json(scope, cache_key)


def _store_response_cache(scope: str, payload: dict, response_payload: dict, ttl_seconds: int):
    cache = get_cache()
    cache_key = _stable_cache_key(payload)
    cache.set_json(scope, cache_key, response_payload, ttl_seconds)
    return response_payload


def _attach_revenue_metadata(payload: dict, *, region: str, computation_time_ms: int | None = None) -> dict:
    """Attach standard metadata to revenue analysis response."""
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="$",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="revenue_analysis_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    if computation_time_ms is not None:
        payload["metadata"]["computation_time_ms"] = computation_time_ms
    return payload


def _attach_regime_layer(payload: dict, *, market: str, region: str) -> dict:
    """Attach regime layer to response payload."""
    try:
        import server as _server
        return _server._attach_regime_layer(payload, market=market, region=region)
    except Exception:
        payload.setdefault("regime_layer", {"availability_status": "not_attached"})
        payload.setdefault("regime_compact", {"availability_status": "not_attached"})
        return payload


# ---------------------------------------------------------------------------
# Route: /api/revenue-analysis
# ---------------------------------------------------------------------------


@router.get(
    "/api/revenue-analysis",
    summary="Get revenue analysis for BESS",
    description=(
        "Calculates revenue from historical price data combined with battery "
        "physical parameters. Returns results in $ with full metadata. "
        "Uses the RevenueAnalysisEngine for dimension-correct calculations."
    ),
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_revenue_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1, QLD1)"),
    power_mw: float = Query(..., description="Battery power capacity in MW"),
    energy_mwh: float = Query(..., description="Battery energy capacity in MWh"),
    efficiency: float = Query(0.85, description="Round-trip efficiency (0 to 1)"),
    degradation_rate: Optional[float] = Query(None, description="Annual degradation rate (0 to 0.15)"),
    network_fee: Optional[float] = Query(None, description="Network fee override ($/MWh)"),
    month: Optional[str] = Query(None, description="Month filter (01-12)"),
    quarter: Optional[str] = Query(None, description="Quarter filter (Q1-Q4)"),
    day_type: Optional[str] = Query(None, description="Day type filter (WEEKDAY, WEEKEND)"),
):
    """Calculate revenue from price data and battery parameters."""
    db = get_db()
    start_time = time.time()

    # Parameter validation
    if power_mw <= 0:
        raise HTTPException(status_code=422, detail="power_mw must be positive")
    if energy_mwh <= 0:
        raise HTTPException(status_code=422, detail="energy_mwh must be positive")
    if not (0.0 < efficiency <= 1.0):
        raise HTTPException(status_code=422, detail="efficiency must be between 0 and 1")
    if degradation_rate is not None and not (0.0 <= degradation_rate <= 0.15):
        raise HTTPException(
            status_code=422,
            detail="degradation_rate must be between 0 and 0.15",
        )

    fee = network_fee if network_fee is not None else get_default_fee(region)
    table_name = trading_price_table(year)
    interval_minutes = get_settlement_interval(region)

    try:
        # Check cache
        cache_payload = {
            "year": year,
            "region": region,
            "power_mw": power_mw,
            "energy_mwh": energy_mwh,
            "efficiency": efficiency,
            "degradation_rate": degradation_rate,
            "network_fee": fee,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(REVENUE_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            cached = _attach_revenue_metadata(cached, region=region)
            return _attach_regime_layer(cached, market="WEM" if region == "WEM" else "NEM", region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", (table_name,))
            if not cursor.fetchone():
                response = {
                    "region": region,
                    "year": year,
                    "total_revenue": 0.0,
                    "gross_revenue": 0.0,
                    "net_revenue": 0.0,
                    "costs": {"network_fees": 0.0, "degradation": 0.0},
                    "summary": {
                        "total_intervals": 0,
                        "power_mw": power_mw,
                        "energy_mwh": energy_mwh,
                    },
                }
                elapsed_ms = int((time.time() - start_time) * 1000)
                response = _attach_revenue_metadata(response, region=region, computation_time_ms=elapsed_ms)
                return response

            # Build query filters
            where = "region_id = ?"
            params: list = [region]

            if month and len(month) == 2:
                where += " AND settlement_date LIKE ?"
                params.append(f"{year}-{month}-%")
            elif quarter in ["Q1", "Q2", "Q3", "Q4"]:
                q_map = {
                    "Q1": ("01", "02", "03"),
                    "Q2": ("04", "05", "06"),
                    "Q3": ("07", "08", "09"),
                    "Q4": ("10", "11", "12"),
                }
                q_values = ", ".join(f"'{v}'" for v in q_map[quarter])
                where += f" AND substr(settlement_date, 6, 2) IN ({q_values})"

            if day_type == "WEEKDAY":
                where += " AND EXTRACT(DOW FROM CAST(substr(settlement_date, 1, 19) AS TIMESTAMP))::INTEGER IN (1, 2, 3, 4, 5)"
            elif day_type == "WEEKEND":
                where += " AND EXTRACT(DOW FROM CAST(substr(settlement_date, 1, 19) AS TIMESTAMP))::INTEGER IN (0, 6)"

            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
                f"WHERE {where} ORDER BY settlement_date ASC",
                tuple(params),
            )
            rows = cursor.fetchall()

            if not rows:
                response = {
                    "region": region,
                    "year": year,
                    "total_revenue": 0.0,
                    "gross_revenue": 0.0,
                    "net_revenue": 0.0,
                    "costs": {"network_fees": 0.0, "degradation": 0.0},
                    "summary": {
                        "total_intervals": 0,
                        "power_mw": power_mw,
                        "energy_mwh": energy_mwh,
                    },
                }
                elapsed_ms = int((time.time() - start_time) * 1000)
                response = _attach_revenue_metadata(response, region=region, computation_time_ms=elapsed_ms)
                return response

            # Convert DB rows to price records for the engine
            interval_hours = interval_minutes / 60.0
            prices = [
                {
                    "timestamp": row[0],
                    "price": row[1],
                    "interval_hours": interval_hours,
                }
                for row in rows
            ]

            # Run revenue calculation through the engine
            result = _revenue_engine.calculate(
                prices,
                power_mw=power_mw,
                energy_mwh=energy_mwh,
                round_trip_efficiency=efficiency,
                degradation_rate=degradation_rate,
                network_fee_per_mwh=fee,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            response = {
                "region": region,
                "year": year,
                "total_revenue": round(result.net_revenue, 2),
                "gross_revenue": round(result.gross_revenue, 2),
                "net_revenue": round(result.net_revenue, 2),
                "costs": {
                    "network_fees": round(result.costs["network_fees"], 2),
                    "degradation": round(result.costs["degradation"], 2),
                },
                "summary": {
                    "total_intervals": len(rows),
                    "total_discharge_mwh": round(result.summary["total_discharge_mwh"], 4),
                    "power_mw": power_mw,
                    "energy_mwh": energy_mwh,
                    "effective_energy_mwh": round(result.summary["effective_energy_mwh"], 4),
                    "round_trip_efficiency": efficiency,
                    "degradation_rate": degradation_rate,
                    "network_fee_per_mwh": fee,
                },
            }
            response = _attach_revenue_metadata(response, region=region, computation_time_ms=elapsed_ms)
            response = _attach_regime_layer(
                response, market="WEM" if region == "WEM" else "NEM", region=region
            )
            # Phase 2（2026-08-12）：FCAS 收益压缩风险标签（best-effort，失败降级）
            try:
                from services.fcas_compression import get_fcas_compression_label

                response["fcas_compression"] = get_fcas_compression_label()
            except Exception:  # noqa: BLE001
                response["fcas_compression"] = {
                    "available": False,
                    "risk_label": "fcas_revenue_compression",
                }
            return _store_response_cache(
                REVENUE_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload,
                response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except DimensionMismatchError as e:
        raise HTTPException(status_code=422, detail=str(e.message))
    except Exception as e:
        logger.error(f"Error in revenue-analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Route: /api/revenue-analysis/validate
# ---------------------------------------------------------------------------


@router.post(
    "/api/revenue-analysis/validate",
    summary="Validate revenue analysis input dimensions",
    description=(
        "Validates that input data has correct dimensions for revenue calculation. "
        "Returns 422 if the input contains price statistics ($/MWh) instead of raw price series."
    ),
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def validate_revenue_input(input_data: dict):
    """Validate input dimensions before revenue calculation."""
    try:
        _revenue_engine.validate_input_dimensions(input_data)
        return {"valid": True, "message": "Input dimensions are correct for revenue calculation."}
    except DimensionMismatchError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "DIMENSION_MISMATCH",
                "message": e.message,
                "details": {
                    "expected_unit": e.expected_unit,
                    "received_unit": e.received_unit,
                },
                "suggestion": "请使用 /api/price-data 获取原始价格序列作为输入",
            },
        )
