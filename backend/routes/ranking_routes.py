"""Regional Ranking API routes for NEM region investment attractiveness scoring.

Provides multi-dimensional scoring and ranking of NEM regions based on:
- Arbitrage revenue potential (price volatility)
- Extreme price event frequency (spikes > $300/MWh)
- FCAS revenue potential (average FCAS prices)
- Saturation risk (inverse of BESS capacity saturation)
- Network constraint frequency (heuristic-based)

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 12.3
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/nem", tags=["NEM Modules"])

# ---------------------------------------------------------------------------
# NEM regions
# ---------------------------------------------------------------------------

NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class RegionalRankingResponse(BaseModel):
    """区域排名响应"""

    rankings: list[dict]
    # [{rank, region, total_score, dimensions: {arbitrage, spikes, fcas, saturation, constraints}}]

    weights_used: dict
    # {arbitrage: 0.2, spikes: 0.2, fcas: 0.2, saturation: 0.2, constraints: 0.2}

    data_year: int
    methodology_notes: list[str]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _compute_arbitrage_scores(cursor, year: int) -> dict[str, float]:
    """Compute arbitrage score per region based on price volatility (std/mean ratio).

    Higher volatility = more arbitrage opportunity = higher score.
    """
    table_name = f"trading_price_{year}"
    scores: dict[str, float] = {}

    for region in NEM_REGIONS:
        try:
            cursor.execute(
                f"""
                SELECT AVG(rrp_aud_mwh), COUNT(*),
                       SUM(rrp_aud_mwh * rrp_aud_mwh) as sum_sq,
                       SUM(rrp_aud_mwh) as sum_val
                FROM {table_name}
                WHERE region_id = ?
                """,
                (region,),
            )
            row = cursor.fetchone()
            if row and row[0] is not None and row[1] > 0:
                avg_price = row[0]
                count = row[1]
                sum_sq = row[2]
                sum_val = row[3]
                # Compute standard deviation
                variance = (sum_sq / count) - (sum_val / count) ** 2
                std_dev = max(0, variance) ** 0.5
                # Coefficient of variation (std/mean) as volatility measure
                # Use abs(avg) to handle negative average prices
                if abs(avg_price) > 1.0:
                    scores[region] = std_dev / abs(avg_price)
                else:
                    scores[region] = std_dev  # fallback for near-zero average
            else:
                scores[region] = 0.0
        except Exception:
            scores[region] = 0.0

    return scores


def _compute_spike_scores(cursor, year: int) -> dict[str, float]:
    """Compute spike score per region based on count of prices > $300/MWh.

    More spikes = more revenue opportunity = higher score.
    """
    table_name = f"trading_price_{year}"
    scores: dict[str, float] = {}

    for region in NEM_REGIONS:
        try:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {table_name}
                WHERE region_id = ? AND rrp_aud_mwh > 300
                """,
                (region,),
            )
            row = cursor.fetchone()
            scores[region] = float(row[0]) if row else 0.0
        except Exception:
            scores[region] = 0.0

    return scores


def _compute_fcas_scores(cursor, year: int) -> dict[str, float]:
    """Compute FCAS revenue score per region based on average FCAS prices.

    Higher average FCAS prices = more FCAS revenue potential = higher score.
    """
    table_name = f"trading_price_{year}"
    scores: dict[str, float] = {}

    # FCAS columns available in the trading_price table
    fcas_cols = [
        "raise6sec_rrp", "raise60sec_rrp", "raise5min_rrp", "raisereg_rrp",
        "lower6sec_rrp", "lower60sec_rrp", "lower5min_rrp", "lowerreg_rrp",
    ]

    for region in NEM_REGIONS:
        try:
            # Check if FCAS columns exist and have data
            avg_expressions = ", ".join(f"AVG({col})" for col in fcas_cols)
            cursor.execute(
                f"""
                SELECT {avg_expressions}
                FROM {table_name}
                WHERE region_id = ?
                """,
                (region,),
            )
            row = cursor.fetchone()
            if row:
                # Average across all FCAS services (ignore NULLs)
                fcas_values = [v for v in row if v is not None and v > 0]
                scores[region] = sum(fcas_values) / len(fcas_values) if fcas_values else 0.0
            else:
                scores[region] = 0.0
        except Exception:
            scores[region] = 0.0

    return scores


def _compute_saturation_scores() -> dict[str, float]:
    """Compute saturation risk score per region.

    Lower saturation = higher investment attractiveness = higher score.
    Uses CapacityDataLoader if available, otherwise returns heuristic defaults.
    """
    try:
        from models.capacity_models import CapacityDataLoader

        loader = CapacityDataLoader()
        data = loader.load()

        # Approximate peak load per region (MW) - based on AEMO data
        peak_loads = {
            "NSW1": 14000,
            "QLD1": 10000,
            "VIC1": 10000,
            "SA1": 3500,
            "TAS1": 1800,
        }

        scores: dict[str, float] = {}
        for region in NEM_REGIONS:
            summary = data.get_region_summary(region)
            registered_mw = summary["registered_mw"]
            peak_load = peak_loads.get(region, 5000)
            # Saturation ratio: registered BESS / peak load
            saturation_ratio = registered_mw / peak_load if peak_load > 0 else 0
            # Inverse: lower saturation = higher score
            # Cap at 1.0 for very low saturation
            scores[region] = max(0.0, 1.0 - saturation_ratio)
        return scores
    except Exception as exc:
        logger.warning("Failed to compute saturation scores from capacity data: %s", exc)
        # Heuristic defaults based on known market conditions
        return {
            "NSW1": 0.7,
            "QLD1": 0.8,
            "VIC1": 0.6,
            "SA1": 0.4,
            "TAS1": 0.9,
        }


def _compute_constraint_scores() -> dict[str, float]:
    """Compute network constraint score per region.

    Higher constraint frequency = more price separation = more opportunity.
    Uses heuristic values based on known NEM network characteristics.
    """
    # Heuristic scores based on known network constraint patterns:
    # SA1 and QLD1 have more interconnector constraints
    # TAS1 has Basslink constraints
    # NSW1 and VIC1 are more interconnected
    return {
        "NSW1": 0.5,
        "QLD1": 0.7,
        "VIC1": 0.4,
        "SA1": 0.9,
        "TAS1": 0.6,
    }


def _normalize_scores(raw_scores: dict[str, float]) -> dict[str, float]:
    """Normalize raw scores to 0-1 scale across regions using min-max normalization.

    If all values are equal, returns 0.5 for all regions.
    """
    if not raw_scores:
        return {r: 0.0 for r in NEM_REGIONS}

    values = list(raw_scores.values())
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return {r: 0.5 for r in raw_scores}

    return {
        region: (score - min_val) / (max_val - min_val)
        for region, score in raw_scores.items()
    }


# ---------------------------------------------------------------------------
# Route: GET /api/v1/nem/regional-ranking
# ---------------------------------------------------------------------------


@router.get(
    "/regional-ranking",
    summary="Get NEM regional investment ranking",
    description=(
        "Computes multi-dimensional investment attractiveness ranking for NEM regions. "
        "Dimensions: arbitrage potential, spike frequency, FCAS revenue, "
        "saturation risk, network constraints."
    ),
    response_model=RegionalRankingResponse,
)
async def get_regional_ranking(
    year: int = Query(..., description="Analysis year"),
    weight_arbitrage: float = Query(default=0.2, ge=0, le=1, description="Weight for arbitrage dimension"),
    weight_spikes: float = Query(default=0.2, ge=0, le=1, description="Weight for spike frequency dimension"),
    weight_fcas: float = Query(default=0.2, ge=0, le=1, description="Weight for FCAS revenue dimension"),
    weight_saturation: float = Query(default=0.2, ge=0, le=1, description="Weight for saturation risk dimension"),
    weight_constraints: float = Query(default=0.2, ge=0, le=1, description="Weight for network constraints dimension"),
) -> RegionalRankingResponse:
    """基于多维度权重计算 NEM 区域排名。

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 12.3
    """
    db = get_db()
    methodology_notes: list[str] = []

    # Validate that weights sum is positive (allow non-unity sums, normalize internally)
    total_weight = (
        weight_arbitrage + weight_spikes + weight_fcas + weight_saturation + weight_constraints
    )
    if total_weight <= 0:
        raise HTTPException(
            status_code=400,
            detail="Sum of weights must be greater than zero.",
        )

    # Normalize weights to sum to 1.0
    w_arb = weight_arbitrage / total_weight
    w_spk = weight_spikes / total_weight
    w_fcas = weight_fcas / total_weight
    w_sat = weight_saturation / total_weight
    w_con = weight_constraints / total_weight

    table_name = f"trading_price_{year}"

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if price data table exists for the requested year
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,),
            )
            has_price_data = cursor.fetchone() is not None

            if has_price_data:
                # Compute data-driven scores
                raw_arbitrage = _compute_arbitrage_scores(cursor, year)
                raw_spikes = _compute_spike_scores(cursor, year)
                raw_fcas = _compute_fcas_scores(cursor, year)
                methodology_notes.append(
                    f"Arbitrage scores based on price volatility (coefficient of variation) for {year}."
                )
                methodology_notes.append(
                    f"Spike scores based on count of intervals with price > $300/MWh in {year}."
                )

                # Check if FCAS data is available
                fcas_available = any(v > 0 for v in raw_fcas.values())
                if fcas_available:
                    methodology_notes.append(
                        f"FCAS scores based on average FCAS prices across 8 services in {year}."
                    )
                else:
                    methodology_notes.append(
                        "FCAS data not available for this year; using heuristic estimates."
                    )
                    raw_fcas = {
                        "NSW1": 15.0,
                        "QLD1": 12.0,
                        "VIC1": 14.0,
                        "SA1": 20.0,
                        "TAS1": 8.0,
                    }
            else:
                # No price data available - use reasonable defaults
                methodology_notes.append(
                    f"No price data available for {year}. Using heuristic default scores."
                )
                raw_arbitrage = {
                    "NSW1": 3.0,
                    "QLD1": 3.5,
                    "VIC1": 2.8,
                    "SA1": 5.0,
                    "TAS1": 2.0,
                }
                raw_spikes = {
                    "NSW1": 50.0,
                    "QLD1": 80.0,
                    "VIC1": 40.0,
                    "SA1": 120.0,
                    "TAS1": 20.0,
                }
                raw_fcas = {
                    "NSW1": 15.0,
                    "QLD1": 12.0,
                    "VIC1": 14.0,
                    "SA1": 20.0,
                    "TAS1": 8.0,
                }

        # Compute saturation and constraint scores (independent of price DB)
        raw_saturation = _compute_saturation_scores()
        raw_constraints = _compute_constraint_scores()

        methodology_notes.append(
            "Saturation scores based on registered BESS capacity / peak load ratio (inverted)."
        )
        methodology_notes.append(
            "Network constraint scores based on historical interconnector constraint patterns (heuristic)."
        )

        # Normalize all dimensions to 0-1 scale
        norm_arbitrage = _normalize_scores(raw_arbitrage)
        norm_spikes = _normalize_scores(raw_spikes)
        norm_fcas = _normalize_scores(raw_fcas)
        norm_saturation = _normalize_scores(raw_saturation)
        norm_constraints = _normalize_scores(raw_constraints)

        # Compute weighted total scores and build rankings
        rankings: list[dict] = []
        for region in NEM_REGIONS:
            dimensions = {
                "arbitrage": round(norm_arbitrage[region], 4),
                "spikes": round(norm_spikes[region], 4),
                "fcas": round(norm_fcas[region], 4),
                "saturation": round(norm_saturation[region], 4),
                "constraints": round(norm_constraints[region], 4),
            }
            total_score = (
                w_arb * dimensions["arbitrage"]
                + w_spk * dimensions["spikes"]
                + w_fcas * dimensions["fcas"]
                + w_sat * dimensions["saturation"]
                + w_con * dimensions["constraints"]
            )
            rankings.append(
                {
                    "region": region,
                    "total_score": round(total_score, 4),
                    "dimensions": dimensions,
                }
            )

        # Sort by total_score descending
        rankings.sort(key=lambda x: x["total_score"], reverse=True)

        # Assign ranks
        for i, entry in enumerate(rankings, start=1):
            entry["rank"] = i

        return RegionalRankingResponse(
            rankings=rankings,
            weights_used={
                "arbitrage": round(w_arb, 4),
                "spikes": round(w_spk, 4),
                "fcas": round(w_fcas, 4),
                "saturation": round(w_sat, 4),
                "constraints": round(w_con, 4),
            },
            data_year=year,
            methodology_notes=methodology_notes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in regional-ranking: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
