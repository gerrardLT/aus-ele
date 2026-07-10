"""Price analysis API routes.

Migrated from server.py — provides price trend, peak/trough spread analysis,
and hourly price profile endpoints. Integrates with PriceAnalysisEngine and
uses deps.py for dependency injection.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import math
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from deps import get_db, get_cache
from engines.price_analysis_engine import PriceAnalysisEngine
from network_fees import get_default_fee, get_settlement_interval, get_window_sizes
from result_metadata import build_result_metadata
from sql_safe import trading_price_table

logger = logging.getLogger(__name__)

router = APIRouter(tags=["price-analysis"])

# ---------------------------------------------------------------------------
# Cache scope constants (mirror server.py values)
# ---------------------------------------------------------------------------

PRICE_TREND_RESPONSE_CACHE_SCOPE = "api_price_trend_v1"
PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_peak_analysis_v1"
HOURLY_PROFILE_RESPONSE_CACHE_SCOPE = "api_hourly_price_profile_v1"
DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 6 * 60 * 60

# ---------------------------------------------------------------------------
# Shared engine instance
# ---------------------------------------------------------------------------

_price_engine = PriceAnalysisEngine()


# ---------------------------------------------------------------------------
# Helper functions (extracted from server.py)
# ---------------------------------------------------------------------------

OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES = {
    404: {"description": "Data not found"},
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


def _attach_price_trend_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    coverage_mode = "core-only" if market == "WEM" else "full"
    regulatory_scope = market
    market_design_context = (
        "WEM co-optimised ESS preview view with independent market-design caveat and non-equivalent coverage."
        if market == "WEM"
        else "NEM energy market truth with regime, event, reserve, and frequency-aware context."
    )
    base_metadata = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="price_trend_v1",
        warnings=[] if market != "WEM" else ["preview_only", "core_only"],
    )
    payload["metadata"] = {
        **base_metadata,
        "coverage_mode": coverage_mode,
        "regulatory_scope": regulatory_scope,
        "market_design_context": market_design_context,
        "result_type": "market_state",
    }
    return payload


def _attach_peak_analysis_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"row_count": len(payload.get("data", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="peak_analysis_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    return payload


def _attach_hourly_price_profile_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"hour_count": len(payload.get("hourly", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="hourly_price_profile_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    return payload


def _attach_regime_layer(payload: dict, *, market: str, region: str) -> dict:
    """Attach regime layer to response payload.

    Delegates to the server-level regime layer cache. If unavailable,
    attaches a minimal unavailable marker.
    """
    # Import lazily to avoid circular imports during module loading
    try:
        import server as _server
        return _server._attach_regime_layer(payload, market=market, region=region)
    except Exception:
        # Graceful degradation: if server module not importable, skip regime layer
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


def _price_trend_sampling_stride(total_rows: int, limit: int | None) -> int | None:
    if limit is None or limit <= 0 or total_rows <= limit:
        return None
    if limit == 1:
        return total_rows
    return max(1, math.ceil((total_rows - 1) / float(limit - 1)))


def _uniform_downsample_price_rows(rows, limit: int):
    if not rows or len(rows) <= limit or limit is None or limit <= 0:
        return [{"time": row[0], "price": round(row[1], 2)} for row in rows]

    if limit == 1:
        last_row = rows[-1]
        return [{"time": last_row[0], "price": round(last_row[1], 2)}]

    step = (len(rows) - 1) / float(limit - 1)
    indices = []
    seen = set()
    for position in range(limit):
        index = int(round(position * step))
        index = max(0, min(index, len(rows) - 1))
        if index not in seen:
            seen.add(index)
            indices.append(index)

    if indices[-1] != len(rows) - 1:
        indices[-1] = len(rows) - 1

    return [{"time": rows[i][0], "price": round(rows[i][1], 2)} for i in indices]


def _downsample_price_rows(rows, limit: int):
    if not rows or len(rows) <= limit or limit is None or limit <= 0:
        return [{"time": row[0], "price": round(row[1], 2)} for row in rows]

    try:
        import numpy as np
        import lttbc

        x = np.arange(len(rows), dtype=np.float64)
        y = np.array([row[1] for row in rows], dtype=np.float64)
        dx, dy = lttbc.downsample(x, y, limit)

        data = []
        for idx_flt, val in zip(dx, dy):
            orig_idx = int(round(idx_flt))
            orig_idx = max(0, min(orig_idx, len(rows) - 1))
            data.append({"time": rows[orig_idx][0], "price": round(val, 2)})
        return data
    except Exception as exc:
        logger.warning("Falling back to uniform price downsampling because LTTB failed: %s", exc)
        return _uniform_downsample_price_rows(rows, limit)


def _fetch_sampled_price_trend_data(
    cursor,
    *,
    table_name: str,
    where_clause: str,
    params: tuple,
    total_rows: int,
    limit: int | None,
) -> list[dict]:
    stride = _price_trend_sampling_stride(total_rows, limit)
    if stride is None:
        cursor.execute(
            f"""
            SELECT settlement_date, rrp_aud_mwh
            FROM {table_name}
            WHERE {where_clause}
            ORDER BY settlement_date ASC
            """,
            params,
        )
        rows = cursor.fetchall()
        return _downsample_price_rows(rows, limit)

    cursor.execute(
        f"""
        WITH filtered AS (
            SELECT
                settlement_date,
                rrp_aud_mwh,
                ROW_NUMBER() OVER (ORDER BY settlement_date ASC) AS rn
            FROM {table_name}
            WHERE {where_clause}
        )
        SELECT settlement_date, rrp_aud_mwh
        FROM filtered
        WHERE rn = 1 OR rn = ? OR ((rn - 1) % ? = 0)
        ORDER BY settlement_date ASC
        """,
        (*params, total_rows, stride),
    )
    rows = cursor.fetchall()
    return [{"time": row[0], "price": round(row[1], 2)} for row in rows]


# ---------------------------------------------------------------------------
# Peak analysis helpers
# ---------------------------------------------------------------------------


def _compute_peak_day_result(day: str, prices: list[float], *, windows: dict, fee: float) -> dict:
    n = len(prices)
    result = {"date": day}

    for label, w_size in windows.items():
        if n < w_size:
            result[f"peak_{label}"] = None
            result[f"trough_{label}"] = None
            continue

        window_sum = sum(prices[:w_size])
        best_max = window_sum
        best_min = window_sum

        for i in range(1, n - w_size + 1):
            window_sum += prices[i + w_size - 1] - prices[i - 1]
            if window_sum > best_max:
                best_max = window_sum
            if window_sum < best_min:
                best_min = window_sum

        result[f"peak_{label}"] = round(best_max / w_size, 2)
        result[f"trough_{label}"] = round(best_min / w_size, 2)

    for label in ["2h", "4h", "6h"]:
        peak = result.get(f"peak_{label}")
        trough = result.get(f"trough_{label}")
        if peak is not None and trough is not None:
            spread = round(peak - trough, 2)
            result[f"spread_{label}"] = spread
            result[f"net_spread_{label}"] = round(spread - 2 * fee, 2)
        else:
            result[f"spread_{label}"] = None
            result[f"net_spread_{label}"] = None

    return result


def _iter_peak_daily_results(rows, *, windows: dict, fee: float):
    current_day = None
    current_prices = []

    for date_str, price in rows:
        day_key = date_str[:10]
        if current_day is None:
            current_day = day_key
        if day_key != current_day:
            yield _compute_peak_day_result(current_day, current_prices, windows=windows, fee=fee)
            current_day = day_key
            current_prices = []
        current_prices.append(price)

    if current_day is not None:
        yield _compute_peak_day_result(current_day, current_prices, windows=windows, fee=fee)


def _aggregate_peak_data(daily_results: list, aggregation: str) -> list:
    """Aggregate daily peak/trough results by week, month, or year."""
    import datetime as dt_module

    groups = defaultdict(list)

    for row in daily_results:
        day = row["date"]
        if aggregation == "weekly":
            d = dt_module.datetime.strptime(day, "%Y-%m-%d")
            iso_year, iso_week, _ = d.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        elif aggregation == "monthly":
            key = day[:7]
        elif aggregation == "yearly":
            key = day[:4]
        else:
            key = day
        groups[key].append(row)

    numeric_fields = [
        "peak_1h", "peak_2h", "peak_4h", "peak_6h",
        "trough_1h", "trough_2h", "trough_4h", "trough_6h",
        "spread_2h", "spread_4h", "spread_6h",
        "net_spread_2h", "net_spread_4h", "net_spread_6h",
    ]

    aggregated = []
    for period, items in sorted(groups.items()):
        entry = {"period": period, "days_count": len(items)}
        for field in numeric_fields:
            values = [item[field] for item in items if item.get(field) is not None]
            entry[field] = round(sum(values) / len(values), 2) if values else None
        aggregated.append(entry)

    return aggregated


def _compute_summary(daily_results: list) -> dict:
    """Compute overall summary stats across all daily results."""
    summary = {}
    for label in ["2h", "4h", "6h"]:
        spreads = [r[f"spread_{label}"] for r in daily_results if r.get(f"spread_{label}") is not None]
        nets = [r[f"net_spread_{label}"] for r in daily_results if r.get(f"net_spread_{label}") is not None]
        summary[f"avg_spread_{label}"] = round(sum(spreads) / len(spreads), 2) if spreads else None
        summary[f"avg_net_spread_{label}"] = round(sum(nets) / len(nets), 2) if nets else None
        summary[f"max_spread_{label}"] = round(max(spreads), 2) if spreads else None
        summary[f"min_spread_{label}"] = round(min(spreads), 2) if spreads else None
    summary["total_days"] = len(daily_results)
    return summary


# ---------------------------------------------------------------------------
# Route: /api/price-trend
# ---------------------------------------------------------------------------


@router.get(
    "/api/price-trend",
    summary="Get price trend analysis",
    description="Returns historical price series, aggregate statistics, and unified metadata.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_price_trend(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1, QLD1)"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    limit: Optional[int] = Query(5000, description="Max points to return."),
):
    """Returns time series data with dynamic sampling to handle large arrays."""
    db = get_db()
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    limit = _cacheable_param(limit)
    table_name = trading_price_table(year)

    try:
        cache_payload = {
            "year": year,
            "region": region,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "limit": limit,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(PRICE_TREND_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            cached = _attach_price_trend_metadata(cached, region=region)
            return _attach_regime_layer(cached, market="WEM" if region == "WEM" else "NEM", region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", (table_name,))
            table_exists = cursor.fetchone()

            if not table_exists:
                total_rows = 0
            else:
                where_clause, params = _build_temporal_filters(
                    year, month, quarter, day_type,
                    time_field="settlement_date",
                    region=region,
                    region_field="region_id",
                )
                cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", tuple(params))
                total_rows = cursor.fetchone()[0]

            if total_rows == 0:
                response = {
                    "region": region, "year": year, "month": month,
                    "total_points": 0, "returned_points": 0,
                    "stats": {"min": 0, "max": 0, "avg": 0},
                    "advanced_stats": {
                        "neg_ratio": 0, "neg_avg": 0, "neg_min": 0,
                        "pos_avg": 0, "pos_max": 0,
                        "days_below_100": 0, "days_above_300": 0,
                    },
                    "hourly_distribution": [], "data": [],
                }
                response = _attach_price_trend_metadata(response, region=region)
                response = _attach_regime_layer(
                    response, market="WEM" if region == "WEM" else "NEM", region=region
                )
                return _store_response_cache(
                    PRICE_TREND_RESPONSE_CACHE_SCOPE, cache_payload,
                    response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            data = _fetch_sampled_price_trend_data(
                cursor,
                table_name=table_name,
                where_clause=where_clause,
                params=tuple(params),
                total_rows=total_rows,
                limit=limit,
            )

            # Single optimized SQL query for all statistics
            stats_query = f"""
                SELECT
                    MIN(rrp_aud_mwh) as overall_min,
                    MAX(rrp_aud_mwh) as overall_max,
                    AVG(rrp_aud_mwh) as overall_avg,
                    SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as neg_count,
                    AVG(CASE WHEN rrp_aud_mwh < 0 THEN rrp_aud_mwh ELSE NULL END) as neg_avg,
                    MIN(CASE WHEN rrp_aud_mwh < 0 THEN rrp_aud_mwh ELSE NULL END) as neg_min,
                    AVG(CASE WHEN rrp_aud_mwh > 0 THEN rrp_aud_mwh ELSE NULL END) as pos_avg,
                    MAX(CASE WHEN rrp_aud_mwh > 0 THEN rrp_aud_mwh ELSE NULL END) as pos_max,
                    COUNT(DISTINCT CASE WHEN rrp_aud_mwh < -100 THEN substr(settlement_date, 1, 10) ELSE NULL END) as days_below_100,
                    COUNT(DISTINCT CASE WHEN rrp_aud_mwh > 300 THEN substr(settlement_date, 1, 10) ELSE NULL END) as days_above_300
                FROM {table_name}
                WHERE {where_clause}
            """
            cursor.execute(stats_query, tuple(params))
            aggs = cursor.fetchone()

            o_min, o_max, o_avg = aggs[0], aggs[1], aggs[2]
            neg_count = aggs[3] if aggs[3] else 0
            neg_avg = aggs[4]
            neg_min = aggs[5]
            pos_avg = aggs[6]
            pos_max = aggs[7]
            days_below_100 = aggs[8] if aggs[8] else 0
            days_above_300 = aggs[9] if aggs[9] else 0

            neg_ratio = round((neg_count / total_rows) * 100, 2) if total_rows > 0 else 0

            # Hourly distribution of negative prices
            hourly_query = f"""
                SELECT
                    LPAD(EXTRACT(HOUR FROM settlement_date::timestamp - INTERVAL '1 second')::text, 2, '0') as hour_bucket,
                    COUNT(*)
                FROM {table_name}
                WHERE {where_clause} AND rrp_aud_mwh < 0
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
            """
            cursor.execute(hourly_query, tuple(params))
            hourly_rows = cursor.fetchall()

            hourly_dict = {r[0]: r[1] for r in hourly_rows}
            hourly_distribution = []
            for h in range(24):
                hr_str = f"{h:02d}"
                hourly_distribution.append({"hour": hr_str, "count": hourly_dict.get(hr_str, 0)})

            response = {
                "region": region,
                "year": year,
                "month": month,
                "total_points": total_rows,
                "returned_points": len(data),
                "stats": {
                    "min": round(o_min, 2) if o_min is not None else 0,
                    "max": round(o_max, 2) if o_max is not None else 0,
                    "avg": round(o_avg, 2) if o_avg is not None else 0,
                },
                "advanced_stats": {
                    "neg_ratio": neg_ratio,
                    "neg_avg": round(neg_avg, 2) if neg_avg is not None else None,
                    "neg_min": round(neg_min, 2) if neg_min is not None else None,
                    "pos_avg": round(pos_avg, 2) if pos_avg is not None else None,
                    "pos_max": round(pos_max, 2) if pos_max is not None else None,
                    "days_below_100": days_below_100,
                    "days_above_300": days_above_300,
                },
                "hourly_distribution": hourly_distribution,
                "data": data,
            }
            response = _attach_price_trend_metadata(response, region=region)
            response = _attach_regime_layer(
                response, market="WEM" if region == "WEM" else "NEM", region=region
            )
            return _store_response_cache(
                PRICE_TREND_RESPONSE_CACHE_SCOPE, cache_payload,
                response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in price-trend: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Route: /api/peak-analysis
# ---------------------------------------------------------------------------


@router.get(
    "/api/peak-analysis",
    summary="Get peak and trough spread analysis",
    description="Returns sliding-window peak/trough spread analysis with unified metadata.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_peak_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID"),
    aggregation: str = Query("monthly", description="Aggregation: daily, weekly, monthly, yearly"),
    network_fee: Optional[float] = Query(None, description="Override network fee ($/MWh)."),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
):
    """Sliding-window peak/trough analysis with network fee integration."""
    db = get_db()
    aggregation = _cacheable_param(aggregation)
    network_fee = _cacheable_param(network_fee)
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    table_name = trading_price_table(year)
    fee = network_fee if network_fee is not None else get_default_fee(region)
    windows = get_window_sizes(region)

    try:
        cache_payload = {
            "year": year,
            "region": region,
            "aggregation": aggregation,
            "network_fee": network_fee,
            "effective_network_fee": fee,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            cached = _attach_peak_analysis_metadata(cached, region=region)
            return _attach_regime_layer(cached, market="WEM" if region == "WEM" else "NEM", region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", (table_name,))
            if not cursor.fetchone():
                response = {
                    "region": region, "year": year, "aggregation": aggregation,
                    "network_fee": fee, "data": [], "summary": {},
                }
                response = _attach_peak_analysis_metadata(response, region=region)
                response = _attach_regime_layer(
                    response, market="WEM" if region == "WEM" else "NEM", region=region
                )
                return _store_response_cache(
                    PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload,
                    response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            where_clause, params = _build_temporal_filters(
                year, month, quarter, day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )
            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
                f"WHERE {where_clause} ORDER BY settlement_date ASC",
                tuple(params),
            )
            first_row = cursor.fetchone()

            if not first_row:
                response = {
                    "region": region, "year": year, "aggregation": aggregation,
                    "network_fee": fee, "data": [], "summary": {},
                }
                response = _attach_peak_analysis_metadata(response, region=region)
                response = _attach_regime_layer(
                    response, market="WEM" if region == "WEM" else "NEM", region=region
                )
                return _store_response_cache(
                    PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload,
                    response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            daily_results = list(
                _iter_peak_daily_results(
                    itertools.chain([first_row], cursor),
                    windows=windows,
                    fee=fee,
                )
            )

            if aggregation == "daily":
                aggregated = daily_results
            else:
                aggregated = _aggregate_peak_data(daily_results, aggregation)

            summary = _compute_summary(daily_results)

            response = {
                "region": region,
                "year": year,
                "aggregation": aggregation,
                "network_fee": fee,
                "filters": {
                    "month": month,
                    "quarter": quarter,
                    "day_type": day_type,
                },
                "data": aggregated,
                "summary": summary,
            }
            response = _attach_peak_analysis_metadata(response, region=region)
            response = _attach_regime_layer(
                response, market="WEM" if region == "WEM" else "NEM", region=region
            )
            return _store_response_cache(
                PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload,
                response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Peak analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Route: /api/hourly-price-profile
# ---------------------------------------------------------------------------


@router.get(
    "/api/hourly-price-profile",
    summary="Get hourly price profile",
    description="Returns hourly average/min/max price profile data for heatmap-style views.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_hourly_price_profile(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID"),
    month: Optional[str] = Query(None, description="Optional month filter (01-12)"),
):
    """Returns average, min, max prices for each hour of the day."""
    db = get_db()
    month = _cacheable_param(month)
    table_name = trading_price_table(year)
    try:
        cache_payload = {
            "year": year,
            "region": region,
            "month": month,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(HOURLY_PROFILE_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            cached = _attach_hourly_price_profile_metadata(cached, region=region)
            return _attach_regime_layer(cached, market="WEM" if region == "WEM" else "NEM", region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", (table_name,))
            if not cursor.fetchone():
                response = {
                    "region": region, "year": year, "month": month,
                    "data": [], "summary": {},
                }
                response = _attach_hourly_price_profile_metadata(response, region=region)
                response = _attach_regime_layer(
                    response, market="WEM" if region == "WEM" else "NEM", region=region
                )
                return _store_response_cache(
                    HOURLY_PROFILE_RESPONSE_CACHE_SCOPE, cache_payload,
                    response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            where = "region_id = ?"
            params = [region]
            if month and len(month) == 2:
                where += " AND settlement_date LIKE ?"
                params.append(f"{year}-{month}-%")

            query = f"""
                SELECT
                    CAST(substr(settlement_date, 12, 2) AS INTEGER) as hour,
                    ROUND(AVG(rrp_aud_mwh), 2) as avg_price,
                    ROUND(MIN(rrp_aud_mwh), 2) as min_price,
                    ROUND(MAX(rrp_aud_mwh), 2) as max_price,
                    COUNT(*) as count,
                    SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as neg_count,
                    ROUND(AVG(CASE WHEN rrp_aud_mwh < 0 THEN rrp_aud_mwh ELSE NULL END), 2) as neg_avg
                FROM {table_name}
                WHERE {where}
                GROUP BY hour
                ORDER BY hour ASC
            """
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            hourly = []
            for r in rows:
                total = r[4] if r[4] else 1
                hourly.append({
                    "hour": r[0],
                    "avg_price": r[1],
                    "min_price": r[2],
                    "max_price": r[3],
                    "count": r[4],
                    "neg_pct": round((r[5] / total) * 100, 1) if r[5] else 0,
                    "neg_avg": r[6],
                })

            # Pad missing hours
            hour_map = {h["hour"]: h for h in hourly}
            result = []
            for h in range(24):
                if h in hour_map:
                    result.append(hour_map[h])
                else:
                    result.append({
                        "hour": h, "avg_price": 0, "min_price": 0,
                        "max_price": 0, "count": 0, "neg_pct": 0, "neg_avg": None,
                    })

            response = {"region": region, "year": year, "month": month, "hourly": result}
            response = _attach_hourly_price_profile_metadata(response, region=region)
            response = _attach_regime_layer(
                response, market="WEM" if region == "WEM" else "NEM", region=region
            )
            return _store_response_cache(
                HOURLY_PROFILE_RESPONSE_CACHE_SCOPE, cache_payload,
                response, DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hourly profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
