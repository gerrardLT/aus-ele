"""Forward Price Scenarios API routes.

Provides endpoints for forward price scenario data:
- GET /api/forward-scenarios: Available scenarios and summary parameters
- GET /api/forward-scenarios/{region}: Scenario comparison result for a region

Requirements: 15.4
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Path

from engines.forward_price_engine import ForwardPriceEngine, SUPPORTED_REGIONS
from models.forward_price_models import (
    ScenarioComparisonResult,
    ScenarioDefinition,
    ScenarioType,
)
from models.financial_params import BatterySpecs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Forward Price Scenarios"])


# ---------------------------------------------------------------------------
# GET /api/forward-scenarios
# ---------------------------------------------------------------------------


@router.get(
    "/forward-scenarios",
    summary="Get available forward price scenarios",
    description=(
        "Returns the list of available scenario definitions (Central/High/Low) "
        "with their names, descriptions, and underlying assumptions."
    ),
    response_model=List[ScenarioDefinition],
)
async def get_forward_scenarios() -> List[ScenarioDefinition]:
    """返回可用的前瞻价格情景定义列表。"""
    try:
        from deps import get_forward_price_engine
        engine = get_forward_price_engine()
        return engine.get_scenarios()
    except FileNotFoundError as e:
        # Log the missing path server-side but return an opaque detail so the
        # filesystem location is not disclosed to the client.
        logger.error("Forward-price data dependency unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Data dependency unavailable; please retry later.",
        )


# ---------------------------------------------------------------------------
# GET /api/forward-scenarios/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/forward-scenarios/{region}",
    summary="Get scenario comparison for a region",
    description=(
        "Generates 20-year revenue projections for all three scenarios "
        "(Central/High/Low) in the specified region, enabling side-by-side comparison."
    ),
    response_model=ScenarioComparisonResult,
)
async def get_forward_scenarios_by_region(
    region: str = Path(description="NEM region or WEM (e.g. NSW1, QLD1, VIC1, SA1, TAS1, WEM)"),
) -> ScenarioComparisonResult:
    """返回指定区域的三情景对比结果。"""
    if region not in SUPPORTED_REGIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid region '{region}'. Supported regions: {SUPPORTED_REGIONS}",
        )

    try:
        from deps import get_forward_price_engine
        engine = get_forward_price_engine()
        battery = BatterySpecs()  # Use default battery specs

        central = engine.generate_20year_projection(
            region=region,
            scenario=ScenarioType.CENTRAL,
            battery=battery,
        )
        high = engine.generate_20year_projection(
            region=region,
            scenario=ScenarioType.HIGH,
            battery=battery,
        )
        low = engine.generate_20year_projection(
            region=region,
            scenario=ScenarioType.LOW,
            battery=battery,
        )

        return ScenarioComparisonResult(
            region=region,
            central=central,
            high=high,
            low=low,
        )
    except FileNotFoundError as e:
        # Log the missing path server-side but return an opaque detail so the
        # filesystem location is not disclosed to the client.
        logger.error("Forward-price data dependency unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Data dependency unavailable; please retry later.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )
