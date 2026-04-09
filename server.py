from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uvicorn
from contextlib import asynccontextmanager
import logging
from typing import Optional
import datetime
import subprocess
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import DatabaseManager
from network_fees import get_default_fee, get_window_sizes, get_all_fees, get_settlement_interval
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "aemo_data.db"
db = DatabaseManager(DB_PATH)

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

def run_sync_scrapers():
    """Background task to run scrapers and update the database."""
    try:
        logger.info("Starting Background Data Syncing Tasks...")
        # WEM and NEM Sync: Incremental (Last 14 days)
        two_weeks_ago = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"Running WEM Scraper from {two_weeks_ago} to {today}...")
        subprocess.run(["python", "aemo_wem_scraper.py", "--start", two_weeks_ago, "--end", today], check=True)
        
        logger.info("Running NEM Scraper...")
        start_month = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime('%Y-%m')
        end_month = datetime.datetime.now().strftime('%Y-%m')
        subprocess.run(["python", "aemo_nem_scraper.py", "--start", start_month, "--end", end_month, "--fcas"], check=True)

        
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
    table_name = f"trading_price_{year}"
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data available for year {year}")

            # Define the filter criteria
            where_clause = "region_id = ?"
            params = [region]
            
            # Temporal filters
            if month and len(month) == 2:
                where_clause += " AND settlement_date LIKE ?"
                params.append(f"{year}-{month}-%")
            elif quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
                q_map = {'Q1': "('01','02','03')", 'Q2': "('04','05','06')", 'Q3': "('07','08','09')", 'Q4': "('10','11','12')"}
                where_clause += f" AND substr(settlement_date, 6, 2) IN {q_map[quarter]}"
                
            if day_type == 'WEEKDAY':
                where_clause += " AND CAST(strftime('%w', substr(settlement_date, 1, 19)) AS INTEGER) IN (1, 2, 3, 4, 5)"
            elif day_type == 'WEEKEND':
                where_clause += " AND CAST(strftime('%w', substr(settlement_date, 1, 19)) AS INTEGER) IN (0, 6)"

            # Get total count for the region and applied filters
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", tuple(params))
            total_rows = cursor.fetchone()[0]
            
            if total_rows == 0:
                return {
                    "region": region, "year": year, "month": month, "total_points": 0, "returned_points": 0,
                    "stats": {"min": 0, "max": 0, "avg": 0},
                    "advanced_stats": {"neg_ratio": 0, "neg_avg": 0, "neg_min": 0, "pos_avg": 0, "pos_max": 0, "days_below_100": 0, "days_above_300": 0},
                    "hourly_distribution": [], "data": []
                }

            # Sampling step calculation
            sample_step = 1
            if total_rows > limit:
                sample_step = total_rows // limit

            # Fetch the time-series data using Peak-Preserving Envelope Sampling (LTTB-like approximation)
            if sample_step > 1:
                query_data = f"""
                    WITH Ranked AS (
                        SELECT settlement_date, rrp_aud_mwh,
                               ((ROW_NUMBER() OVER (ORDER BY settlement_date ASC) - 1) / {sample_step}) as bucket_id
                        FROM {table_name}
                        WHERE {where_clause}
                    )
                    SELECT 
                        MIN(settlement_date) as bucket_start,
                        MAX(rrp_aud_mwh) as max_val,
                        MIN(rrp_aud_mwh) as min_val
                    FROM Ranked
                    GROUP BY bucket_id
                    ORDER BY bucket_id ASC
                """
            else:
                query_data = f"""
                    SELECT settlement_date, rrp_aud_mwh, rrp_aud_mwh
                    FROM {table_name}
                    WHERE {where_clause}
                    ORDER BY settlement_date ASC
                """
            
            cursor.execute(query_data, tuple(params))
            rows = cursor.fetchall()
            
            # Format output: generate envelope points to ensure UI completely respects absolute peaks
            data = []
            if sample_step > 1:
                for r in rows:
                    data.append({"time": r[0], "price": round(r[1], 2)}) # Max
                    if round(r[1], 2) != round(r[2], 2):
                        data.append({"time": r[0], "price": round(r[2], 2)}) # Min (to draw vertical envelope stroke)
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
            
            return {
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
    network_fee: Optional[float] = Query(None, description="Override network fee ($/MWh). If omitted, uses default for region.")
):
    """
    Sliding-window peak/trough analysis with network fee integration.
    Returns peak/trough averages for 1h/2h/4h/6h windows and spread calculations.
    """
    table_name = f"trading_price_{year}"
    fee = network_fee if network_fee is not None else get_default_fee(region)
    windows = get_window_sizes(region)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check table exists
            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

            # Fetch all data for this year+region, ordered by time
            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
                f"WHERE region_id = ? ORDER BY settlement_date ASC",
                (region,)
            )
            rows = cursor.fetchall()

            if not rows:
                return {
                    "region": region, "year": year, "aggregation": aggregation,
                    "network_fee": fee, "data": [], "summary": {}
                }

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

            return {
                "region": region,
                "year": year,
                "aggregation": aggregation,
                "network_fee": fee,
                "data": aggregated,
                "summary": summary
            }

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
    table_name = f"trading_price_{year}"
    try:
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

            return {"region": region, "year": year, "month": month, "hourly": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hourly profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================
# FCAS (Frequency Control Ancillary Services) Analysis
# ============================================================

FCAS_SERVICES = {
    "raise6sec": "Raise 6 Sec",
    "raise60sec": "Raise 60 Sec",
    "raise5min": "Raise 5 Min",
    "raisereg": "Raise Reg",
    "lower6sec": "Lower 6 Sec",
    "lower60sec": "Lower 60 Sec",
    "lower5min": "Lower 5 Min",
    "lowerreg": "Lower Reg",
}

FCAS_COLUMNS = list(f"{k}_rrp" for k in FCAS_SERVICES.keys())


@app.get("/api/fcas-analysis")
def get_fcas_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1)"),
    aggregation: str = Query("daily", description="Aggregation: daily, weekly, monthly"),
    capacity_mw: float = Query(100, description="Battery capacity in MW for revenue estimation"),
):
    """
    FCAS revenue analysis endpoint.
    Returns per-service average prices, revenue estimates, hourly distribution,
    and time series data for charting.
    """
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
                return {
                    "region": region, "year": year, "has_fcas_data": False,
                    "message": "No FCAS data available. Run scraper with --fcas flag.",
                    "data": [], "summary": {}, "hourly": [], "service_breakdown": []
                }

            # Check if there's actually non-null FCAS data
            check_query = f"SELECT COUNT(*) FROM {table_name} WHERE region_id = ? AND {available_fcas[0]} IS NOT NULL"
            cursor.execute(check_query, (region,))
            fcas_count = cursor.fetchone()[0]

            if fcas_count == 0:
                return {
                    "region": region, "year": year, "has_fcas_data": False,
                    "message": "FCAS columns exist but no data yet. Re-sync with --fcas flag.",
                    "data": [], "summary": {}, "hourly": [], "service_breakdown": []
                }

            # 1. Overall service breakdown: average price per FCAS service
            avg_selects = ", ".join(
                f"AVG({col}) as avg_{col}" for col in available_fcas
            )
            max_selects = ", ".join(
                f"MAX({col}) as max_{col}" for col in available_fcas
            )
            cursor.execute(
                f"SELECT {avg_selects}, {max_selects}, COUNT(*) as total_intervals "
                f"FROM {table_name} WHERE region_id = ? AND {available_fcas[0]} IS NOT NULL",
                (region,)
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
                WHERE region_id = ? AND {available_fcas[0]} IS NOT NULL
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
            """
            cursor.execute(hourly_query, (region,))
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
                WHERE region_id = ? AND {available_fcas[0]} IS NOT NULL
                GROUP BY period
                ORDER BY period ASC
            """
            cursor.execute(ts_query, (region,))
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

            return {
                "region": region,
                "year": year,
                "has_fcas_data": True,
                "aggregation": aggregation,
                "summary": summary,
                "service_breakdown": service_breakdown,
                "hourly": hourly,
                "data": ts_data,
            }

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
    capacity_payment_per_mw_year: float = 0  # WEM RCM or CIS
    # Backtest years to use for projection
    backtest_years: List[int] = [2024, 2025]


@app.post("/api/investment-analysis")
def investment_analysis(params: InvestmentParams):
    """
    Compute BESS investment cash flow analysis:
    1. Backtest historical arbitrage revenue
    2. Project future revenue with degradation
    3. Calculate NPV, IRR, payback period
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        capacity_mwh = params.power_mw * params.duration_hours
        intervals_per_hour = 12  # 5-min dispatch
        charge_intervals = int(params.duration_hours * intervals_per_hour)

        # --- Step 1: Backtest arbitrage revenue per year ---
        yearly_revenues = {}
        for year in params.backtest_years:
            table = f"trading_price_{year}"
            try:
                rows = conn.execute(
                    f"SELECT settlement_date, rrp_aud_mwh FROM {table} "
                    f"WHERE region_id = ? ORDER BY settlement_date",
                    (params.region,)
                ).fetchall()
            except Exception:
                continue

            if not rows:
                continue

            daily_prices = defaultdict(list)
            for ts, price in rows:
                daily_prices[ts[:10]].append(price)

            annual_revenue = 0
            trading_days = 0

            for day in sorted(daily_prices.keys()):
                prices = daily_prices[day]
                n = len(prices)
                if n < charge_intervals * 2:
                    continue

                # Find best charge window (lowest avg)
                best_charge_avg = float('inf')
                best_charge_start = 0
                for i in range(n - charge_intervals + 1):
                    avg = sum(prices[i:i + charge_intervals]) / charge_intervals
                    if avg < best_charge_avg:
                        best_charge_avg = avg
                        best_charge_start = i

                # Find best discharge window (highest avg, no overlap)
                best_discharge_avg = float('-inf')
                charge_end = best_charge_start + charge_intervals
                for i in range(n - charge_intervals + 1):
                    if i < charge_end and i + charge_intervals > best_charge_start:
                        continue
                    avg = sum(prices[i:i + charge_intervals]) / charge_intervals
                    if avg > best_discharge_avg:
                        best_discharge_avg = avg

                if best_discharge_avg == float('-inf'):
                    continue

                charge_cost = best_charge_avg * capacity_mwh
                discharge_income = best_discharge_avg * capacity_mwh * params.round_trip_efficiency
                net = discharge_income - charge_cost

                if net > 0:
                    annual_revenue += net
                    trading_days += 1

            if trading_days > 0:
                yearly_revenues[year] = {
                    "gross_arbitrage": round(annual_revenue),
                    "trading_days": trading_days,
                    "per_mw": round(annual_revenue / params.power_mw),
                }

        conn.close()

        if not yearly_revenues:
            return {"error": "No backtest data available for the specified region/years"}

        # --- Step 2: Compute baseline annual revenue ---
        avg_gross = sum(v["gross_arbitrage"] for v in yearly_revenues.values()) / len(yearly_revenues)
        baseline_arbitrage = avg_gross * params.revenue_capture_rate
        baseline_fcas = params.fcas_revenue_per_mw_year * params.power_mw
        baseline_capacity = params.capacity_payment_per_mw_year * params.power_mw
        baseline_total = baseline_arbitrage + baseline_fcas + baseline_capacity

        # --- Step 3: Build cash flow model ---
        total_capex = (params.capex_per_kwh * capacity_mwh * 1000) + params.grid_connection_cost
        annual_fixed_om = params.fixed_om_per_mw_year * params.power_mw + params.land_lease_per_year
        # Estimate annual discharge MWh for variable O&M
        est_annual_discharge_mwh = capacity_mwh * 365 * 0.85  # ~85% availability
        annual_var_om = params.variable_om_per_mwh * est_annual_discharge_mwh

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
            deg_factor = (1 - params.degradation_rate) ** (yr - 1)

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

        return {
            "backtest": yearly_revenues,
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
