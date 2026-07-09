"""Co-Optimization API routes.

Provides the co-optimization backtest endpoint that runs LP/MILP joint
optimization of energy arbitrage and FCAS market participation for BESS.

Uses the CoOptimizationEngine from engines/co_optimization_engine.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging

from fastapi import APIRouter, HTTPException

from deps import get_db
from engines.co_optimization_engine import CoOptConfig, CoOptimizationEngine
from models.coopt_models import CoOptimizationParams, CoOptimizationResponse
from models.financial_params import BatterySpecs
from network_fees import get_settlement_interval

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/co-optimization", tags=["Co-Optimization"])

# ---------------------------------------------------------------------------
# In-memory cache for co-optimization results
# Key: hash of (region, year, month, resolution, power_mw, duration_hours, rte)
# Value: CoOptimizationResponse dict
# ---------------------------------------------------------------------------
_COOPT_CACHE: dict[str, dict] = {}
_COOPT_CACHE_MAX_SIZE = 50


def _build_cache_key(params: CoOptimizationParams) -> str:
    """Build a deterministic cache key from request parameters."""
    key_data = {
        "market": params.market,
        "region": params.region,
        "year": params.year,
        "month": params.month,
        "resolution": params.resolution,
        "power_mw": params.power_mw,
        "duration_hours": params.duration_hours,
        "round_trip_efficiency": params.round_trip_efficiency,
        "fcas_services": sorted(params.fcas_services),
        "fcas_max_capacity_pct": params.fcas_max_capacity_pct,
    }
    serialized = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]

# ---------------------------------------------------------------------------
# Valid regions per market
# ---------------------------------------------------------------------------

VALID_REGIONS = {
    "NEM": {"NSW1", "QLD1", "VIC1", "SA1", "TAS1"},
    "WEM": {"WEM"},
}

# FCAS price column mapping in trading_price tables
FCAS_COLUMN_MAP = {
    "raise1sec": "raise1sec_rrp",
    "raise6sec": "raise6sec_rrp",
    "raise60sec": "raise60sec_rrp",
    "raise5min": "raise5min_rrp",
    "raisereg": "raisereg_rrp",
    "lower1sec": "lower1sec_rrp",
    "lower6sec": "lower6sec_rrp",
    "lower60sec": "lower60sec_rrp",
    "lower5min": "lower5min_rrp",
    "lowerreg": "lowerreg_rrp",
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_energy_prices(
    db,
    region: str,
    year: int,
    month: int | None,
    interval_minutes: int,
) -> list[dict]:
    """Load energy price data from the trading_price table.

    Returns empty list if no data found (graceful degradation).
    """
    table_name = f"trading_price_{year}"
    interval_hours = interval_minutes / 60.0

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,),
            )
            if not cursor.fetchone():
                return []

            # Build query with optional month filter
            query = f"""
                SELECT settlement_date, rrp_aud_mwh
                FROM {table_name}
                WHERE region_id = ?
            """
            params: list = [region]

            if month is not None:
                month_prefix = f"{year}-{month:02d}"
                query += " AND settlement_date LIKE ?"
                params.append(f"{month_prefix}%")

            query += " ORDER BY settlement_date ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "timestamp": row[0],
                    "price": float(row[1]) if row[1] is not None else 0.0,
                    "interval_hours": interval_hours,
                }
                for row in rows
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error loading energy prices: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


def _load_fcas_prices(
    db,
    region: str,
    year: int,
    month: int | None,
    fcas_services: list[str],
) -> dict[str, list[float]]:
    """Load FCAS price data from the trading_price table.

    Returns zeros for services whose columns don't exist or have no data.

    Args:
        db: DatabaseManager instance.
        region: Market region identifier.
        year: Data year.
        month: Optional month filter (1-12).
        fcas_services: List of FCAS service names to load.

    Returns:
        Dict mapping service name to list of prices per interval.
    """
    table_name = f"trading_price_{year}"
    fcas_prices: dict[str, list[float]] = {}

    # Determine which columns to query
    columns_to_query = []
    service_to_column: dict[str, str] = {}
    for service in fcas_services:
        col = FCAS_COLUMN_MAP.get(service)
        if col:
            columns_to_query.append(col)
            service_to_column[service] = col

    if not columns_to_query:
        # No valid FCAS services requested, return empty
        return {s: [] for s in fcas_services}

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check which FCAS columns actually exist in the table
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                (table_name,),
            )
            existing_columns = {row[0] for row in cursor.fetchall()}

            available_columns = [c for c in columns_to_query if c in existing_columns]

            if not available_columns:
                # No FCAS columns available, return zeros
                logger.info(
                    f"No FCAS price columns found in {table_name}, using zeros"
                )
                return {s: [] for s in fcas_services}

            # Build query for available FCAS columns
            col_select = ", ".join(available_columns)
            query = f"""
                SELECT {col_select}
                FROM {table_name}
                WHERE region_id = ?
            """
            params: list = [region]

            if month is not None:
                month_prefix = f"{year}-{month:02d}"
                query += " AND settlement_date LIKE ?"
                params.append(f"{month_prefix}%")

            query += " ORDER BY settlement_date ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Map results back to service names
            for service, col in service_to_column.items():
                if col in available_columns:
                    col_idx = available_columns.index(col)
                    fcas_prices[service] = [
                        float(row[col_idx]) if row[col_idx] is not None else 0.0
                        for row in rows
                    ]
                else:
                    fcas_prices[service] = []

            # Fill missing services with empty lists
            for service in fcas_services:
                if service not in fcas_prices:
                    fcas_prices[service] = []

            return fcas_prices

    except Exception as e:
        logger.warning(f"Failed to load FCAS prices: {e}, using zeros")
        return {s: [] for s in fcas_services}


# ---------------------------------------------------------------------------
# Route: POST /backtest
# ---------------------------------------------------------------------------


@router.post(
    "/backtest",
    summary="Co-optimization backtest",
    description=(
        "Executes LP/MILP co-optimization of energy arbitrage and FCAS market "
        "participation for a BESS. Returns revenue breakdown, constraint binding "
        "report, and monthly decomposition."
    ),
    response_model=CoOptimizationResponse,
    responses={
        404: {"description": "Price data not found for the specified year/region"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def run_co_optimization(
    params: CoOptimizationParams,
) -> CoOptimizationResponse:
    """执行联合优化回测。"""

    # Validate region
    valid_regions = VALID_REGIONS.get(params.market, set())
    if params.region not in valid_regions:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid region '{params.region}' for market {params.market}. "
                f"Must be one of: {', '.join(sorted(valid_regions))}"
            ),
        )

    # Validate FCAS services
    valid_fcas = set(FCAS_COLUMN_MAP.keys())
    invalid_services = [s for s in params.fcas_services if s not in valid_fcas]
    if invalid_services:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid FCAS services: {invalid_services}. "
                f"Valid services: {sorted(valid_fcas)}"
            ),
        )

    db = get_db()

    # --- Cache lookup ---
    cache_key = _build_cache_key(params)
    if cache_key in _COOPT_CACHE:
        logger.info(f"Co-optimization cache hit: {params.region}/{params.year}-{params.month} ({params.resolution})")
        return CoOptimizationResponse(**_COOPT_CACHE[cache_key])
    interval_minutes = get_settlement_interval(params.region)

    # Load energy prices
    energy_prices = _load_energy_prices(
        db, params.region, params.year, params.month, interval_minutes
    )

    # Load FCAS prices (gracefully handles missing data)
    fcas_prices = _load_fcas_prices(
        db, params.region, params.year, params.month, params.fcas_services
    )

    # Graceful degradation: if no energy price data available, return empty result
    if not energy_prices:
        return CoOptimizationResponse(
            status="infeasible",
            optimality_gap=None,
            energy_revenue=0.0,
            fcas_revenue=0.0,
            total_gross_revenue=0.0,
            total_net_revenue=0.0,
            energy_only_revenue=0.0,
            co_optimization_uplift=0.0,
            binding_constraints=[],
            monthly_breakdown=[],
            solve_time_seconds=0.0,
            solver_status=f"No price data available for {params.region} in {params.year}"
            + (f" month {params.month}" if params.month else ""),
        )

    # Downsample to 30-minute intervals for MILP performance (fast mode only)
    # 5-min data → 30-min: reduces problem size by 6x (from ~9000 to ~1500 variables per month)
    # In precise mode, keep original 5-min data for higher accuracy
    if params.resolution == "fast" and len(energy_prices) > 2000 and interval_minutes <= 5:
        downsampled = []
        bucket_size = 6  # 6 × 5min = 30min
        for i in range(0, len(energy_prices), bucket_size):
            bucket = energy_prices[i:i + bucket_size]
            avg_price = sum(p["price"] for p in bucket) / len(bucket)
            downsampled.append({
                "timestamp": bucket[0]["timestamp"],
                "price": avg_price,
                "interval_hours": 0.5,  # 30 minutes
            })
        energy_prices = downsampled
        # Also downsample FCAS prices
        if fcas_prices:
            for service in list(fcas_prices.keys()):
                prices = fcas_prices[service]
                if len(prices) > 2000:
                    ds_prices = []
                    for i in range(0, len(prices), bucket_size):
                        bucket = prices[i:i + bucket_size]
                        ds_prices.append(sum(bucket) / len(bucket))
                    fcas_prices[service] = ds_prices
        logger.info(
            f"Downsampled {params.region} {params.year}-{params.month} from "
            f"{len(energy_prices) * bucket_size} to {len(energy_prices)} intervals (30-min)"
        )
    elif params.resolution == "precise":
        logger.info(
            f"Precise mode: keeping original {interval_minutes}-min data "
            f"({len(energy_prices)} intervals) for {params.region} {params.year}-{params.month}"
        )

    # Build BatterySpecs for the engine
    battery_specs = BatterySpecs(
        power_mw=params.power_mw,
        duration_hours=params.duration_hours,
        round_trip_efficiency=params.round_trip_efficiency,
    )

    # Build CoOptConfig
    # In precise mode, allow up to 120s time limit for larger problem size
    effective_time_limit = params.time_limit_seconds
    if params.resolution == "precise":
        effective_time_limit = min(params.time_limit_seconds, 120)

    config = CoOptConfig(
        fcas_services=params.fcas_services,
        fcas_max_capacity_pct=params.fcas_max_capacity_pct,
        time_limit_seconds=effective_time_limit,
        optimality_gap_tolerance=params.optimality_gap_tolerance,
        monthly_segmentation=(params.month is None),  # segment by month only for full year
    )

    # Override engine SOC limits based on params
    engine = CoOptimizationEngine(battery_specs, config)
    engine.min_soc_mwh = engine.energy_mwh * (params.min_soc_pct / 100.0)
    engine.max_soc_mwh = engine.energy_mwh * (params.max_soc_pct / 100.0)

    try:
        result = await asyncio.to_thread(
            engine.optimize,
            energy_prices,
            fcas_prices,
            variable_om_per_mwh=params.variable_om_per_mwh,
            network_fee_per_mwh=params.network_fee_per_mwh,
            degradation_cost_per_mwh=params.degradation_cost_per_mwh,
        )
    except Exception as e:
        logger.error(f"Co-optimization engine error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Optimization engine error: {e}",
        )

    response = CoOptimizationResponse(
        status=result.status,
        optimality_gap=result.optimality_gap,
        energy_revenue=result.energy_revenue,
        fcas_revenue=result.fcas_revenue,
        total_gross_revenue=result.total_gross_revenue,
        total_net_revenue=result.total_net_revenue,
        energy_only_revenue=result.energy_only_revenue,
        co_optimization_uplift=result.co_optimization_uplift,
        binding_constraints=result.binding_constraints,
        monthly_breakdown=result.monthly_breakdown,
        solve_time_seconds=result.solve_time_seconds,
        solver_status=result.solver_status,
    )

    # --- Cache store ---
    if response.status in ("optimal", "feasible"):
        if len(_COOPT_CACHE) >= _COOPT_CACHE_MAX_SIZE:
            # Evict oldest entry
            oldest_key = next(iter(_COOPT_CACHE))
            del _COOPT_CACHE[oldest_key]
        _COOPT_CACHE[cache_key] = response.model_dump()
        logger.info(f"Co-optimization cached: {params.region}/{params.year}-{params.month} ({params.resolution}) in {result.solve_time_seconds:.1f}s")

    return response
