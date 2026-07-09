"""FCAS analysis API routes.

Migrated from server.py — provides the Reserve Opportunity analysis endpoint
for FCAS price data. Supports both NEM and WEM (ESS slim data)
markets.

Uses deps.py for dependency injection.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from deps import get_db, get_cache
from network_fees import get_settlement_interval
from result_metadata import build_result_metadata
from sql_safe import trading_price_table
from pipelines.fcas_4s_ingest import (
    FCAS_4S_SERVICES,
    FCAS_4S_TABLE,
    resolve_fcas_resolution,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fcas-analysis"])

# ---------------------------------------------------------------------------
# Cache scope constants (mirror server.py values)
# ---------------------------------------------------------------------------

FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_fcas_analysis_v1"
DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 6 * 60 * 60
DEFAULT_FCAS_OPPORTUNITY_DURATION_HOURS = 4.0

# ---------------------------------------------------------------------------
# FCAS service definitions
# ---------------------------------------------------------------------------

FCAS_SERVICES = {
    "raise1sec": "Raise 1 Sec",
    "raise6sec": "Raise 6 Sec",
    "raise60sec": "Raise 60 Sec",
    "raise5min": "Raise 5 Min",
    "raisereg": "Raise Reg",
    "lower1sec": "Lower 1 Sec",
    "lower6sec": "Lower 6 Sec",
    "lower60sec": "Lower 60 Sec",
    "lower5min": "Lower 5 Min",
    "lowerreg": "Lower Reg",
}

FCAS_COLUMNS = list(f"{k}_rrp" for k in FCAS_SERVICES.keys())
FCAS_GROUPS = {
    key: ("raise" if key.startswith("raise") else "lower")
    for key in FCAS_SERVICES.keys()
}

# ---------------------------------------------------------------------------
# OpenAPI response schemas
# ---------------------------------------------------------------------------

OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES = {
    404: {"description": "Data not found"},
    500: {"description": "Internal server error"},
}


# ---------------------------------------------------------------------------
# Helper functions (extracted from server.py)
# ---------------------------------------------------------------------------


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


def _cacheable_param(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    default = getattr(value, "default", None)
    if isinstance(default, (str, int, float, bool)) or default is None:
        return default
    return str(value)


def _fetch_response_cache(scope: str, payload: dict, normalize_fn=None):
    cache = get_cache()
    cache_key = _stable_cache_key(payload)
    cached = cache.get_json(scope, cache_key)
    if cached is None:
        return None
    return normalize_fn(cached) if normalize_fn else cached


def _store_response_cache(scope: str, payload: dict, response_payload: dict, ttl_seconds: int):
    cache = get_cache()
    cache_key = _stable_cache_key(payload)
    cache.set_json(scope, cache_key, response_payload, ttl_seconds)
    return response_payload


def _attach_fcas_analysis_metadata(
    payload: dict,
    *,
    region: str,
    interval_seconds: int | None = None,
    fallback_used: bool = False,
) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()

    # Determine interval_minutes from interval_seconds or default
    if interval_seconds is not None:
        interval_minutes = interval_seconds // 60 if interval_seconds >= 60 else None
    else:
        interval_minutes = 5 if market == "WEM" else get_settlement_interval(region)

    warnings = []
    if market == "WEM":
        warnings = ["preview_only", "core_only"]
    if fallback_used:
        warnings.append("resolution_fallback_5min")

    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MW/year",
        interval_minutes=interval_minutes,
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"row_count": len(payload.get("data", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="fcas_analysis_v1",
        warnings=warnings,
    )

    # Add interval_seconds to metadata for 4s resolution
    if interval_seconds is not None:
        payload["metadata"]["interval_seconds"] = interval_seconds
        payload["metadata"]["actual_resolution"] = (
            "4s" if interval_seconds == 4 else f"{interval_seconds}s"
        )

    return payload


def _attach_regime_layer(payload: dict, *, market: str, region: str) -> dict:
    """Attach regime layer to response payload.

    Delegates to the server-level regime layer cache. If unavailable,
    attaches a minimal unavailable marker.
    """
    try:
        import server as _server
        return _server._attach_regime_layer(payload, market=market, region=region)
    except Exception:
        payload.setdefault("regime_layer", {"availability_status": "not_attached"})
        payload.setdefault("regime_compact", {"availability_status": "not_attached"})
        return payload


def _build_temporal_filters(
    year: int,
    month: Optional[str],
    quarter: Optional[str],
    day_type: Optional[str],
    *,
    time_field: str = "settlement_date",
    region: Optional[str] = None,
    region_field: Optional[str] = "region_id",
    force_year_prefix: bool = False,
):
    if not isinstance(month, str):
        month = None
    if not isinstance(quarter, str):
        quarter = None
    if not isinstance(day_type, str):
        day_type = None

    clauses = []
    params = []

    if region_field and region is not None:
        clauses.append(f"{region_field} = ?")
        params.append(region)

    if month and len(month) == 2:
        clauses.append(f"{time_field} LIKE ?")
        params.append(f"{year}-{month}-%")
    elif quarter in ["Q1", "Q2", "Q3", "Q4"]:
        q_map = {
            "Q1": ("01", "02", "03"),
            "Q2": ("04", "05", "06"),
            "Q3": ("07", "08", "09"),
            "Q4": ("10", "11", "12"),
        }
        q_values = ", ".join(f"'{value}'" for value in q_map[quarter])
        clauses.append(f"substr({time_field}, 6, 2) IN ({q_values})")
        if force_year_prefix:
            clauses.append(f"{time_field} LIKE ?")
            params.append(f"{year}-%")
    elif force_year_prefix:
        clauses.append(f"{time_field} LIKE ?")
        params.append(f"{year}-%")

    if day_type == "WEEKDAY":
        clauses.append(
            f"EXTRACT(DOW FROM CAST(substr({time_field}, 1, 19) AS TIMESTAMP))::INTEGER IN (1, 2, 3, 4, 5)"
        )
    elif day_type == "WEEKEND":
        clauses.append(
            f"EXTRACT(DOW FROM CAST(substr({time_field}, 1, 19) AS TIMESTAMP))::INTEGER IN (0, 6)"
        )

    return " AND ".join(clauses) if clauses else "1=1", params


# ---------------------------------------------------------------------------
# Route: /api/fcas-analysis
# ---------------------------------------------------------------------------


@router.get(
    "/api/fcas-analysis",
    summary="Get Reserve Opportunity analysis",
    description=(
        "Returns Reserve Opportunity proxy outputs for FCAS upside, ESS reserve "
        "context, and unified metadata. WEM responses remain preview_only/core_only "
        "and should not be treated as investment-grade market truth."
    ),
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_fcas_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1)"),
    aggregation: str = Query("daily", description="Aggregation: daily, weekly, monthly"),
    capacity_mw: float = Query(100, description="Battery capacity in MW for revenue estimation"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    resolution: Optional[str] = Query("auto", description="Data resolution: auto (tries 4s first, falls back to 5min), 4s, or 5min"),
    access_scope: Optional[dict] = None,
):
    """
    FCAS revenue analysis endpoint.
    Returns per-service average prices, revenue estimates, hourly distribution,
    and time series data for charting.
    """
    db = get_db()

    if access_scope:
        try:
            import server as _server
            _server._assert_scope_allows_internal_query(
                access_scope,
                region=region,
                market="WEM" if region == "WEM" else "NEM",
            )
        except Exception:
            pass

    aggregation = _cacheable_param(aggregation)
    capacity_mw = _cacheable_param(capacity_mw)
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    resolution = _cacheable_param(resolution) or "auto"

    # Resolve actual data resolution (4s → 5min fallback)
    resolution_info = resolve_fcas_resolution(
        db, region=region, year=year, requested_resolution=resolution
    )
    actual_interval_seconds = resolution_info["resolution_seconds"]
    fallback_used = resolution_info["fallback_used"]

    cache_payload = {
        "year": year,
        "region": region,
        "aggregation": aggregation,
        "capacity_mw": capacity_mw,
        "month": month,
        "quarter": quarter,
        "day_type": day_type,
        "resolution": resolution,
        "data_version": _market_data_version(),
    }
    cached = _fetch_response_cache(FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload)
    if cached is not None:
        cached = _attach_fcas_analysis_metadata(
            cached,
            region=region,
            interval_seconds=actual_interval_seconds,
            fallback_used=fallback_used,
        )
        return _attach_regime_layer(cached, market="WEM" if region == "WEM" else "NEM", region=region)

    if region == "WEM":
        try:
            import server as _server
            response = _server._get_wem_ess_analysis(
                year, aggregation, capacity_mw, month, quarter, day_type
            )
            response = _attach_fcas_analysis_metadata(response, region=region)
            response = _attach_regime_layer(response, market="WEM", region=region)
            return _store_response_cache(
                FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.error(f"WEM ESS analysis error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    table_name = trading_price_table(year)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,)
            )
            if not cursor.fetchone():
                response = {
                    "region": region,
                    "year": year,
                    "has_fcas_data": False,
                    "message": f"No data available for year {year}",
                    "data": [],
                    "summary": {},
                    "hourly": [],
                    "service_breakdown": [],
                }
                response = _attach_fcas_analysis_metadata(
                    response,
                    region=region,
                    interval_seconds=actual_interval_seconds,
                    fallback_used=fallback_used,
                )
                response = _attach_regime_layer(response, market="NEM", region=region)
                return _store_response_cache(
                    FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # Check if FCAS columns exist in the table
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                (table_name,),
            )
            existing_cols = {row[0] for row in cursor.fetchall()}
            available_fcas = [c for c in FCAS_COLUMNS if c in existing_cols]

            if not available_fcas:
                response = {
                    "region": region,
                    "year": year,
                    "has_fcas_data": False,
                    "message": "No FCAS data available. Run scraper with --fcas flag.",
                    "data": [],
                    "summary": {},
                    "hourly": [],
                    "service_breakdown": [],
                }
                response = _attach_fcas_analysis_metadata(
                    response,
                    region=region,
                    interval_seconds=actual_interval_seconds,
                    fallback_used=fallback_used,
                )
                response = _attach_regime_layer(response, market="NEM", region=region)
                return _store_response_cache(
                    FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            where_clause, params = _build_temporal_filters(
                year,
                month,
                quarter,
                day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )
            nonnull_expr = " OR ".join(f"{col} IS NOT NULL" for col in available_fcas)

            # Check if there's actually non-null FCAS data
            check_query = (
                f"SELECT COUNT(*) FROM {table_name} "
                f"WHERE {where_clause} AND ({nonnull_expr})"
            )
            cursor.execute(check_query, tuple(params))
            fcas_count = cursor.fetchone()[0]

            if fcas_count == 0:
                response = {
                    "region": region,
                    "year": year,
                    "has_fcas_data": False,
                    "message": "FCAS columns exist but no data yet. Re-sync with --fcas flag.",
                    "data": [],
                    "summary": {},
                    "hourly": [],
                    "service_breakdown": [],
                }
                response = _attach_fcas_analysis_metadata(
                    response,
                    region=region,
                    interval_seconds=actual_interval_seconds,
                    fallback_used=fallback_used,
                )
                response = _attach_regime_layer(response, market="NEM", region=region)
                return _store_response_cache(
                    FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # 1. Overall service breakdown: average price per FCAS service
            avg_selects = ", ".join(
                f"AVG({col}) as avg_{col}" for col in available_fcas
            )
            max_selects = ", ".join(
                f"MAX({col}) as max_{col}" for col in available_fcas
            )
            cursor.execute(
                f"SELECT {avg_selects}, {max_selects}, COUNT(*) as total_intervals "
                f"FROM {table_name} WHERE {where_clause} AND ({nonnull_expr})",
                tuple(params),
            )
            agg_row = cursor.fetchone()

            n_fcas = len(available_fcas)
            total_intervals = agg_row[2 * n_fcas] if agg_row else 0

            service_breakdown = []
            for i, col in enumerate(available_fcas):
                svc_key = col.replace("_rrp", "")
                avg_price = agg_row[i] if agg_row and agg_row[i] is not None else 0
                max_price = (
                    agg_row[n_fcas + i]
                    if agg_row and agg_row[n_fcas + i] is not None
                    else 0
                )
                # Revenue estimate: price * capacity * (5min / 60min) per interval
                est_revenue = (
                    avg_price * capacity_mw * total_intervals * (5 / 60) / 1000
                )  # in $k
                service_breakdown.append({
                    "service": FCAS_SERVICES.get(svc_key, svc_key),
                    "key": svc_key,
                    "group": FCAS_GROUPS.get(svc_key),
                    "avg_price": round(avg_price, 2),
                    "max_price": round(max_price, 2),
                    "est_revenue_k": round(est_revenue, 1),
                })

            # 2. Hourly distribution of FCAS prices (average by hour)
            total_fcas_expr = " + ".join(
                f"COALESCE({col}, 0)" for col in available_fcas
            )
            hourly_query = f"""
                SELECT
                    CAST(substr(settlement_date, 12, 2) AS INTEGER) as hour_bucket,
                    AVG({total_fcas_expr}) as avg_total_fcas,
                    COUNT(*) as cnt
                FROM {table_name}
                WHERE {where_clause} AND ({nonnull_expr})
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
            """
            cursor.execute(hourly_query, tuple(params))
            hourly_rows = cursor.fetchall()
            hourly_dict = {r[0]: round(r[1], 2) for r in hourly_rows}
            hourly = [
                {"hour": f"{h:02d}", "avg_total_fcas": hourly_dict.get(h, 0)}
                for h in range(24)
            ]

            # 3. Time series aggregated by day/week/month
            if aggregation == "daily":
                date_expr = "substr(settlement_date, 1, 10)"
            elif aggregation == "weekly":
                date_expr = "TO_CHAR(CAST(settlement_date AS TIMESTAMP), 'IYYY-\"W\"IW')"
            else:  # monthly
                date_expr = "substr(settlement_date, 1, 7)"

            fcas_avg_selects = ", ".join(
                f"ROUND(AVG({col}), 2) as {col}" for col in available_fcas
            )
            ts_query = f"""
                SELECT {date_expr} as period, {fcas_avg_selects},
                       ROUND(AVG({total_fcas_expr}), 2) as total_fcas_avg,
                       COUNT(*) as intervals
                FROM {table_name}
                WHERE {where_clause} AND ({nonnull_expr})
                GROUP BY period
                ORDER BY period ASC
            """
            cursor.execute(ts_query, tuple(params))
            ts_rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]

            ts_data = []
            for row in ts_rows:
                entry = {}
                for j, col_name in enumerate(col_names):
                    entry[col_name] = row[j]
                ts_data.append(entry)

            # FCAS opportunity analysis
            from fcas_opportunity import summarize_nem_fcas_opportunity

            cursor.execute(
                f"""
                SELECT settlement_date, rrp_aud_mwh, {", ".join(available_fcas)}
                FROM {table_name}
                WHERE {where_clause} AND ({nonnull_expr})
                ORDER BY settlement_date ASC
                """,
                tuple(params),
            )
            opportunity_columns = [desc[0] for desc in cursor.description]
            opportunity_rows = cursor.fetchall()
            opportunity = summarize_nem_fcas_opportunity(
                opportunity_rows,
                capacity_mw=capacity_mw,
                duration_hours=DEFAULT_FCAS_OPPORTUNITY_DURATION_HOURS,
                columns=opportunity_columns,
            )
            opportunity_by_key = {
                item["key"]: item for item in opportunity["service_breakdown"]
            }
            enriched_breakdown = []
            for service in service_breakdown:
                opportunity_item = opportunity_by_key.get(service["key"], {})
                enriched_breakdown.append(
                    {
                        **service,
                        "avg_reserved_capacity_mw": opportunity_item.get(
                            "avg_reserved_capacity_mw", 0.0
                        ),
                        "opportunity_cost_k": opportunity_item.get(
                            "opportunity_cost_k", 0.0
                        ),
                        "net_incremental_revenue_k": opportunity_item.get(
                            "net_incremental_revenue_k", 0.0
                        ),
                        "soc_binding_interval_ratio": opportunity_item.get(
                            "soc_binding_interval_ratio", 0.0
                        ),
                        "power_binding_interval_ratio": opportunity_item.get(
                            "power_binding_interval_ratio", 0.0
                        ),
                        "incremental_revenue_positive": opportunity_item.get(
                            "incremental_revenue_positive", False
                        ),
                    }
                )

            # 4. Overall summary
            total_avg_fcas = sum(s["avg_price"] for s in enriched_breakdown)
            total_est_revenue_k = sum(s["est_revenue_k"] for s in enriched_breakdown)

            summary = {
                "total_avg_fcas_price": round(total_avg_fcas, 2),
                "total_est_revenue_k": round(total_est_revenue_k, 1),
                "total_intervals": total_intervals,
                "capacity_mw": capacity_mw,
                "data_points_with_fcas": fcas_count,
                "total_opportunity_cost_k": opportunity["summary"][
                    "total_opportunity_cost_k"
                ],
                "total_net_incremental_revenue_k": opportunity["summary"][
                    "total_net_incremental_revenue_k"
                ],
                "viable_service_count": opportunity["summary"]["viable_service_count"],
                "assumed_duration_hours": opportunity["summary"][
                    "assumed_duration_hours"
                ],
            }

            response = {
                "region": region,
                "year": year,
                "has_fcas_data": True,
                "aggregation": aggregation,
                "filters": {
                    "month": month,
                    "quarter": quarter,
                    "day_type": day_type,
                },
                "resolution": {
                    "requested": resolution,
                    "actual_seconds": actual_interval_seconds,
                    "fallback_used": fallback_used,
                },
                "summary": summary,
                "service_breakdown": enriched_breakdown,
                "hourly": hourly,
                "data": ts_data,
            }
            response = _attach_fcas_analysis_metadata(
                response,
                region=region,
                interval_seconds=actual_interval_seconds,
                fallback_used=fallback_used,
            )
            response = _attach_regime_layer(response, market="NEM", region=region)
            return _store_response_cache(
                FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FCAS analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
