"""Spike Profit Analysis API routes.

Provides the NEM spike profit analysis endpoint that calculates
extreme price event (>threshold $/MWh) contributions to BESS annual revenue.

Uses deps.py for dependency injection and network_fees for settlement intervals.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from deps import get_db
from network_fees import get_settlement_interval

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/nem", tags=["NEM Modules"])

# ---------------------------------------------------------------------------
# Valid NEM regions
# ---------------------------------------------------------------------------

VALID_NEM_REGIONS = {"NSW1", "QLD1", "VIC1", "SA1", "TAS1"}

# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class SpikeProfitResponse(BaseModel):
    """极端价格事件利润分析响应"""

    region: str
    year: int
    threshold: float

    # 事件统计
    spike_count: int
    total_spike_hours: float
    max_single_event_revenue: float

    # 收入贡献
    spike_revenue_total: float
    annual_arbitrage_revenue: float
    spike_revenue_pct: float  # spike_revenue_total / annual_arbitrage_revenue * 100

    # 分布数据
    monthly_distribution: list[dict]  # [{month: 1, count: 3, revenue: 12000}, ...]
    hourly_distribution: list[dict]  # [{hour: 14, count: 5, avg_price: 5200}, ...]
    duration_distribution: list[dict]  # [{duration_min: 5, count: 10}, ...]

    # 年际趋势
    yearly_trend: list[dict]  # [{year: 2022, count: 15, revenue: 45000}, ...]


# ---------------------------------------------------------------------------
# Spike detection logic
# ---------------------------------------------------------------------------


def _detect_spike_events(
    rows: list[tuple[str, float]],
    threshold: float,
    interval_minutes: int,
) -> list[dict]:
    """Detect consecutive spike events from ordered price data.

    A spike event is a contiguous block of intervals where price >= threshold.

    Args:
        rows: List of (settlement_date, price) tuples ordered by time.
        threshold: Price threshold in $/MWh.
        interval_minutes: Settlement interval in minutes.

    Returns:
        List of spike event dicts with start, end, duration, prices, revenue.
    """
    interval_hours = interval_minutes / 60.0
    events: list[dict] = []
    current_event: Optional[dict] = None

    for settlement_date, price in rows:
        if price >= threshold:
            if current_event is None:
                current_event = {
                    "start": settlement_date,
                    "end": settlement_date,
                    "intervals": 1,
                    "prices": [price],
                    "revenue": price * interval_hours,
                    "max_price": price,
                }
            else:
                current_event["end"] = settlement_date
                current_event["intervals"] += 1
                current_event["prices"].append(price)
                current_event["revenue"] += price * interval_hours
                current_event["max_price"] = max(current_event["max_price"], price)
        else:
            if current_event is not None:
                current_event["duration_min"] = current_event["intervals"] * interval_minutes
                events.append(current_event)
                current_event = None

    # Close any trailing event
    if current_event is not None:
        current_event["duration_min"] = current_event["intervals"] * interval_minutes
        events.append(current_event)

    return events


def _compute_annual_arbitrage_revenue(
    rows: list[tuple[str, float]],
    interval_minutes: int,
) -> float:
    """Estimate annual arbitrage revenue using daily peak-trough spread.

    For each day, computes the best single-cycle spread (peak - trough)
    and multiplies by interval_hours to get daily revenue for 1 MW BESS.
    Sums across all days for annual estimate.

    Args:
        rows: List of (settlement_date, price) tuples ordered by time.
        interval_minutes: Settlement interval in minutes.

    Returns:
        Estimated annual arbitrage revenue in $/MW.
    """
    interval_hours = interval_minutes / 60.0

    # Group prices by day
    daily_prices: dict[str, list[float]] = defaultdict(list)
    for settlement_date, price in rows:
        day_key = settlement_date[:10]
        daily_prices[day_key].append(price)

    total_revenue = 0.0
    for _day, prices in daily_prices.items():
        if len(prices) < 2:
            continue
        # Best single-cycle revenue: peak - trough (assuming buy at trough, sell at peak)
        peak = max(prices)
        trough = min(prices)
        spread = peak - trough
        if spread > 0:
            # Revenue from one full cycle (charge at trough, discharge at peak)
            # Duration of one cycle = energy_capacity / power = duration_hours
            # For 1 MW reference, revenue = spread * interval_hours per interval
            # But for daily spread, it's simply spread * 1 (one cycle per day)
            total_revenue += spread * interval_hours

    return total_revenue


def _compute_distributions(
    events: list[dict],
    interval_minutes: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Compute monthly, hourly, and duration distributions from spike events.

    Returns:
        Tuple of (monthly_distribution, hourly_distribution, duration_distribution)
    """
    interval_hours = interval_minutes / 60.0

    # Monthly distribution
    monthly_data: dict[int, dict] = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    # Hourly distribution (count of spike intervals per hour, avg price)
    hourly_data: dict[int, dict] = defaultdict(lambda: {"count": 0, "total_price": 0.0})
    # Duration distribution
    duration_data: dict[int, int] = defaultdict(int)

    for event in events:
        # Monthly: use start date month
        month = int(event["start"][5:7])
        monthly_data[month]["count"] += 1
        monthly_data[month]["revenue"] += event["revenue"]

        # Duration distribution
        duration_data[event["duration_min"]] += 1

        # Hourly: count each interval's hour
        # We need to parse hours from the event's individual intervals
        # Since we only have start/end, we'll use the start hour for each interval
        # For more accuracy, we track hours from the start time
        start_hour = int(event["start"][11:13])
        for i in range(event["intervals"]):
            # Calculate hour for each interval
            hour = (start_hour + (i * interval_minutes) // 60) % 24
            hourly_data[hour]["count"] += 1
            hourly_data[hour]["total_price"] += event["prices"][i]

    # Format monthly distribution
    monthly_distribution = []
    for month in range(1, 13):
        entry = monthly_data.get(month, {"count": 0, "revenue": 0.0})
        monthly_distribution.append({
            "month": month,
            "count": entry["count"],
            "revenue": round(entry["revenue"], 2),
        })

    # Format hourly distribution
    hourly_distribution = []
    for hour in range(24):
        entry = hourly_data.get(hour, {"count": 0, "total_price": 0.0})
        avg_price = (
            round(entry["total_price"] / entry["count"], 2)
            if entry["count"] > 0
            else 0.0
        )
        hourly_distribution.append({
            "hour": hour,
            "count": entry["count"],
            "avg_price": avg_price,
        })

    # Format duration distribution (sorted by duration)
    duration_distribution = sorted(
        [{"duration_min": dur, "count": cnt} for dur, cnt in duration_data.items()],
        key=lambda x: x["duration_min"],
    )

    return monthly_distribution, hourly_distribution, duration_distribution


def _compute_yearly_trend(
    db,
    region: str,
    target_year: int,
    threshold: float,
    interval_minutes: int,
) -> list[dict]:
    """Compute spike event trends across multiple years (at least 3 years).

    Looks back up to 5 years from target_year to find available data.

    Args:
        db: DatabaseManager instance.
        region: NEM region.
        target_year: The primary analysis year.
        threshold: Price threshold.
        interval_minutes: Settlement interval in minutes.

    Returns:
        List of yearly trend dicts with year, count, revenue, total_hours.
    """
    interval_hours = interval_minutes / 60.0
    trend: list[dict] = []

    # Check years from target_year-4 to target_year (5 year window)
    for year in range(target_year - 4, target_year + 1):
        table_name = f"trading_price_{year}"
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                # Check if table exists
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                    (table_name,),
                )
                if not cursor.fetchone():
                    continue

                # Count spike intervals and compute revenue
                cursor.execute(
                    f"""
                    SELECT COUNT(*), COALESCE(SUM(rrp_aud_mwh), 0)
                    FROM {table_name}
                    WHERE region_id = ? AND rrp_aud_mwh >= ?
                    """,
                    (region, threshold),
                )
                row = cursor.fetchone()
                spike_intervals = row[0] if row else 0
                spike_revenue_sum = row[1] if row else 0.0

                if spike_intervals == 0:
                    trend.append({
                        "year": year,
                        "count": 0,
                        "revenue": 0.0,
                        "total_hours": 0.0,
                    })
                    continue

                # For event count, we need to detect events
                cursor.execute(
                    f"""
                    SELECT settlement_date, rrp_aud_mwh
                    FROM {table_name}
                    WHERE region_id = ?
                    ORDER BY settlement_date ASC
                    """,
                    (region,),
                )
                rows = cursor.fetchall()
                events = _detect_spike_events(rows, threshold, interval_minutes)

                total_hours = spike_intervals * interval_hours
                total_revenue = sum(e["revenue"] for e in events)

                trend.append({
                    "year": year,
                    "count": len(events),
                    "revenue": round(total_revenue, 2),
                    "total_hours": round(total_hours, 4),
                })

        except Exception as e:
            logger.warning(f"Failed to query year {year} for trend: {e}")
            continue

    return trend


# ---------------------------------------------------------------------------
# Route: GET /spike-profit
# ---------------------------------------------------------------------------


@router.get(
    "/spike-profit",
    summary="Spike profit analysis",
    description=(
        "Calculates extreme price event (spike) contributions to BESS annual revenue. "
        "Identifies consecutive intervals where price >= threshold, computes event "
        "statistics, revenue contribution percentage, and distribution analysis."
    ),
    response_model=SpikeProfitResponse,
    responses={
        404: {"description": "Data not found for the specified year/region"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def get_spike_profit(
    region: str = Query(..., description="NEM region: NSW1, QLD1, VIC1, SA1, TAS1"),
    year: int = Query(..., description="Analysis year"),
    threshold: float = Query(default=3000, description="Price threshold $/MWh"),
) -> SpikeProfitResponse:
    """计算极端价格事件的利润贡献分析。"""

    # Validate region
    if region not in VALID_NEM_REGIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid region '{region}'. Must be one of: {', '.join(sorted(VALID_NEM_REGIONS))}",
        )

    # Validate threshold
    if threshold <= 0:
        raise HTTPException(
            status_code=422,
            detail="Threshold must be a positive number.",
        )

    db = get_db()
    interval_minutes = get_settlement_interval(region)
    interval_hours = interval_minutes / 60.0
    table_name = f"trading_price_{year}"

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,),
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"No price data available for year {year}",
                )

            # Fetch all price data for the region, ordered by time
            cursor.execute(
                f"""
                SELECT settlement_date, rrp_aud_mwh
                FROM {table_name}
                WHERE region_id = ?
                ORDER BY settlement_date ASC
                """,
                (region,),
            )
            rows = cursor.fetchall()

            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No price data found for region {region} in year {year}",
                )

        # Detect spike events
        events = _detect_spike_events(rows, threshold, interval_minutes)

        # Compute annual arbitrage revenue estimate
        annual_arbitrage_revenue = _compute_annual_arbitrage_revenue(rows, interval_minutes)

        # Handle no-events case: return empty results with historical frequency reference
        if not events:
            # Compute yearly trend for historical reference
            yearly_trend = _compute_yearly_trend(db, region, year, threshold, interval_minutes)

            return SpikeProfitResponse(
                region=region,
                year=year,
                threshold=threshold,
                spike_count=0,
                total_spike_hours=0.0,
                max_single_event_revenue=0.0,
                spike_revenue_total=0.0,
                annual_arbitrage_revenue=round(annual_arbitrage_revenue, 2),
                spike_revenue_pct=0.0,
                monthly_distribution=[
                    {"month": m, "count": 0, "revenue": 0.0} for m in range(1, 13)
                ],
                hourly_distribution=[
                    {"hour": h, "count": 0, "avg_price": 0.0} for h in range(24)
                ],
                duration_distribution=[],
                yearly_trend=yearly_trend,
            )

        # Compute event statistics
        spike_count = len(events)
        total_spike_intervals = sum(e["intervals"] for e in events)
        total_spike_hours = round(total_spike_intervals * interval_hours, 4)
        max_single_event_revenue = round(max(e["revenue"] for e in events), 2)
        spike_revenue_total = round(sum(e["revenue"] for e in events), 2)

        # Compute spike revenue percentage
        spike_revenue_pct = (
            round((spike_revenue_total / annual_arbitrage_revenue) * 100, 2)
            if annual_arbitrage_revenue > 0
            else 0.0
        )

        # Compute distributions
        monthly_distribution, hourly_distribution, duration_distribution = (
            _compute_distributions(events, interval_minutes)
        )

        # Compute yearly trend
        yearly_trend = _compute_yearly_trend(db, region, year, threshold, interval_minutes)

        return SpikeProfitResponse(
            region=region,
            year=year,
            threshold=threshold,
            spike_count=spike_count,
            total_spike_hours=total_spike_hours,
            max_single_event_revenue=max_single_event_revenue,
            spike_revenue_total=spike_revenue_total,
            annual_arbitrage_revenue=round(annual_arbitrage_revenue, 2),
            spike_revenue_pct=spike_revenue_pct,
            monthly_distribution=monthly_distribution,
            hourly_distribution=hourly_distribution,
            duration_distribution=duration_distribution,
            yearly_trend=yearly_trend,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in spike-profit: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
