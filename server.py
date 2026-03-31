from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uvicorn
from contextlib import asynccontextmanager
import logging
from typing import Optional

from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "aemo_data.db"
db = DatabaseManager(DB_PATH)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting AEMO NEM API server...")
    yield
    # Shutdown actions
    logger.info("Shutting down AEMO NEM API server...")

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
    """Returns database summary statistics (tables, time ranges, record counts)"""
    try:
        return db.get_summary()
    except Exception as e:
        logger.error(f"Error fetching summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8085, reload=True)
