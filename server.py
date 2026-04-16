from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import json
import sqlite3
import threading
import uvicorn
from contextlib import asynccontextmanager
import logging
from typing import Optional
import datetime
import subprocess
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import DatabaseManager
import grid_events
import grid_forecast
from network_fees import get_default_fee, get_window_sizes, get_all_fees, get_settlement_interval
from collections import defaultdict
from response_cache import RedisResponseCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "aemo_data.db"
db = DatabaseManager(DB_PATH)
response_cache = RedisResponseCache()

GRID_FORECAST_RESPONSE_CACHE_SCOPE = "api_grid_forecast_v1"
EVENT_OVERLAY_RESPONSE_CACHE_SCOPE = "api_event_overlays_v1"
PRICE_TREND_RESPONSE_CACHE_SCOPE = "api_price_trend_v1"
PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_peak_analysis_v1"
FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_fcas_analysis_v1"
HOURLY_PROFILE_RESPONSE_CACHE_SCOPE = "api_hourly_price_profile_v1"
INVESTMENT_RESPONSE_REDIS_SCOPE = "api_investment_analysis_v1"

DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 6 * 60 * 60
EVENT_OVERLAY_CACHE_TTL_SECONDS = 30 * 60
INVESTMENT_RESPONSE_CACHE_TTL_SECONDS = 24 * 60 * 60
GRID_FORECAST_CACHE_TTL_SECONDS = {
    "24h": 60 * 60,
    "7d": 6 * 60 * 60,
    "30d": 12 * 60 * 60,
}


def _stable_cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _market_data_version() -> str:
    return db.get_last_update_time() or "no_last_update"


def _event_overlay_data_version() -> str:
    return _stable_cache_key({
        "market_version": _market_data_version(),
        "event_sync": db.fetch_grid_event_sync_states(),
    })


def _grid_forecast_data_version() -> str:
    return _event_overlay_data_version()


def _fetch_response_cache(scope: str, payload: dict, normalize_fn=None):
    cache_key = _stable_cache_key(payload)
    cached = response_cache.get_json(scope, cache_key)
    if cached is None:
        return None
    return normalize_fn(cached) if normalize_fn else cached


def _store_response_cache(scope: str, payload: dict, response_payload: dict, ttl_seconds: int):
    cache_key = _stable_cache_key(payload)
    response_cache.set_json(scope, cache_key, response_payload, ttl_seconds)
    return response_payload


def _cacheable_param(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    default = getattr(value, "default", None)
    if isinstance(default, (str, int, float, bool)) or default is None:
        return default
    return str(value)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting AEMO NEM API server with built-in Scheduler...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_sync_scrapers, 'cron', hour=2, minute=0)
    scheduler.start()
    app.state.scheduler = scheduler
    
    yield
    # Shutdown actions
    logger.info("Shutting down AEMO NEM API server...")
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()

app = FastAPI(title="AEMO NEM Data API", lifespan=lifespan)

# Allow CORS for the frontend Vite server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev, allow all. Restrict in prod.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/summary")
def get_summary():
    """Returns database summary statistics (tables, time ranges, record counts) and last update time"""
    try:
        summary = db.get_summary()
        summary["last_update"] = db.get_last_update_time()
        return summary
    except Exception as e:
        logger.error(f"Error fetching summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/event-overlays")
def get_event_overlays(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1, WEM)"),
    market: Optional[str] = Query(None, description="Optional market override: NEM or WEM"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
):
    try:
        market = _cacheable_param(market)
        month = _cacheable_param(month)
        quarter = _cacheable_param(quarter)
        day_type = _cacheable_param(day_type)
        cache_payload = {
            "year": year,
            "region": region,
            "market": market,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "data_version": _event_overlay_data_version(),
        }
        cached = _fetch_response_cache(EVENT_OVERLAY_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return cached

        response = grid_events.get_event_overlay_response(
            db,
            year=year,
            region=region,
            market=market,
            month=month,
            quarter=quarter,
            day_type=day_type,
        )
        return _store_response_cache(
            EVENT_OVERLAY_RESPONSE_CACHE_SCOPE,
            cache_payload,
            response,
            EVENT_OVERLAY_CACHE_TTL_SECONDS,
        )
    except Exception as e:
        logger.error(f"Event overlay error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/grid-forecast")
def get_grid_forecast(
    market: str = Query(..., description="Market code: NEM or WEM"),
    region: str = Query(..., description="Region code such as NSW1 or WEM"),
    horizon: str = Query(..., pattern="^(24h|7d|30d)$", description="Forecast horizon"),
    as_of: Optional[str] = Query(None, description="Optional forecast issue timestamp"),
):
    try:
        market = _cacheable_param(market)
        region = _cacheable_param(region)
        horizon = _cacheable_param(horizon)
        as_of = _cacheable_param(as_of)
        cache_payload = {
            "market": market,
            "region": region,
            "horizon": horizon,
            "as_of_bucket": grid_forecast.build_as_of_bucket(as_of, horizon),
            "data_version": _grid_forecast_data_version(),
        }
        cached = _fetch_response_cache(GRID_FORECAST_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return cached

        response = grid_forecast.get_grid_forecast_response(
            db,
            market=market,
            region=region,
            horizon=horizon,
            as_of=as_of,
        )
        return _store_response_cache(
            GRID_FORECAST_RESPONSE_CACHE_SCOPE,
            cache_payload,
            response,
            GRID_FORECAST_CACHE_TTL_SECONDS.get(horizon, DEFAULT_RESPONSE_CACHE_TTL_SECONDS),
        )
    except Exception as e:
        logger.error(f"Grid forecast error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/grid-forecast/coverage")
def get_grid_forecast_coverage(
    market: str = Query(..., description="Market code: NEM or WEM"),
    region: str = Query(..., description="Region code such as NSW1 or WEM"),
    horizon: str = Query(..., pattern="^(24h|7d|30d)$", description="Forecast horizon"),
    as_of: Optional[str] = Query(None, description="Optional forecast issue timestamp"),
):
    try:
        return grid_forecast.get_grid_forecast_coverage(
            db,
            market=market,
            region=region,
            horizon=horizon,
            as_of=as_of,
        )
    except Exception as e:
        logger.error(f"Grid forecast coverage error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def run_sync_scrapers():
    """Background task to run scrapers and update the database."""
    try:
        logger.info("Starting Background Data Syncing Tasks...")
        # WEM and NEM Sync: Incremental (Last 14 days)
        two_weeks_ago = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"Running WEM Scraper from {two_weeks_ago} to {today}...")
        subprocess.run(["python", "aemo_wem_scraper.py", "--start", two_weeks_ago, "--end", today], check=True)

        logger.info("Running WEM ESS slim sync for latest 30 days...")
        subprocess.run(["python", "aemo_wem_ess_scraper.py", "--days", "30"], check=True)
        
        logger.info("Running NEM Scraper...")
        start_month = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime('%Y-%m')
        end_month = datetime.datetime.now().strftime('%Y-%m')
        subprocess.run(["python", "aemo_nem_scraper.py", "--start", start_month, "--end", end_month, "--fcas"], check=True)

        logger.info("Running Grid Event Scraper...")
        subprocess.run(["python", "aemo_grid_event_scraper.py", "--days", "180"], check=True)

        
        # Record Success Time
        db.set_last_update_time(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        logger.info("Data Syncing Completed successfully!")
    except Exception as e:
        logger.error(f"Error in data sync task: {e}")

@app.post("/api/sync_data")
def sync_data(background_tasks: BackgroundTasks):
    """Trigger data scrape manually via background task."""
    background_tasks.add_task(run_sync_scrapers)
    return {"status": "Update started in background"}


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
            f"CAST(strftime('%w', substr({time_field}, 1, 19)) AS INTEGER) IN (1, 2, 3, 4, 5)"
        )
    elif day_type == "WEEKEND":
        clauses.append(
            f"CAST(strftime('%w', substr({time_field}, 1, 19)) AS INTEGER) IN (0, 6)"
        )

    return " AND ".join(clauses) if clauses else "1=1", params


@app.get("/api/years")
def get_available_years():
    """Returns a list of years for which data tables exist"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%'")
            tables = [r[0] for r in cursor.fetchall()]
            years = sorted([int(t.split('_')[-1]) for t in tables], reverse=True)
            return {"years": years}
    except Exception as e:
        logger.error(f"Error fetching years: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/price-trend")
def get_price_trend(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1, QLD1)"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    limit: Optional[int] = Query(1500, description="Max points to return to avoid overwhelming frontend.")
):
    """
    Returns time series data with dynamic sampling to handle large arrays.
    """
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    limit = _cacheable_param(limit)
    table_name = f"trading_price_{year}"
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
            return cached

        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data available for year {year}")

            where_clause, params = _build_temporal_filters(
                year,
                month,
                quarter,
                day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )

            # Get total count for the region and applied filters
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", tuple(params))
            total_rows = cursor.fetchone()[0]
            
            if total_rows == 0:
                response = {
                    "region": region, "year": year, "month": month, "total_points": 0, "returned_points": 0,
                    "stats": {"min": 0, "max": 0, "avg": 0},
                    "advanced_stats": {"neg_ratio": 0, "neg_avg": 0, "neg_min": 0, "pos_avg": 0, "pos_max": 0, "days_below_100": 0, "days_above_300": 0},
                    "hourly_distribution": [], "data": []
                }
                return _store_response_cache(
                    PRICE_TREND_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # Fetch the time-series data
            query_data = f"""
                SELECT settlement_date, rrp_aud_mwh
                FROM {table_name}
                WHERE {where_clause}
                ORDER BY settlement_date ASC
            """
            
            cursor.execute(query_data, tuple(params))
            rows = cursor.fetchall()
            
            data = []
            if len(rows) > limit:
                import numpy as np
                import lttbc
                x = np.arange(len(rows), dtype=np.float64)
                y = np.array([r[1] for r in rows], dtype=np.float64)
                dx, dy = lttbc.downsample(x, y, limit)
                for idx_flt, val in zip(dx, dy):
                    orig_idx = int(round(idx_flt))
                    data.append({"time": rows[orig_idx][0], "price": round(val, 2)})
            else:
                for r in rows:
                    data.append({"time": r[0], "price": round(r[1], 2)})
            
            # Calculate all statistics in a single highly optimized SQL query
            # This turns 6 separate full table scans into just 1
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

            # Hourly Distribution of Negative Prices (requires GROUP BY so kept separate, but relatively fast)
            hourly_query = f"""
                SELECT 
                    substr(datetime(settlement_date, '-1 second'), 12, 2) as hour_bucket,
                    COUNT(*)
                FROM {table_name}
                WHERE {where_clause} AND rrp_aud_mwh < 0
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
            """
            cursor.execute(hourly_query, tuple(params))
            hourly_rows = cursor.fetchall()
            
            # Pad with 0s for missing hours
            hourly_dict = {r[0]: r[1] for r in hourly_rows}
            hourly_distribution = []
            for h in range(24):
                hr_str = f"{h:02d}"
                hourly_distribution.append({
                    "hour": hr_str,
                    "count": hourly_dict.get(hr_str, 0)
                })
            
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
                    "days_above_300": days_above_300
                },
                "hourly_distribution": hourly_distribution,
                "data": data
            }
            return _store_response_cache(
                PRICE_TREND_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.error(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/network-fees")
def get_network_fees():
    """Returns default network fees (TUOS+DUOS) for all regions."""
    return {"fees": get_all_fees()}


@app.get("/api/peak-analysis")
def get_peak_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID"),
    aggregation: str = Query("monthly", description="Aggregation: daily, weekly, monthly, yearly"),
    network_fee: Optional[float] = Query(None, description="Override network fee ($/MWh). If omitted, uses default for region."),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
):
    """
    Sliding-window peak/trough analysis with network fee integration.
    Returns peak/trough averages for 1h/2h/4h/6h windows and spread calculations.
    """
    aggregation = _cacheable_param(aggregation)
    network_fee = _cacheable_param(network_fee)
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    table_name = f"trading_price_{year}"
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
            return cached

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check table exists
            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

            # Fetch all data for this year+region, ordered by time
            where_clause, params = _build_temporal_filters(
                year,
                month,
                quarter,
                day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )
            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
                f"WHERE {where_clause} ORDER BY settlement_date ASC",
                tuple(params),
            )
            rows = cursor.fetchall()

            if not rows:
                response = {
                    "region": region, "year": year, "aggregation": aggregation,
                    "network_fee": fee, "data": [], "summary": {}
                }
                return _store_response_cache(
                    PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # Group by day: { "2025-01-15": [price1, price2, ...] }
            daily_prices = defaultdict(list)
            for date_str, price in rows:
                day_key = date_str[:10]  # "2025-01-15"
                daily_prices[day_key].append(price)

            # Sliding window analysis for each day
            daily_results = []
            for day, prices in sorted(daily_prices.items()):
                n = len(prices)
                result = {"date": day}

                for label, w_size in windows.items():
                    if n < w_size:
                        # Not enough data points for this window
                        result[f"peak_{label}"] = None
                        result[f"trough_{label}"] = None
                        continue

                    # Efficient sliding window using running sum
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

                # Calculate spreads for 2h/4h/6h
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

                daily_results.append(result)

            # Aggregate based on requested granularity
            if aggregation == "daily":
                aggregated = daily_results
            else:
                aggregated = _aggregate_peak_data(daily_results, aggregation)

            # Compute overall summary
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
                "summary": summary
            }
            return _store_response_cache(
                PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Peak analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _aggregate_peak_data(daily_results: list, aggregation: str) -> list:
    """Aggregate daily peak/trough results by week, month, or year."""
    groups = defaultdict(list)

    for row in daily_results:
        day = row["date"]
        if aggregation == "weekly":
            # ISO week: "2025-W03"
            d = datetime.datetime.strptime(day, "%Y-%m-%d")
            iso_year, iso_week, _ = d.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        elif aggregation == "monthly":
            key = day[:7]  # "2025-01"
        elif aggregation == "yearly":
            key = day[:4]  # "2025"
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


# ============================================================
# Hourly Price Profile (for Clock Heatmap / Charging Window)
# ============================================================

@app.get("/api/hourly-price-profile")
def get_hourly_price_profile(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID"),
    month: Optional[str] = Query(None, description="Optional month filter (01-12)"),
):
    """
    Returns average, min, max prices for each hour of the day.
    Used for the Clock Heatmap / Negative Pricing Window visualization.
    """
    month = _cacheable_param(month)
    table_name = f"trading_price_{year}"
    try:
        cache_payload = {
            "year": year,
            "region": region,
            "month": month,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(HOURLY_PROFILE_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return cached

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

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
                        "max_price": 0, "count": 0, "neg_pct": 0, "neg_avg": None
                    })

            response = {"region": region, "year": year, "month": month, "hourly": result}
            return _store_response_cache(
                HOURLY_PROFILE_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hourly profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================
# FCAS (Frequency Control Ancillary Services) Analysis
# ============================================================

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

WEM_ESS_SERVICES = {
    "regulation_raise": {
        "label": "Regulation Raise",
        "price_col": "regulation_raise_price",
        "available_col": "available_regulation_raise",
        "in_service_col": "in_service_regulation_raise",
        "requirement_col": "requirement_regulation_raise",
        "shortfall_col": "shortfall_regulation_raise",
        "dispatch_total_col": "dispatch_total_regulation_raise",
        "capped_col": "capped_regulation_raise",
        "group": "raise",
    },
    "regulation_lower": {
        "label": "Regulation Lower",
        "price_col": "regulation_lower_price",
        "available_col": "available_regulation_lower",
        "in_service_col": "in_service_regulation_lower",
        "requirement_col": "requirement_regulation_lower",
        "shortfall_col": "shortfall_regulation_lower",
        "dispatch_total_col": "dispatch_total_regulation_lower",
        "capped_col": "capped_regulation_lower",
        "group": "lower",
    },
    "contingency_raise": {
        "label": "Contingency Raise",
        "price_col": "contingency_raise_price",
        "available_col": "available_contingency_raise",
        "in_service_col": "in_service_contingency_raise",
        "requirement_col": "requirement_contingency_raise",
        "shortfall_col": "shortfall_contingency_raise",
        "dispatch_total_col": "dispatch_total_contingency_raise",
        "capped_col": "capped_contingency_raise",
        "group": "raise",
    },
    "contingency_lower": {
        "label": "Contingency Lower",
        "price_col": "contingency_lower_price",
        "available_col": "available_contingency_lower",
        "in_service_col": "in_service_contingency_lower",
        "requirement_col": "requirement_contingency_lower",
        "shortfall_col": "shortfall_contingency_lower",
        "dispatch_total_col": "dispatch_total_contingency_lower",
        "capped_col": "capped_contingency_lower",
        "group": "lower",
    },
    "rocof": {
        "label": "RoCoF",
        "price_col": "rocof_price",
        "available_col": "available_rocof",
        "in_service_col": "in_service_rocof",
        "requirement_col": "requirement_rocof",
        "shortfall_col": "shortfall_rocof",
        "dispatch_total_col": "dispatch_total_rocof",
        "capped_col": "capped_rocof",
        "group": "raise",
    },
}


def _aggregate_period_key(date_str: str, aggregation: str) -> str:
    if aggregation == "daily":
        return date_str[:10]
    if aggregation == "weekly":
        d = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return date_str[:7]


def _estimate_wem_capture(row: dict, service_meta: dict, capacity_mw: float) -> tuple[float, float, float]:
    dispatch_total = row.get(service_meta["dispatch_total_col"]) or 0.0
    shortfall = row.get(service_meta["shortfall_col"]) or 0.0
    in_service = row.get(service_meta["in_service_col"]) or 0.0
    requirement = row.get(service_meta["requirement_col"]) or 0.0
    available = row.get(service_meta["available_col"]) or 0.0

    candidate_mw = min(capacity_mw, max(dispatch_total + shortfall, dispatch_total, 0.0))
    if in_service > 0:
        capture_rate = min(dispatch_total / in_service, 1.0)
    elif dispatch_total > 0:
        capture_rate = 1.0
    else:
        capture_rate = 0.0

    enabled_mw = min(candidate_mw * capture_rate, max(dispatch_total + shortfall, 0.0))
    tightness = 0.0
    if requirement > 0:
        tightness = max(0.0, 1 - min(available / requirement, 1.0))
    return enabled_mw, capture_rate, tightness


def _get_wem_ess_analysis(
    year: int,
    aggregation: str,
    capacity_mw: float,
    month: Optional[str] = None,
    quarter: Optional[str] = None,
    day_type: Optional[str] = None,
):
    market_table = db.WEM_ESS_MARKET_TABLE
    constraint_table = db.WEM_ESS_CONSTRAINT_TABLE
    interval_hours = 5 / 60

    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        cursor = conn.cursor()
        where_clause, params = _build_temporal_filters(
            year,
            month,
            quarter,
            day_type,
            time_field="m.dispatch_interval",
            region=None,
            region_field=None,
            force_year_prefix=True,
        )
        cursor.execute(
            f"""
            SELECT m.*,
                   c.binding_count,
                   c.near_binding_count,
                   c.binding_max_shadow_price
            FROM {market_table} m
            LEFT JOIN {constraint_table} c ON c.dispatch_interval = m.dispatch_interval
            WHERE {where_clause}
            ORDER BY m.dispatch_interval ASC
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]

    if not rows:
        return {
            "region": "WEM",
            "year": year,
            "has_fcas_data": False,
            "message": "No WEM ESS slim data available for this year. Run the WEM ESS latest-month sync first.",
            "data": [],
            "summary": {},
            "hourly": [],
            "service_breakdown": [],
        }

    records = [dict(zip(col_names, row)) for row in rows]
    grouped = defaultdict(list)
    hourly_buckets = defaultdict(list)
    service_breakdown = []

    for record in records:
        period = _aggregate_period_key(record["dispatch_interval"], aggregation)
        grouped[period].append(record)
        hour_bucket = record["dispatch_interval"][11:13]
        total_price = 0.0
        for service_key, meta in WEM_ESS_SERVICES.items():
            total_price += record.get(meta["price_col"]) or 0.0
        hourly_buckets[hour_bucket].append(total_price)

    for service_key, meta in WEM_ESS_SERVICES.items():
        prices = []
        revenues = []
        requirements = []
        in_service = []
        available = []
        dispatch_totals = []
        capture_rates = []
        tightness_scores = []
        shortfall_intervals = 0
        capped_intervals = 0

        for record in records:
            price = record.get(meta["price_col"])
            if price is None:
                continue
            prices.append(price)
            requirements.append(record.get(meta["requirement_col"]) or 0.0)
            in_service.append(record.get(meta["in_service_col"]) or 0.0)
            available.append(record.get(meta["available_col"]) or 0.0)
            dispatch_totals.append(record.get(meta["dispatch_total_col"]) or 0.0)
            enabled_mw, capture_rate, tightness = _estimate_wem_capture(record, meta, capacity_mw)
            revenues.append(enabled_mw * price * interval_hours / 1000)
            capture_rates.append(capture_rate)
            tightness_scores.append(tightness)
            if (record.get(meta["shortfall_col"]) or 0.0) > 0:
                shortfall_intervals += 1
            if record.get(meta["capped_col"]) == 1:
                capped_intervals += 1

        avg_price = sum(prices) / len(prices) if prices else 0.0
        service_breakdown.append(
            {
                "service": meta["label"],
                "key": service_key,
                "group": meta["group"],
                "avg_price": round(avg_price, 2),
                "max_price": round(max(prices), 2) if prices else 0.0,
                "est_revenue_k": round(sum(revenues), 1),
                "avg_requirement_mw": round(sum(requirements) / len(requirements), 2) if requirements else 0.0,
                "avg_in_service_mw": round(sum(in_service) / len(in_service), 2) if in_service else 0.0,
                "avg_available_mw": round(sum(available) / len(available), 2) if available else 0.0,
                "avg_dispatch_total_mw": round(sum(dispatch_totals) / len(dispatch_totals), 2) if dispatch_totals else 0.0,
                "avg_capture_rate": round(sum(capture_rates) / len(capture_rates), 4) if capture_rates else 0.0,
                "avg_tightness": round(sum(tightness_scores) / len(tightness_scores), 4) if tightness_scores else 0.0,
                "shortfall_intervals": shortfall_intervals,
                "capped_intervals": capped_intervals,
            }
        )

    hourly = []
    for h in range(24):
        hour_key = f"{h:02d}"
        values = hourly_buckets.get(hour_key, [])
        hourly.append(
            {
                "hour": hour_key,
                "avg_total_fcas": round(sum(values) / len(values), 2) if values else 0.0,
            }
        )

    data = []
    for period, items in sorted(grouped.items()):
        entry = {"period": period, "intervals": len(items)}
        for service_key, meta in WEM_ESS_SERVICES.items():
            values = [item.get(meta["price_col"]) for item in items if item.get(meta["price_col"]) is not None]
            entry[service_key] = round(sum(values) / len(values), 2) if values else 0.0
        entry["total_fcas_avg"] = round(
            sum(
                sum(item.get(meta["price_col"]) or 0.0 for meta in WEM_ESS_SERVICES.values())
                for item in items
            ) / len(items),
            2,
        )
        entry["binding_count_avg"] = round(
            sum(item.get("binding_count") or 0 for item in items) / len(items),
            2,
        )
        entry["binding_shadow_max"] = round(
            max(item.get("binding_max_shadow_price") or 0.0 for item in items),
            2,
        )
        data.append(entry)

    total_avg_fcas = sum(item["avg_price"] for item in service_breakdown)
    total_est_revenue = sum(item["est_revenue_k"] for item in service_breakdown)
    avg_capture_rate = (
        round(sum(item["avg_capture_rate"] for item in service_breakdown) / len(service_breakdown), 4)
        if service_breakdown else 0.0
    )
    coverage_days = len({record["dispatch_interval"][:10] for record in records})
    preview_mode = "single_day_preview" if coverage_days == 1 else "multi_day_preview"

    return {
        "region": "WEM",
        "year": year,
        "has_fcas_data": True,
        "aggregation": aggregation,
        "estimate_basis": "price_taker_share_using_dispatch_total_and_in_service",
        "summary": {
            "total_avg_fcas_price": round(total_avg_fcas, 2),
            "total_est_revenue_k": round(total_est_revenue, 1),
            "total_intervals": len(records),
            "capacity_mw": capacity_mw,
            "data_points_with_fcas": len(records),
            "avg_capture_rate": avg_capture_rate,
            "revenue_scope": "loaded_window",
            "coverage_start": records[0]["dispatch_interval"],
            "coverage_end": records[-1]["dispatch_interval"],
            "coverage_days": coverage_days,
            "preview_mode": preview_mode,
            "investment_grade": False,
            "message": (
                "WEM ESS revenue uses a slim-table preview estimate based on dispatchTotal and "
                "inService quantities. Current output is not investment-grade project finance data."
            ),
        },
        "service_breakdown": service_breakdown,
        "hourly": hourly,
        "data": data,
    }


@app.get("/api/fcas-analysis")
def get_fcas_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1)"),
    aggregation: str = Query("daily", description="Aggregation: daily, weekly, monthly"),
    capacity_mw: float = Query(100, description="Battery capacity in MW for revenue estimation"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
):
    """
    FCAS revenue analysis endpoint.
    Returns per-service average prices, revenue estimates, hourly distribution,
    and time series data for charting.
    """
    aggregation = _cacheable_param(aggregation)
    capacity_mw = _cacheable_param(capacity_mw)
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    cache_payload = {
        "year": year,
        "region": region,
        "aggregation": aggregation,
        "capacity_mw": capacity_mw,
        "month": month,
        "quarter": quarter,
        "day_type": day_type,
        "data_version": _market_data_version(),
    }
    cached = _fetch_response_cache(FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload)
    if cached is not None:
        return cached

    if region == "WEM":
        try:
            response = _get_wem_ess_analysis(year, aggregation, capacity_mw, month, quarter, day_type)
            return _store_response_cache(
                FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.error(f"WEM ESS analysis error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    table_name = f"trading_price_{year}"

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

            # Check if FCAS columns exist in the table
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            available_fcas = [c for c in FCAS_COLUMNS if c in existing_cols]

            if not available_fcas:
                response = {
                    "region": region, "year": year, "has_fcas_data": False,
                    "message": "No FCAS data available. Run scraper with --fcas flag.",
                    "data": [], "summary": {}, "hourly": [], "service_breakdown": []
                }
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
            check_query = f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause} AND ({nonnull_expr})"
            cursor.execute(check_query, tuple(params))
            fcas_count = cursor.fetchone()[0]

            if fcas_count == 0:
                response = {
                    "region": region, "year": year, "has_fcas_data": False,
                    "message": "FCAS columns exist but no data yet. Re-sync with --fcas flag.",
                    "data": [], "summary": {}, "hourly": [], "service_breakdown": []
                }
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
                max_price = agg_row[n_fcas + i] if agg_row and agg_row[n_fcas + i] is not None else 0
                # Revenue estimate: price * capacity * (5min / 60min) per interval
                est_revenue = avg_price * capacity_mw * total_intervals * (5 / 60) / 1000  # in $k
                service_breakdown.append({
                    "service": FCAS_SERVICES.get(svc_key, svc_key),
                    "key": svc_key,
                    "group": FCAS_GROUPS.get(svc_key),
                    "avg_price": round(avg_price, 2),
                    "max_price": round(max_price, 2),
                    "est_revenue_k": round(est_revenue, 1),
                })

            # 2. Hourly distribution of FCAS prices (average by hour)
            total_fcas_expr = " + ".join(f"COALESCE({col}, 0)" for col in available_fcas)
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
            hourly = [{"hour": f"{h:02d}", "avg_total_fcas": hourly_dict.get(h, 0)} for h in range(24)]

            # 3. Time series aggregated by day/week/month
            if aggregation == "daily":
                date_expr = "substr(settlement_date, 1, 10)"
            elif aggregation == "weekly":
                date_expr = "strftime('%Y-W%W', settlement_date)"
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

            # 4. Overall summary
            total_avg_fcas = sum(s["avg_price"] for s in service_breakdown)
            total_est_revenue_k = sum(s["est_revenue_k"] for s in service_breakdown)

            summary = {
                "total_avg_fcas_price": round(total_avg_fcas, 2),
                "total_est_revenue_k": round(total_est_revenue_k, 1),
                "total_intervals": total_intervals,
                "capacity_mw": capacity_mw,
                "data_points_with_fcas": fcas_count,
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
                "summary": summary,
                "service_breakdown": service_breakdown,
                "hourly": hourly,
                "data": ts_data,
            }
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


# ============================================================
# Investment Analysis (BESS Cash Flow / NPV / IRR)
# ============================================================

from pydantic import BaseModel
from typing import List, Dict
import math

INVESTMENT_RESPONSE_CACHE_SCOPE = "investment_response_v1"
INVESTMENT_BACKTEST_CACHE_SCOPE = "investment_backtest_v1"
INVESTMENT_FCAS_CACHE_SCOPE = "investment_fcas_v1"
_ANALYSIS_INFLIGHT_LOCK = threading.Lock()
_ANALYSIS_INFLIGHT: Dict[str, dict] = {}

class InvestmentParams(BaseModel):
    region: str = "SA1"
    # Storage specs
    power_mw: float = 100
    duration_hours: float = 4
    round_trip_efficiency: float = 0.87
    degradation_rate: float = 0.025  # 2.5%/year
    # Cost params (AUD)
    capex_per_kwh: float = 350  # $/kWh total EPC
    fixed_om_per_mw_year: float = 12000  # $/MW/year
    variable_om_per_mwh: float = 2.5  # $/MWh discharged
    grid_connection_cost: float = 5000000  # one-time
    land_lease_per_year: float = 200000
    # Finance
    discount_rate: float = 0.08  # 8%
    project_life_years: int = 20
    # Revenue adjustments
    revenue_capture_rate: float = 0.65  # realistic vs perfect foresight
    fcas_revenue_per_mw_year: float = 15000  # additional FCAS income
    fcas_revenue_mode: Optional[str] = None  # auto for NEM, manual for WEM by default
    capacity_payment_per_mw_year: float = 0  # WEM RCM or CIS
    # Backtest years to use for projection
    backtest_years: List[int] = [2024, 2025]


def _estimate_nem_fcas_baseline(conn, region: str, years: List[int], power_mw: float):
    annual_estimates = []
    cursor = conn.cursor()
    interval_hours = 5 / 60

    for year in years:
        table_name = f"trading_price_{year}"
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        if not cursor.fetchone():
            continue

        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        available_fcas = [col for col in FCAS_COLUMNS if col in existing_cols]
        if not available_fcas:
            continue

        nonnull_expr = " OR ".join(f"{col} IS NOT NULL" for col in available_fcas)
        total_fcas_expr = " + ".join(f"COALESCE({col}, 0)" for col in available_fcas)
        cursor.execute(
            f"""
            SELECT SUM(({total_fcas_expr}) * ? * ?) as annual_estimate
            FROM {table_name}
            WHERE region_id = ? AND ({nonnull_expr})
            """,
            (power_mw, interval_hours, region),
        )
        estimate = cursor.fetchone()[0]
        if estimate:
            annual_estimates.append(float(estimate))

    if not annual_estimates:
        return 0.0, "manual_input_no_historical_fcas"
    return sum(annual_estimates) / len(annual_estimates), "historical_auto"


def _stable_cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _analysis_data_version() -> str:
    return db.get_last_update_time() or "no_last_update"


def _investment_response_cache_key(params: InvestmentParams, capacity_mwh: float) -> str:
    return _stable_cache_key({
        "region": params.region,
        "power_mw": params.power_mw,
        "duration_hours": params.duration_hours,
        "capacity_mwh": capacity_mwh,
        "round_trip_efficiency": params.round_trip_efficiency,
        "degradation_rate": params.degradation_rate,
        "capex_per_kwh": params.capex_per_kwh,
        "fixed_om_per_mw_year": params.fixed_om_per_mw_year,
        "variable_om_per_mwh": params.variable_om_per_mwh,
        "grid_connection_cost": params.grid_connection_cost,
        "land_lease_per_year": params.land_lease_per_year,
        "discount_rate": params.discount_rate,
        "project_life_years": params.project_life_years,
        "revenue_capture_rate": params.revenue_capture_rate,
        "fcas_revenue_per_mw_year": params.fcas_revenue_per_mw_year,
        "fcas_revenue_mode": params.fcas_revenue_mode,
        "capacity_payment_per_mw_year": params.capacity_payment_per_mw_year,
        "backtest_years": sorted(params.backtest_years),
    })


def _investment_backtest_cache_key(
    *,
    region: str,
    year: int,
    power_mw: float,
    duration_hours: float,
    capacity_mwh: float,
    round_trip_efficiency: float,
) -> str:
    return _stable_cache_key({
        "region": region,
        "year": year,
        "power_mw": power_mw,
        "duration_hours": duration_hours,
        "capacity_mwh": capacity_mwh,
        "round_trip_efficiency": round_trip_efficiency,
    })


def _investment_fcas_cache_key(*, region: str, years: List[int], power_mw: float) -> str:
    return _stable_cache_key({
        "region": region,
        "years": sorted(years),
        "power_mw": power_mw,
    })


def _normalize_cached_investment_response(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload
    backtest = payload.get("backtest")
    if not isinstance(backtest, dict):
        return payload

    normalized = {}
    for key, value in backtest.items():
        if isinstance(key, str) and key.isdigit():
            normalized[int(key)] = value
        else:
            normalized[key] = value

    result = dict(payload)
    result["backtest"] = normalized
    return result


def _analysis_inflight_key(*, scope: str, cache_key: str, data_version: str) -> str:
    return f"{scope}:{data_version}:{cache_key}"


def _fetch_or_compute_analysis_cache(*, scope: str, cache_key: str, data_version: str, compute_fn):
    cached = db.fetch_analysis_cache(
        scope=scope,
        cache_key=cache_key,
        data_version=data_version,
    )
    if cached is not None:
        return cached

    inflight_key = _analysis_inflight_key(
        scope=scope,
        cache_key=cache_key,
        data_version=data_version,
    )
    is_leader = False

    with _ANALYSIS_INFLIGHT_LOCK:
        inflight = _ANALYSIS_INFLIGHT.get(inflight_key)
        if inflight is None:
            inflight = {
                "event": threading.Event(),
                "result": None,
                "error": None,
            }
            _ANALYSIS_INFLIGHT[inflight_key] = inflight
            is_leader = True

    if not is_leader:
        inflight["event"].wait()
        if inflight["error"] is not None:
            raise RuntimeError(str(inflight["error"])) from inflight["error"]
        if inflight["result"] is not None:
            return inflight["result"]
        return db.fetch_analysis_cache(
            scope=scope,
            cache_key=cache_key,
            data_version=data_version,
        )

    try:
        result = compute_fn()
        inflight["result"] = result
        if not (isinstance(result, dict) and "error" in result):
            db.upsert_analysis_cache(
                scope=scope,
                cache_key=cache_key,
                data_version=data_version,
                response_payload=result or {},
            )
        return result
    except Exception as exc:
        inflight["error"] = exc
        raise
    finally:
        inflight["event"].set()
        with _ANALYSIS_INFLIGHT_LOCK:
            _ANALYSIS_INFLIGHT.pop(inflight_key, None)


def _run_investment_backtest(*, region: str, year: int, storage_config: dict):
    import bess_backtest

    with db.get_connection() as conn:
        return bess_backtest.backtest_arbitrage(conn, region, year, storage_config)


def _run_investment_fcas_baseline(*, region: str, years: List[int], power_mw: float):
    with db.get_connection() as conn:
        baseline_fcas, fcas_baseline_source = _estimate_nem_fcas_baseline(
            conn,
            region,
            years,
            power_mw,
        )
    return {
        "baseline_fcas": baseline_fcas,
        "fcas_baseline_source": fcas_baseline_source,
    }


def _compute_investment_analysis_response(
    params: InvestmentParams,
    *,
    capacity_mwh: float,
    data_version: str,
):
    actual_fcas_mode = params.fcas_revenue_mode or ("manual" if params.region == "WEM" else "auto")

    yearly_revenues = {}
    total_discharge_history = []
    backtest_mode = "optimized_hindsight / physical_upper_bound"
    storage_config = {
        "duration_hours": params.duration_hours,
        "power_mw": params.power_mw,
        "capacity_mwh": capacity_mwh,
    }
    assumptions = [
        "Arbitrage baseline is derived from an optimized hindsight backtest and should be treated as a physical upper bound, not realized dispatch revenue.",
        f"Revenue capture rate ({params.revenue_capture_rate:.0%}) converts the backtest upper bound into an implementable arbitrage baseline.",
        "Capacity payment remains a manual user input.",
    ]
    for year in params.backtest_years:
        backtest_cache_key = _investment_backtest_cache_key(
            region=params.region,
            year=year,
            power_mw=params.power_mw,
            duration_hours=params.duration_hours,
            capacity_mwh=capacity_mwh,
            round_trip_efficiency=params.round_trip_efficiency,
        )
        res = _fetch_or_compute_analysis_cache(
            scope=INVESTMENT_BACKTEST_CACHE_SCOPE,
            cache_key=backtest_cache_key,
            data_version=data_version,
            compute_fn=lambda year=year: _run_investment_backtest(
                region=params.region,
                year=year,
                storage_config=storage_config,
            ),
        )

        if res and res.get("total_revenue_aud", 0) > 0:
            gross = res["total_revenue_aud"]
            yearly_revenues[year] = {
                "gross_arbitrage": round(gross),
                "trading_days": res.get("trading_days", 0),
                "per_mw": round(res.get("revenue_per_mw_year", 0)),
                "backtest_mode": res.get("backtest_mode", "optimized_hindsight"),
                "revenue_scope": res.get("revenue_scope", "physical_upper_bound"),
            }
            backtest_mode = (
                f"{res.get('backtest_mode', 'optimized_hindsight')} / "
                f"{res.get('revenue_scope', 'physical_upper_bound')}"
            )
            if res.get("annual_discharge_mwh"):
                total_discharge_history.append(res["annual_discharge_mwh"])

    if not yearly_revenues:
        return {"error": "No backtest data available for the specified region/years"}

    avg_gross = sum(v["gross_arbitrage"] for v in yearly_revenues.values()) / len(yearly_revenues)
    avg_annual_discharge_mwh = sum(total_discharge_history) / len(total_discharge_history) if total_discharge_history else capacity_mwh * 365 * 0.85

    baseline_arbitrage = avg_gross * params.revenue_capture_rate
    actual_est_annual_discharge = avg_annual_discharge_mwh * params.revenue_capture_rate

    if actual_fcas_mode == "auto" and params.region != "WEM":
        fcas_cache_key = _investment_fcas_cache_key(
            region=params.region,
            years=params.backtest_years,
            power_mw=params.power_mw,
        )
        cached_fcas = _fetch_or_compute_analysis_cache(
            scope=INVESTMENT_FCAS_CACHE_SCOPE,
            cache_key=fcas_cache_key,
            data_version=data_version,
            compute_fn=lambda: _run_investment_fcas_baseline(
                region=params.region,
                years=params.backtest_years,
                power_mw=params.power_mw,
            ),
        )
        baseline_fcas = cached_fcas.get("baseline_fcas", 0.0)
        fcas_baseline_source = cached_fcas.get("fcas_baseline_source", "manual_input_no_historical_fcas")
        if fcas_baseline_source != "historical_auto":
            actual_fcas_mode = "manual"
            baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
            fcas_baseline_source = "manual_input_no_historical_fcas"
            assumptions.append(
                "Historical FCAS coverage was incomplete for the selected NEM years, so the manual FCAS revenue input was used."
            )
    elif actual_fcas_mode == "auto" and params.region == "WEM":
        actual_fcas_mode = "manual"
        baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
        fcas_baseline_source = "manual_input_wem_fallback"
        assumptions.append(
            "WEM investment model keeps FCAS revenue on manual input until full historical ESS coverage is available."
        )
    else:
        baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
        fcas_baseline_source = "manual_input"

    baseline_capacity = params.capacity_payment_per_mw_year * params.power_mw
    baseline_total = baseline_arbitrage + baseline_fcas + baseline_capacity

    total_capex = (params.capex_per_kwh * capacity_mwh * 1000) + params.grid_connection_cost
    annual_fixed_om = params.fixed_om_per_mw_year * params.power_mw + params.land_lease_per_year
    annual_var_om = params.variable_om_per_mwh * actual_est_annual_discharge

    effective_degradation_rate = max(params.degradation_rate, 0.0)

    cash_flows = []
    cumulative = -total_capex
    payback_year = None

    cash_flows.append({
        "year": 0,
        "revenue": 0,
        "opex": 0,
        "net_cash_flow": round(-total_capex),
        "cumulative": round(-total_capex),
        "degradation_factor": 1.0,
    })

    for yr in range(1, params.project_life_years + 1):
        deg_factor = (1 - effective_degradation_rate) ** (yr - 1)
        rev_arbitrage = baseline_arbitrage * deg_factor
        rev_fcas = baseline_fcas * deg_factor
        rev_capacity = baseline_capacity
        total_rev = rev_arbitrage + rev_fcas + rev_capacity
        total_opex = annual_fixed_om + (annual_var_om * deg_factor)
        net = total_rev - total_opex
        cumulative += net

        if payback_year is None and cumulative >= 0:
            payback_year = yr

        cash_flows.append({
            "year": yr,
            "revenue": round(total_rev),
            "revenue_arbitrage": round(rev_arbitrage),
            "revenue_fcas": round(rev_fcas),
            "revenue_capacity": round(rev_capacity),
            "opex": round(total_opex),
            "net_cash_flow": round(net),
            "cumulative": round(cumulative),
            "degradation_factor": round(deg_factor, 4),
        })

    cf_list = [cf["net_cash_flow"] for cf in cash_flows]
    npv = sum(cf / (1 + params.discount_rate) ** i for i, cf in enumerate(cf_list))
    irr = _compute_irr(cf_list)
    total_net = sum(cf_list[1:])
    roi = total_net / total_capex if total_capex > 0 else 0

    return {
        "backtest": yearly_revenues,
        "backtest_mode": backtest_mode,
        "effective_degradation_rate": round(effective_degradation_rate, 4),
        "fcas_baseline_source": fcas_baseline_source,
        "assumptions": assumptions,
        "params": {
            "region": params.region,
            "power_mw": params.power_mw,
            "duration_hours": params.duration_hours,
            "capacity_mwh": capacity_mwh,
            "total_capex": round(total_capex),
            "capex_per_kwh": params.capex_per_kwh,
            "revenue_capture_rate": params.revenue_capture_rate,
            "project_life_years": params.project_life_years,
            "discount_rate": params.discount_rate,
            "degradation_rate": params.degradation_rate,
            "fcas_revenue_mode": actual_fcas_mode,
        },
        "baseline_revenue": {
            "arbitrage": round(baseline_arbitrage),
            "fcas": round(baseline_fcas),
            "capacity": round(baseline_capacity),
            "total": round(baseline_total),
            "per_mw": round(baseline_total / params.power_mw),
        },
        "metrics": {
            "npv": round(npv),
            "irr": round(irr * 100, 2) if irr is not None else None,
            "payback_years": payback_year,
            "roi_pct": round(roi * 100, 1),
            "total_capex": round(total_capex),
        },
        "cash_flows": cash_flows,
    }


@app.post("/api/investment-analysis")
def investment_analysis(params: InvestmentParams):
    """
    Compute BESS investment cash flow analysis:
    1. Backtest historical arbitrage revenue
    2. Project future revenue with degradation
    3. Calculate NPV, IRR, payback period
    """
    try:
        capacity_mwh = params.power_mw * params.duration_hours
        data_version = _analysis_data_version()
        response_cache_key = _investment_response_cache_key(params, capacity_mwh)
        redis_cache_payload = {
            "response_cache_key": response_cache_key,
            "data_version": data_version,
        }
        redis_cached_response = _fetch_response_cache(
            INVESTMENT_RESPONSE_REDIS_SCOPE,
            redis_cache_payload,
            normalize_fn=_normalize_cached_investment_response,
        )
        if redis_cached_response is not None:
            return redis_cached_response
        cached_response = db.fetch_analysis_cache(
            scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
            cache_key=response_cache_key,
            data_version=data_version,
        )
        if cached_response is not None:
            _store_response_cache(
                INVESTMENT_RESPONSE_REDIS_SCOPE,
                redis_cache_payload,
                cached_response,
                INVESTMENT_RESPONSE_CACHE_TTL_SECONDS,
            )
            return _normalize_cached_investment_response(cached_response)
        response = _fetch_or_compute_analysis_cache(
            scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
            cache_key=response_cache_key,
            data_version=data_version,
            compute_fn=lambda: _compute_investment_analysis_response(
                params,
                capacity_mwh=capacity_mwh,
                data_version=data_version,
            ),
        )
        _store_response_cache(
            INVESTMENT_RESPONSE_REDIS_SCOPE,
            redis_cache_payload,
            response,
            INVESTMENT_RESPONSE_CACHE_TTL_SECONDS,
        )
        return _normalize_cached_investment_response(response)

        actual_fcas_mode = params.fcas_revenue_mode or ("manual" if params.region == "WEM" else "auto")

        # --- Step 1: Backtest arbitrage revenue per year ---
        import bess_backtest
        yearly_revenues = {}
        total_discharge_history = []
        backtest_mode = "optimized_hindsight / physical_upper_bound"
        storage_config = {
            "duration_hours": params.duration_hours,
            "power_mw": params.power_mw,
            "capacity_mwh": capacity_mwh,
        }
        assumptions = [
            "Arbitrage baseline is derived from an optimized hindsight backtest and should be treated as a physical upper bound, not realized dispatch revenue.",
            f"Revenue capture rate ({params.revenue_capture_rate:.0%}) converts the backtest upper bound into an implementable arbitrage baseline.",
            "Capacity payment remains a manual user input.",
        ]
        for year in params.backtest_years:
            backtest_cache_key = _investment_backtest_cache_key(
                region=params.region,
                year=year,
                power_mw=params.power_mw,
                duration_hours=params.duration_hours,
                capacity_mwh=capacity_mwh,
                round_trip_efficiency=params.round_trip_efficiency,
            )
            res = db.fetch_analysis_cache(
                scope=INVESTMENT_BACKTEST_CACHE_SCOPE,
                cache_key=backtest_cache_key,
                data_version=data_version,
            )
            if res is None:
                with db.get_connection() as conn:
                    res = bess_backtest.backtest_arbitrage(conn, params.region, year, storage_config)
                db.upsert_analysis_cache(
                    scope=INVESTMENT_BACKTEST_CACHE_SCOPE,
                    cache_key=backtest_cache_key,
                    data_version=data_version,
                    response_payload=res or {},
                )

            if res and res.get("total_revenue_aud", 0) > 0:
                gross = res["total_revenue_aud"]
                yearly_revenues[year] = {
                    "gross_arbitrage": round(gross),
                    "trading_days": res.get("trading_days", 0),
                    "per_mw": round(res.get("revenue_per_mw_year", 0)),
                    "backtest_mode": res.get("backtest_mode", "optimized_hindsight"),
                    "revenue_scope": res.get("revenue_scope", "physical_upper_bound"),
                }
                backtest_mode = (
                    f"{res.get('backtest_mode', 'optimized_hindsight')} / "
                    f"{res.get('revenue_scope', 'physical_upper_bound')}"
                )
                if res.get("annual_discharge_mwh"):
                    total_discharge_history.append(res["annual_discharge_mwh"])

        if not yearly_revenues:
            return {"error": "No backtest data available for the specified region/years"}

        # --- Step 2: Compute baseline annual revenue ---
        avg_gross = sum(v["gross_arbitrage"] for v in yearly_revenues.values()) / len(yearly_revenues)
        avg_annual_discharge_mwh = sum(total_discharge_history) / len(total_discharge_history) if total_discharge_history else capacity_mwh * 365 * 0.85
        
        baseline_arbitrage = avg_gross * params.revenue_capture_rate
        actual_est_annual_discharge = avg_annual_discharge_mwh * params.revenue_capture_rate

        if actual_fcas_mode == "auto" and params.region != "WEM":
            fcas_cache_key = _investment_fcas_cache_key(
                region=params.region,
                years=params.backtest_years,
                power_mw=params.power_mw,
            )
            cached_fcas = db.fetch_analysis_cache(
                scope=INVESTMENT_FCAS_CACHE_SCOPE,
                cache_key=fcas_cache_key,
                data_version=data_version,
            )
            if cached_fcas is None:
                with db.get_connection() as conn:
                    baseline_fcas, fcas_baseline_source = _estimate_nem_fcas_baseline(
                        conn,
                        params.region,
                        params.backtest_years,
                        params.power_mw,
                    )
                cached_fcas = {
                    "baseline_fcas": baseline_fcas,
                    "fcas_baseline_source": fcas_baseline_source,
                }
                db.upsert_analysis_cache(
                    scope=INVESTMENT_FCAS_CACHE_SCOPE,
                    cache_key=fcas_cache_key,
                    data_version=data_version,
                    response_payload=cached_fcas,
                )
            baseline_fcas = cached_fcas.get("baseline_fcas", 0.0)
            fcas_baseline_source = cached_fcas.get("fcas_baseline_source", "manual_input_no_historical_fcas")
            if fcas_baseline_source != "historical_auto":
                actual_fcas_mode = "manual"
                baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
                fcas_baseline_source = "manual_input_no_historical_fcas"
                assumptions.append(
                    "Historical FCAS coverage was incomplete for the selected NEM years, so the manual FCAS revenue input was used."
                )
        elif actual_fcas_mode == "auto" and params.region == "WEM":
            actual_fcas_mode = "manual"
            baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
            fcas_baseline_source = "manual_input_wem_fallback"
            assumptions.append(
                "WEM investment model keeps FCAS revenue on manual input until full historical ESS coverage is available."
            )
        else:
            baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
            fcas_baseline_source = "manual_input"

        baseline_capacity = params.capacity_payment_per_mw_year * params.power_mw
        baseline_total = baseline_arbitrage + baseline_fcas + baseline_capacity

        # --- Step 3: Build cash flow model ---
        total_capex = (params.capex_per_kwh * capacity_mwh * 1000) + params.grid_connection_cost
        annual_fixed_om = params.fixed_om_per_mw_year * params.power_mw + params.land_lease_per_year
        annual_var_om = params.variable_om_per_mwh * actual_est_annual_discharge

        # 双因子寿命衰减模型 (Dual-factor Degradation Model: Calendar + Cycle)
        effective_degradation_rate = max(params.degradation_rate, 0.0)

        cash_flows = []
        cumulative = -total_capex
        payback_year = None

        # Year 0
        cash_flows.append({
            "year": 0,
            "revenue": 0,
            "opex": 0,
            "net_cash_flow": round(-total_capex),
            "cumulative": round(-total_capex),
            "degradation_factor": 1.0,
        })

        for yr in range(1, params.project_life_years + 1):
            deg_factor = (1 - effective_degradation_rate) ** (yr - 1)

            # Revenue degrades with battery capacity
            rev_arbitrage = baseline_arbitrage * deg_factor
            rev_fcas = baseline_fcas * deg_factor
            rev_capacity = baseline_capacity  # capacity payments don't degrade
            total_rev = rev_arbitrage + rev_fcas + rev_capacity

            # OpEx
            total_opex = annual_fixed_om + (annual_var_om * deg_factor)

            net = total_rev - total_opex
            cumulative += net

            if payback_year is None and cumulative >= 0:
                payback_year = yr

            cash_flows.append({
                "year": yr,
                "revenue": round(total_rev),
                "revenue_arbitrage": round(rev_arbitrage),
                "revenue_fcas": round(rev_fcas),
                "revenue_capacity": round(rev_capacity),
                "opex": round(total_opex),
                "net_cash_flow": round(net),
                "cumulative": round(cumulative),
                "degradation_factor": round(deg_factor, 4),
            })

        # --- Step 4: NPV & IRR ---
        cf_list = [cf["net_cash_flow"] for cf in cash_flows]
        npv = sum(cf / (1 + params.discount_rate) ** i for i, cf in enumerate(cf_list))

        # IRR via bisection
        irr = _compute_irr(cf_list)

        # ROI
        total_net = sum(cf_list[1:])
        roi = total_net / total_capex if total_capex > 0 else 0

        response = {
            "backtest": yearly_revenues,
            "backtest_mode": backtest_mode,
            "effective_degradation_rate": round(effective_degradation_rate, 4),
            "fcas_baseline_source": fcas_baseline_source,
            "assumptions": assumptions,
            "params": {
                "region": params.region,
                "power_mw": params.power_mw,
                "duration_hours": params.duration_hours,
                "capacity_mwh": capacity_mwh,
                "total_capex": round(total_capex),
                "capex_per_kwh": params.capex_per_kwh,
                "revenue_capture_rate": params.revenue_capture_rate,
                "project_life_years": params.project_life_years,
                "discount_rate": params.discount_rate,
                "degradation_rate": params.degradation_rate,
                "fcas_revenue_mode": actual_fcas_mode,
            },
            "baseline_revenue": {
                "arbitrage": round(baseline_arbitrage),
                "fcas": round(baseline_fcas),
                "capacity": round(baseline_capacity),
                "total": round(baseline_total),
                "per_mw": round(baseline_total / params.power_mw),
            },
            "metrics": {
                "npv": round(npv),
                "irr": round(irr * 100, 2) if irr is not None else None,
                "payback_years": payback_year,
                "roi_pct": round(roi * 100, 1),
                "total_capex": round(total_capex),
            },
            "cash_flows": cash_flows,
        }
        db.upsert_analysis_cache(
            scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
            cache_key=response_cache_key,
            data_version=data_version,
            response_payload=response,
        )
        return response

    except Exception as e:
        logger.error(f"Investment analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _compute_irr(cash_flows, tol=1e-6, max_iter=1000):
    """Compute IRR using bisection method."""
    if not cash_flows or cash_flows[0] >= 0:
        return None
    
    low, high = -0.5, 5.0
    
    for _ in range(max_iter):
        mid = (low + high) / 2
        npv = sum(cf / (1 + mid) ** i for i, cf in enumerate(cash_flows))
        
        if abs(npv) < tol:
            return mid
        if npv > 0:
            low = mid
        else:
            high = mid
    
    return (low + high) / 2


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8085)
