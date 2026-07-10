"""WEM market module API routes.

Provides endpoints for WEM-specific analysis modules:
- Capacity Credits analysis
- STEM/Balancing spread analysis
- Five-minute settlement impact analysis
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from deps import get_db
from sql_safe import safe_table_name, trading_price_table

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wem", tags=["WEM Modules"])

# ---------------------------------------------------------------------------
# Historical capacity credit price data (approximate $/MW/year)
# Source: WEM Reserve Capacity Mechanism reports
# ---------------------------------------------------------------------------

HISTORICAL_CAPACITY_CREDIT_PRICES: list[dict] = [
    {"year": 2020, "price_per_mw": 80_000},
    {"year": 2021, "price_per_mw": 100_000},
    {"year": 2022, "price_per_mw": 120_000},
    {"year": 2023, "price_per_mw": 140_000},
    {"year": 2024, "price_per_mw": 150_000},
    {"year": 2025, "price_per_mw": 155_000},
]

# Current capacity credit price (2024-25, approximately $150,000/MW/year)
CURRENT_CREDIT_PRICE = 150_000

# Default energy revenue estimate for WEM BESS ($/MW/year)
DEFAULT_ENERGY_REVENUE_PER_MW = 50_000


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CapacityCreditsResponse(BaseModel):
    """WEM 容量信用分析响应"""

    power_mw: float
    duration_hours: float
    eligibility_coefficient: float
    credit_price_current: float  # $/MW/year
    annual_capacity_revenue: float
    energy_revenue_estimate: float
    capacity_revenue_share_pct: float
    historical_prices: list[dict]  # [{year, price_per_mw}, ...]


class StemBalancingResponse(BaseModel):
    """STEM/Balancing 价差分析响应"""

    date_range: dict  # {start, end}
    spread_stats: dict  # {mean, median, p10, p90, std}
    hourly_pattern: list[dict]  # [{hour, avg_spread, count}, ...]
    theoretical_revenue: float
    unconstrained_revenue: float
    constraint_impact_pct: float
    data_window: Optional[dict] = None  # {start, end, days} — actual Balancing data coverage


class FiveMinSettlementResponse(BaseModel):
    """5 分钟结算影响分析响应"""

    data_mode: Literal["simulated", "actual"]
    volatility_30min: float
    volatility_5min: float
    volatility_change_pct: float
    revenue_change_pct: float
    spread_distribution_comparison: dict
    spike_capture_rate_comparison: dict


# ---------------------------------------------------------------------------
# Helper: Eligibility coefficient calculation
# ---------------------------------------------------------------------------


def calculate_eligibility_coefficient(duration_hours: float) -> float:
    """Calculate WEM capacity credit eligibility coefficient based on BESS duration.

    The coefficient reflects the proportion of nameplate capacity that qualifies
    for capacity credits under WEM rules. Longer duration systems receive higher
    coefficients as they can sustain output for longer peak demand periods.

    Uses linear interpolation between defined breakpoints:
      - 1h: 0.4
      - 2h: 0.6
      - 3h: 0.8
      - 4h+: 1.0

    For durations below 1h, linearly interpolates from 0.0 at 0h to 0.4 at 1h.

    Args:
        duration_hours: BESS energy duration in hours.

    Returns:
        Eligibility coefficient between 0.0 and 1.0.
    """
    if duration_hours >= 4:
        return 1.0

    # Breakpoints for linear interpolation
    breakpoints = [(0, 0.0), (1, 0.4), (2, 0.6), (3, 0.8), (4, 1.0)]

    # Find the segment containing duration_hours
    for i in range(len(breakpoints) - 1):
        lower_h, lower_coeff = breakpoints[i]
        upper_h, upper_coeff = breakpoints[i + 1]
        if lower_h <= duration_hours <= upper_h:
            # Linear interpolation
            fraction = (duration_hours - lower_h) / (upper_h - lower_h)
            return lower_coeff + fraction * (upper_coeff - lower_coeff)

    # Fallback (should not reach here given duration_hours > 0)
    return 1.0


# ---------------------------------------------------------------------------
# Route: GET /api/v1/wem/capacity-credits
# ---------------------------------------------------------------------------


@router.get("/capacity-credits")
async def get_capacity_credits(
    power_mw: float = Query(default=100, gt=0, description="BESS power capacity in MW"),
    duration_hours: float = Query(default=4, gt=0, description="BESS energy duration in hours"),
) -> CapacityCreditsResponse:
    """计算 WEM 容量信用收入。

    基于 BESS 功率和时长参数，计算容量信用资格系数、年度容量信用收入，
    并与能量市场收入进行对比分析。
    """
    # Calculate eligibility coefficient
    eligibility_coefficient = calculate_eligibility_coefficient(duration_hours)

    # Current credit price
    credit_price_current = CURRENT_CREDIT_PRICE

    # Annual capacity revenue = power_mw * eligibility_coefficient * credit_price_current
    annual_capacity_revenue = power_mw * eligibility_coefficient * credit_price_current

    # Energy revenue estimate: use $50,000/MW/year as default baseline
    energy_revenue_estimate = power_mw * DEFAULT_ENERGY_REVENUE_PER_MW

    # Capacity revenue share percentage
    total_revenue = annual_capacity_revenue + energy_revenue_estimate
    if total_revenue > 0:
        capacity_revenue_share_pct = (annual_capacity_revenue / total_revenue) * 100
    else:
        capacity_revenue_share_pct = 0.0

    return CapacityCreditsResponse(
        power_mw=power_mw,
        duration_hours=duration_hours,
        eligibility_coefficient=eligibility_coefficient,
        credit_price_current=credit_price_current,
        annual_capacity_revenue=annual_capacity_revenue,
        energy_revenue_estimate=energy_revenue_estimate,
        capacity_revenue_share_pct=round(capacity_revenue_share_pct, 2),
        historical_prices=HISTORICAL_CAPACITY_CREDIT_PRICES,
    )


# ---------------------------------------------------------------------------
# Route: GET /api/v1/wem/stem-balancing
# ---------------------------------------------------------------------------

# WEM interval durations
_WEM_STEM_INTERVAL_HOURS = 0.5  # 30-minute STEM settlement intervals
_WEM_BALANCING_INTERVAL_MINUTES = 5  # 5-minute ESS dispatch intervals
_WEM_BALANCING_INTERVAL_HOURS = _WEM_BALANCING_INTERVAL_MINUTES / 60.0
_BESS_ROUND_TRIP_EFFICIENCY = 0.87


def _parse_date_safe(date_str: str) -> datetime | None:
    """Parse a YYYY-MM-DD date string, returning None on failure."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _fetch_stem_prices(start_date: str, end_date: str) -> list[tuple[str, float]]:
    """Fetch WEM STEM (Reference Trading Price) data for the date range.

    Returns list of (timestamp, price) tuples from trading_price_{year} tables.
    STEM prices are 30-minute settlement intervals.
    """
    db = get_db()
    start_dt = _parse_date_safe(start_date)
    end_dt = _parse_date_safe(end_date)
    if not start_dt or not end_dt:
        return []

    results: list[tuple[str, float]] = []

    # Query each year table that overlaps with the date range
    for year in range(start_dt.year, end_dt.year + 1):
        table_name = trading_price_table(year)
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                # Check table exists
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                    (table_name,),
                )
                if not cursor.fetchone():
                    continue

                cursor.execute(
                    f"""
                    SELECT settlement_date, rrp_aud_mwh
                    FROM {table_name}
                    WHERE region_id = 'WEM'
                      AND settlement_date >= ?
                      AND settlement_date <= ?
                      AND rrp_aud_mwh IS NOT NULL
                    ORDER BY settlement_date ASC
                    """,
                    (start_date, end_date + " 23:59:59"),
                )
                rows = cursor.fetchall()
                results.extend(rows)
        except Exception as exc:
            logger.warning(f"Failed to fetch STEM prices from {table_name}: {exc}")

    return results


def _fetch_balancing_prices(start_date: str, end_date: str) -> list[tuple[str, float]]:
    """Fetch WEM Balancing (ESS dispatch) energy prices for the date range.

    Returns list of (dispatch_interval, energy_price) tuples from wem_ess_market_price.
    Balancing prices are 5-minute dispatch intervals.
    """
    db = get_db()
    try:
        with db.get_connection() as conn:
            db.ensure_wem_ess_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT dispatch_interval, energy_price
                FROM {db.WEM_ESS_MARKET_TABLE}
                WHERE dispatch_interval >= ?
                  AND dispatch_interval <= ?
                  AND energy_price IS NOT NULL
                ORDER BY dispatch_interval ASC
                """,
                (start_date, end_date + " 23:59:59"),
            )
            return cursor.fetchall()
    except Exception as exc:
        logger.warning(f"Failed to fetch Balancing prices: {exc}")
        return []


def _get_balancing_data_range() -> tuple[str, str] | None:
    """Query the actual data range available in wem_ess_market_price.

    Returns (min_date, max_date) as 'YYYY-MM-DD' strings, or None if empty.
    """
    db = get_db()
    try:
        with db.get_connection() as conn:
            db.ensure_wem_ess_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT MIN(dispatch_interval), MAX(dispatch_interval)
                FROM {db.WEM_ESS_MARKET_TABLE}
                WHERE energy_price IS NOT NULL
                """
            )
            row = cursor.fetchone()
            if row and row[0] and row[1]:
                return row[0][:10], row[1][:10]  # 'YYYY-MM-DD'
    except Exception as exc:
        logger.warning(f"Failed to query Balancing data range: {exc}")
    return None


def _align_stem_balancing_prices(
    stem_prices: list[tuple[str, float]],
    balancing_prices: list[tuple[str, float]],
) -> list[dict]:
    """Align STEM and Balancing prices at 30-minute intervals.

    For each 30-minute STEM interval, averages the 5-minute Balancing prices
    that fall within that interval. Returns aligned records with both prices.

    Returns:
        List of dicts: [{timestamp, stem_price, balancing_price, spread}, ...]
    """
    if not stem_prices or not balancing_prices:
        return []

    # Build a lookup: truncate balancing timestamps to 30-min buckets
    # and average the 5-min prices within each bucket
    balancing_by_bucket: dict[str, list[float]] = {}
    for ts, price in balancing_prices:
        # Parse timestamp and truncate to 30-min boundary
        try:
            dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(ts[:19])
            except (ValueError, TypeError):
                continue
        # Truncate to 30-min bucket
        minute_bucket = (dt.minute // 30) * 30
        bucket_dt = dt.replace(minute=minute_bucket, second=0, microsecond=0)
        bucket_key = bucket_dt.strftime("%Y-%m-%d %H:%M:%S")
        if bucket_key not in balancing_by_bucket:
            balancing_by_bucket[bucket_key] = []
        balancing_by_bucket[bucket_key].append(price)

    # Average balancing prices per bucket
    balancing_avg: dict[str, float] = {}
    for bucket_key, prices in balancing_by_bucket.items():
        balancing_avg[bucket_key] = sum(prices) / len(prices)

    # Align with STEM prices
    aligned: list[dict] = []
    for ts, stem_price in stem_prices:
        # Normalize STEM timestamp to match bucket format
        try:
            dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(ts[:19])
            except (ValueError, TypeError):
                continue
        bucket_key = dt.strftime("%Y-%m-%d %H:%M:%S")

        if bucket_key in balancing_avg:
            bal_price = balancing_avg[bucket_key]
            spread = bal_price - stem_price
            aligned.append({
                "timestamp": bucket_key,
                "hour": dt.hour,
                "stem_price": stem_price,
                "balancing_price": bal_price,
                "spread": spread,
            })

    return aligned


def _compute_spread_stats(spreads: list[float]) -> dict:
    """Compute spread statistics: mean, median, p10, p90, std."""
    if not spreads:
        return {"mean": 0.0, "median": 0.0, "p10": 0.0, "p90": 0.0, "std": 0.0}

    arr = np.array(spreads)
    return {
        "mean": round(float(np.mean(arr)), 4),
        "median": round(float(np.median(arr)), 4),
        "p10": round(float(np.percentile(arr, 10)), 4),
        "p90": round(float(np.percentile(arr, 90)), 4),
        "std": round(float(np.std(arr)), 4),
    }


def _compute_hourly_pattern(aligned_data: list[dict]) -> list[dict]:
    """Compute average spread and count by hour of day."""
    hourly: dict[int, list[float]] = {h: [] for h in range(24)}
    for record in aligned_data:
        hour = record["hour"]
        hourly[hour].append(record["spread"])

    pattern: list[dict] = []
    for hour in range(24):
        spreads = hourly[hour]
        if spreads:
            pattern.append({
                "hour": hour,
                "avg_spread": round(sum(spreads) / len(spreads), 4),
                "count": len(spreads),
            })
        else:
            pattern.append({"hour": hour, "avg_spread": 0.0, "count": 0})

    return pattern


def _compute_theoretical_revenue(
    aligned_data: list[dict],
    power_mw: float,
    duration_hours: float,
    interval_hours: float = _WEM_STEM_INTERVAL_HOURS,
) -> float:
    """Compute theoretical BESS arbitrage revenue from STEM/Balancing spreads.

    Constrained by BESS energy capacity: can only capture positive spreads
    up to the energy capacity limit per day (charge/discharge cycle).

    Strategy: For each day, sort positive spreads descending and capture
    the top intervals limited by energy capacity.

    Args:
        aligned_data: Aligned price records with spread values.
        power_mw: BESS power capacity (MW).
        duration_hours: BESS energy duration (hours).
        interval_hours: Duration of each interval (hours).

    Returns:
        Total theoretical revenue ($) considering BESS physical constraints.
    """
    if not aligned_data:
        return 0.0

    energy_mwh = power_mw * duration_hours
    max_intervals_per_cycle = int(duration_hours / interval_hours)

    # Group by day
    daily_data: dict[str, list[float]] = {}
    for record in aligned_data:
        day = record["timestamp"][:10]
        if day not in daily_data:
            daily_data[day] = []
        daily_data[day].append(record["spread"])

    total_revenue = 0.0
    for _day, spreads in daily_data.items():
        # Only consider positive spreads (profitable to buy STEM, sell Balancing)
        positive_spreads = sorted([s for s in spreads if s > 0], reverse=True)

        # Constrain by BESS capacity: can only discharge for max_intervals_per_cycle
        captured = positive_spreads[:max_intervals_per_cycle]

        # Revenue = spread * power_mw * interval_hours * efficiency
        day_revenue = sum(s * power_mw * interval_hours * _BESS_ROUND_TRIP_EFFICIENCY for s in captured)
        total_revenue += day_revenue

    return round(total_revenue, 2)


def _compute_unconstrained_revenue(
    aligned_data: list[dict],
    power_mw: float,
    interval_hours: float = _WEM_STEM_INTERVAL_HOURS,
) -> float:
    """Compute unconstrained revenue: sum of ALL positive spreads without capacity limit.

    This represents the theoretical maximum if the BESS had unlimited energy capacity.
    """
    if not aligned_data:
        return 0.0

    total_revenue = 0.0
    for record in aligned_data:
        if record["spread"] > 0:
            total_revenue += record["spread"] * power_mw * interval_hours * _BESS_ROUND_TRIP_EFFICIENCY

    return round(total_revenue, 2)


@router.get("/stem-balancing")
async def get_stem_balancing(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    power_mw: float = Query(default=100, gt=0, description="BESS power capacity in MW"),
    duration_hours: float = Query(default=4, gt=0, description="BESS energy duration in hours"),
) -> StemBalancingResponse:
    """分析 STEM/Balancing 价差套利机会。

    STEM 是 WEM 的日前市场（Short Term Energy Market），Balancing 是实时市场。
    价差 = Balancing 价格 - STEM 价格。正价差意味着实时价格高于日前价格。

    本端点计算价差统计、时段分布模式和理论套利收入（考虑 BESS 物理约束）。
    当数据不可用时返回零值结构化响应。

    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 12.5
    """
    # Validate date parameters
    start_dt = _parse_date_safe(start_date)
    end_dt = _parse_date_safe(end_date)

    if not start_dt or not end_dt:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_DATE_FORMAT",
                "message": "Date parameters must be in YYYY-MM-DD format",
                "suggested_action": "Provide valid dates, e.g. start_date=2024-01-01",
            },
        )

    if end_dt < start_dt:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_DATE_RANGE",
                "message": "end_date must be on or after start_date",
                "suggested_action": "Swap start_date and end_date values",
            },
        )

    # Fetch STEM and Balancing price data
    stem_prices = _fetch_stem_prices(start_date, end_date)
    balancing_prices = _fetch_balancing_prices(start_date, end_date)

    # --- Auto-detect Balancing data window (lazy) ---
    # Only query the actual data range if the requested range has no Balancing data.
    # This avoids an unnecessary DB round-trip on the happy path.
    data_window = None

    if not balancing_prices:
        balancing_range = _get_balancing_data_range()
        if balancing_range:
            bal_start, bal_end = balancing_range
            bw_days = (datetime.strptime(bal_end, "%Y-%m-%d") - datetime.strptime(bal_start, "%Y-%m-%d")).days + 1
            data_window = {"start": bal_start, "end": bal_end, "days": bw_days}

            logger.info(
                f"No Balancing data for {start_date}~{end_date}; "
                f"falling back to actual range {bal_start}~{bal_end}"
            )
            balancing_prices = _fetch_balancing_prices(bal_start, bal_end)
            # Also re-fetch STEM for the actual range so timestamps align
            stem_prices = _fetch_stem_prices(bal_start, bal_end)
    else:
        # Happy path: still report the data window for transparency
        balancing_range = _get_balancing_data_range()
        if balancing_range:
            bw_start, bw_end = balancing_range
            bw_days = (datetime.strptime(bw_end, "%Y-%m-%d") - datetime.strptime(bw_start, "%Y-%m-%d")).days + 1
            data_window = {"start": bw_start, "end": bw_end, "days": bw_days}

    # date_range always echoes the original request to preserve API contract.
    # data_window conveys actual Balancing data coverage.
    req_range = {"start": start_date, "end": end_date}

    # Handle data unavailability: return zeros with structured response
    if not stem_prices and not balancing_prices:
        logger.info(
            f"No STEM or Balancing data available for {start_date} to {end_date}"
        )
        return StemBalancingResponse(
            date_range=req_range,
            spread_stats={"mean": 0.0, "median": 0.0, "p10": 0.0, "p90": 0.0, "std": 0.0},
            hourly_pattern=[{"hour": h, "avg_spread": 0.0, "count": 0} for h in range(24)],
            theoretical_revenue=0.0,
            unconstrained_revenue=0.0,
            constraint_impact_pct=0.0,
            data_window=data_window,
        )

    if not stem_prices:
        logger.info(f"No STEM price data available for {start_date} to {end_date}")
        return StemBalancingResponse(
            date_range=req_range,
            spread_stats={"mean": 0.0, "median": 0.0, "p10": 0.0, "p90": 0.0, "std": 0.0},
            hourly_pattern=[{"hour": h, "avg_spread": 0.0, "count": 0} for h in range(24)],
            theoretical_revenue=0.0,
            unconstrained_revenue=0.0,
            constraint_impact_pct=0.0,
            data_window=data_window,
        )

    if not balancing_prices:
        logger.info(f"No Balancing price data available for {start_date} to {end_date}")
        return StemBalancingResponse(
            date_range=req_range,
            spread_stats={"mean": 0.0, "median": 0.0, "p10": 0.0, "p90": 0.0, "std": 0.0},
            hourly_pattern=[{"hour": h, "avg_spread": 0.0, "count": 0} for h in range(24)],
            theoretical_revenue=0.0,
            unconstrained_revenue=0.0,
            constraint_impact_pct=0.0,
            data_window=data_window,
        )

    # Align STEM and Balancing prices at 30-minute intervals
    aligned_data = _align_stem_balancing_prices(stem_prices, balancing_prices)

    if not aligned_data:
        logger.info(
            f"No overlapping STEM/Balancing data for {start_date} to {end_date}"
        )
        return StemBalancingResponse(
            date_range=req_range,
            spread_stats={"mean": 0.0, "median": 0.0, "p10": 0.0, "p90": 0.0, "std": 0.0},
            hourly_pattern=[{"hour": h, "avg_spread": 0.0, "count": 0} for h in range(24)],
            theoretical_revenue=0.0,
            unconstrained_revenue=0.0,
            constraint_impact_pct=0.0,
            data_window=data_window,
        )

    # Compute spread statistics
    spreads = [record["spread"] for record in aligned_data]
    spread_stats = _compute_spread_stats(spreads)

    # Compute hourly pattern
    hourly_pattern = _compute_hourly_pattern(aligned_data)

    # Compute theoretical revenue (constrained by BESS capacity)
    theoretical_revenue = _compute_theoretical_revenue(
        aligned_data, power_mw, duration_hours
    )

    # Compute unconstrained revenue (no capacity limit)
    unconstrained_revenue = _compute_unconstrained_revenue(
        aligned_data, power_mw
    )

    # Compute constraint impact percentage
    if unconstrained_revenue > 0:
        constraint_impact_pct = round(
            (unconstrained_revenue - theoretical_revenue) / unconstrained_revenue * 100,
            2,
        )
    else:
        constraint_impact_pct = 0.0

    return StemBalancingResponse(
        date_range=req_range,
        spread_stats=spread_stats,
        hourly_pattern=hourly_pattern,
        theoretical_revenue=theoretical_revenue,
        unconstrained_revenue=unconstrained_revenue,
        constraint_impact_pct=constraint_impact_pct,
        data_window=data_window,
    )


# ---------------------------------------------------------------------------
# Route: GET /api/v1/wem/five-min-settlement
# ---------------------------------------------------------------------------

# WEM 5-minute settlement transition constants
_INTRA_INTERVAL_VOLATILITY_FACTOR = 0.20  # 5-min noise std ≈ 20% of 30-min price
_SPIKE_THRESHOLD_AUD = 300.0  # Price spike threshold ($/MWh)
_SEED_BASE = 42  # Base seed for reproducibility


def _fetch_wem_prices_for_year(year: int) -> list[float]:
    """Fetch WEM 30-minute settlement prices for a given year.

    Returns a list of prices ($/MWh) ordered by settlement_date.
    """
    db = get_db()
    table_name = trading_price_table(year)
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,),
            )
            if not cursor.fetchone():
                return []
            cursor.execute(
                f"""
                SELECT rrp_aud_mwh
                FROM {table_name}
                WHERE region_id = 'WEM' AND rrp_aud_mwh IS NOT NULL
                ORDER BY settlement_date ASC
                """,
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception as exc:
        logger.warning(f"Failed to fetch WEM prices for {year}: {exc}")
        return []


def _check_actual_5min_data_available(year: int) -> bool:
    """Check if actual 5-minute settlement data exists for the given year.

    WEM is transitioning from 30-min to 5-min settlement. When actual 5-min
    data becomes available in the database, we prefer it over simulation.
    """
    db = get_db()
    # Convention: actual 5-min WEM data would be stored in a dedicated table
    table_name = safe_table_name(f"wem_5min_price_{year}")
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,),
            )
            if not cursor.fetchone():
                return False
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} LIMIT 1")
            count = cursor.fetchone()[0]
            return count > 0
    except Exception:
        return False


def _fetch_actual_5min_prices(year: int) -> list[float]:
    """Fetch actual 5-minute WEM prices if available."""
    db = get_db()
    table_name = safe_table_name(f"wem_5min_price_{year}")
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT price_aud_mwh
                FROM {table_name}
                WHERE price_aud_mwh IS NOT NULL
                ORDER BY settlement_date ASC
                """,
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception as exc:
        logger.warning(f"Failed to fetch actual 5-min WEM prices for {year}: {exc}")
        return []


def _simulate_5min_prices_from_30min(prices_30min: list[float], seed: int) -> list[float]:
    """Simulate 5-minute prices from 30-minute settlement data.

    For each 30-minute interval, generates 6 sub-intervals (5 min each) by:
    - Adding Gaussian noise scaled to typical intra-interval volatility
    - Preserving the 30-minute average (mean-reversion constraint)

    The noise standard deviation is approximately 15-25% of the absolute 30-min price,
    capped at a minimum to avoid degenerate cases near zero prices.
    """
    rng = np.random.default_rng(seed)
    prices_5min: list[float] = []

    for price_30min in prices_30min:
        # Noise std scales with price magnitude, bounded between 5 and 500 $/MWh
        noise_std = max(5.0, min(500.0, abs(price_30min) * _INTRA_INTERVAL_VOLATILITY_FACTOR))

        # Generate 6 sub-interval deviations
        raw_noise = rng.normal(0, noise_std, size=6)

        # Mean-center the noise to preserve the 30-min average
        raw_noise -= raw_noise.mean()

        # 5-min prices = 30-min base + mean-centered noise
        for deviation in raw_noise:
            prices_5min.append(price_30min + deviation)

    return prices_5min


def _calculate_price_return_volatility(prices: list[float]) -> float:
    """Calculate volatility as standard deviation of log price returns.

    Handles zero/negative prices by using absolute returns as fallback.
    """
    if len(prices) < 2:
        return 0.0

    arr = np.array(prices)

    # Use percentage returns for volatility calculation
    # Avoid division by zero: use absolute diff where price is near zero
    returns = []
    for i in range(1, len(arr)):
        if abs(arr[i - 1]) > 1.0:
            returns.append((arr[i] - arr[i - 1]) / abs(arr[i - 1]))
        else:
            # For near-zero prices, use absolute difference scaled by typical price
            returns.append((arr[i] - arr[i - 1]) / 100.0)

    if not returns:
        return 0.0

    return float(np.std(returns))


def _calculate_bess_arbitrage_revenue(
    prices: list[float],
    power_mw: float,
    duration_hours: float,
    interval_hours: float,
) -> float:
    """Estimate BESS arbitrage revenue using a simple price-threshold strategy.

    Strategy: charge during lowest-price intervals, discharge during highest-price
    intervals, subject to energy capacity and power constraints.

    Args:
        prices: Price series ($/MWh).
        power_mw: BESS power capacity (MW).
        duration_hours: BESS energy duration (hours).
        interval_hours: Duration of each price interval (hours).

    Returns:
        Estimated annual arbitrage revenue ($).
    """
    if not prices:
        return 0.0

    energy_mwh = power_mw * duration_hours
    intervals_per_cycle = int(duration_hours / interval_hours)  # intervals to fully charge/discharge
    efficiency = 0.87  # round-trip efficiency

    # Group prices by day
    intervals_per_day = int(24 / interval_hours)
    total_days = len(prices) // intervals_per_day

    total_revenue = 0.0

    for day_idx in range(total_days):
        day_start = day_idx * intervals_per_day
        day_end = day_start + intervals_per_day
        day_prices = prices[day_start:day_end]

        if len(day_prices) < intervals_per_cycle * 2:
            continue

        # Find best charge (lowest) and discharge (highest) windows
        sorted_prices = sorted(enumerate(day_prices), key=lambda x: x[1])

        # Charge at lowest prices
        charge_cost = sum(
            p * power_mw * interval_hours
            for _, p in sorted_prices[:intervals_per_cycle]
        )

        # Discharge at highest prices
        discharge_revenue = sum(
            p * power_mw * interval_hours * efficiency
            for _, p in sorted_prices[-intervals_per_cycle:]
        )

        daily_profit = discharge_revenue - charge_cost
        if daily_profit > 0:
            total_revenue += daily_profit

    return total_revenue


def _calculate_spike_capture_rate(
    prices: list[float],
    power_mw: float,
    duration_hours: float,
    interval_hours: float,
    threshold: float = _SPIKE_THRESHOLD_AUD,
) -> dict:
    """Calculate the fraction of price spikes a BESS can capture.

    A spike is defined as a price interval exceeding the threshold.
    Capture rate depends on how many consecutive spike intervals the BESS
    can serve given its energy capacity.

    Returns:
        Dict with total_spikes, captured_spikes, capture_rate.
    """
    if not prices:
        return {"total_spikes": 0, "captured_spikes": 0, "capture_rate": 0.0}

    # Identify spike intervals
    spike_indices = [i for i, p in enumerate(prices) if p >= threshold]
    total_spikes = len(spike_indices)

    if total_spikes == 0:
        return {"total_spikes": 0, "captured_spikes": 0, "capture_rate": 0.0}

    # BESS can discharge for (duration_hours / interval_hours) consecutive intervals
    max_discharge_intervals = int(duration_hours / interval_hours)

    # Group consecutive spikes into events
    captured = 0
    i = 0
    while i < len(spike_indices):
        # Start of a spike event - BESS can capture up to max_discharge_intervals
        event_start = i
        event_captured = 0
        while i < len(spike_indices) and event_captured < max_discharge_intervals:
            # Check if this spike is consecutive with the previous
            if i > event_start and spike_indices[i] - spike_indices[i - 1] > 1:
                break
            event_captured += 1
            i += 1
        captured += event_captured

        # Skip remaining spikes in this event that couldn't be captured
        while i < len(spike_indices) and (
            i == event_start or spike_indices[i] - spike_indices[i - 1] == 1
        ):
            i += 1

    capture_rate = captured / total_spikes if total_spikes > 0 else 0.0
    return {
        "total_spikes": total_spikes,
        "captured_spikes": captured,
        "capture_rate": round(capture_rate, 4),
    }


def _calculate_spread_distribution(prices: list[float], interval_hours: float) -> dict:
    """Calculate spread distribution statistics for a price series.

    Returns percentile-based distribution of price spreads within each day.
    """
    if not prices:
        return {"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0, "max_spread": 0}

    intervals_per_day = int(24 / interval_hours)
    total_days = len(prices) // intervals_per_day

    daily_spreads = []
    for day_idx in range(total_days):
        day_start = day_idx * intervals_per_day
        day_end = day_start + intervals_per_day
        day_prices = prices[day_start:day_end]
        if day_prices:
            spread = max(day_prices) - min(day_prices)
            daily_spreads.append(spread)

    if not daily_spreads:
        return {"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0, "max_spread": 0}

    arr = np.array(daily_spreads)
    return {
        "p10": round(float(np.percentile(arr, 10)), 2),
        "p25": round(float(np.percentile(arr, 25)), 2),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p75": round(float(np.percentile(arr, 75)), 2),
        "p90": round(float(np.percentile(arr, 90)), 2),
        "max_spread": round(float(arr.max()), 2),
    }


@router.get("/five-min-settlement")
async def get_five_min_settlement(
    year: int = Query(..., description="Analysis year"),
    power_mw: float = Query(default=100, gt=0, description="BESS power capacity in MW"),
    duration_hours: float = Query(default=4, gt=0, description="BESS energy duration in hours"),
) -> FiveMinSettlementResponse:
    """评估 5 分钟结算对储能收入的影响。

    WEM 正从 30 分钟结算过渡到 5 分钟结算。本端点分析结算间隔缩短对
    价格波动性、BESS 套利收入和极端事件捕获率的影响。

    当实际 5 分钟数据可用时自动切换到实际数据模式；否则使用基于 30 分钟
    数据的波动性模拟。
    """
    # Check if actual 5-min data is available
    use_actual = _check_actual_5min_data_available(year)

    if use_actual:
        # Use actual 5-minute data
        prices_5min = _fetch_actual_5min_prices(year)
        prices_30min = _fetch_wem_prices_for_year(year)

        if not prices_5min or not prices_30min:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "DATA_NOT_FOUND",
                    "message": f"WEM price data not found for year {year}",
                    "suggested_action": "Try a different year or check data availability",
                },
            )
        data_mode: Literal["simulated", "actual"] = "actual"
    else:
        # Simulate 5-min prices from 30-min data
        prices_30min = _fetch_wem_prices_for_year(year)

        if not prices_30min:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "DATA_NOT_FOUND",
                    "message": f"WEM 30-minute price data not found for year {year}",
                    "suggested_action": "Ensure WEM price data has been scraped for the requested year",
                },
            )

        # Use deterministic seed based on year for reproducibility
        seed = _SEED_BASE + year
        prices_5min = _simulate_5min_prices_from_30min(prices_30min, seed)
        data_mode = "simulated"

    # Calculate volatility metrics
    volatility_30min = _calculate_price_return_volatility(prices_30min)
    volatility_5min = _calculate_price_return_volatility(prices_5min)

    if volatility_30min > 0:
        volatility_change_pct = round(
            ((volatility_5min - volatility_30min) / volatility_30min) * 100, 2
        )
    else:
        volatility_change_pct = 0.0

    # Calculate revenue comparison
    interval_30min = 0.5  # hours
    interval_5min = 5 / 60  # hours

    revenue_30min = _calculate_bess_arbitrage_revenue(
        prices_30min, power_mw, duration_hours, interval_30min
    )
    revenue_5min = _calculate_bess_arbitrage_revenue(
        prices_5min, power_mw, duration_hours, interval_5min
    )

    if revenue_30min > 0:
        revenue_change_pct = round(
            ((revenue_5min - revenue_30min) / revenue_30min) * 100, 2
        )
    else:
        revenue_change_pct = 0.0

    # Calculate spread distribution comparison
    spread_30min = _calculate_spread_distribution(prices_30min, interval_30min)
    spread_5min = _calculate_spread_distribution(prices_5min, interval_5min)

    spread_distribution_comparison = {
        "settlement_30min": spread_30min,
        "settlement_5min": spread_5min,
    }

    # Calculate spike capture rate comparison
    spike_30min = _calculate_spike_capture_rate(
        prices_30min, power_mw, duration_hours, interval_30min
    )
    spike_5min = _calculate_spike_capture_rate(
        prices_5min, power_mw, duration_hours, interval_5min
    )

    spike_capture_rate_comparison = {
        "settlement_30min": spike_30min,
        "settlement_5min": spike_5min,
    }

    return FiveMinSettlementResponse(
        data_mode=data_mode,
        volatility_30min=round(volatility_30min, 6),
        volatility_5min=round(volatility_5min, 6),
        volatility_change_pct=volatility_change_pct,
        revenue_change_pct=revenue_change_pct,
        spread_distribution_comparison=spread_distribution_comparison,
        spike_capture_rate_comparison=spike_capture_rate_comparison,
    )
