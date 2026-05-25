"""Saturation tracking API routes.

Provides BESS capacity saturation analysis for NEM and WEM markets.
Calculates saturation ratios, pipeline ratios, revenue dilution estimates,
and capacity growth timelines.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.1, 10.2, 12.2
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from models.capacity_models import CapacityDataLoader, CapacityDataLoadError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Saturation"])

# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class SaturationResponse(BaseModel):
    """饱和度追踪响应"""

    market: str
    last_updated: str
    regions: list[dict]
    # Each region: {region, registered_mw, pipeline_mw, peak_load_mw,
    #               saturation_ratio, pipeline_ratio, dilution_estimate}
    timeline: list[dict]
    # [{date, region, cumulative_mw, project_name}, ...]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate peak load values (MW) for each region
PEAK_LOAD_MW: dict[str, float] = {
    "NSW1": 14000,
    "QLD1": 10000,
    "VIC1": 10000,
    "SA1": 3500,
    "TAS1": 1800,
    "WEM": 5000,
}

# NEM regions
NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

# WEM regions
WEM_REGIONS = ["WEM"]

# Shared loader instance (cached internally)
_capacity_loader = CapacityDataLoader()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_regions_for_market(market: str) -> list[str]:
    """Return the list of regions for a given market."""
    if market == "NEM":
        return NEM_REGIONS
    elif market == "WEM":
        return WEM_REGIONS
    else:
        return NEM_REGIONS + WEM_REGIONS


def _calculate_dilution_estimate(saturation_ratio: float) -> float:
    """Calculate revenue dilution estimate.

    Simple linear model: dilution_pct = saturation_ratio * 100, capped at 80%.
    Higher saturation means more competition and lower per-unit revenue.

    Args:
        saturation_ratio: registered_mw / peak_load_mw ratio for the region.

    Returns:
        Estimated revenue dilution percentage (0-80%).
    """
    dilution_pct = saturation_ratio * 100
    return min(dilution_pct, 80.0)


def _build_region_saturation(data, region: str) -> dict:
    """Build saturation metrics for a single region."""
    summary = data.get_region_summary(region)
    peak_load = PEAK_LOAD_MW.get(region, 0)

    registered_mw = summary["registered_mw"]
    pipeline_mw = summary["pipeline_mw"]

    saturation_ratio = round(registered_mw / peak_load, 4) if peak_load > 0 else 0.0
    pipeline_ratio = round(pipeline_mw / (registered_mw + 1), 4)
    dilution_estimate = round(_calculate_dilution_estimate(saturation_ratio), 2)

    return {
        "region": region,
        "registered_mw": registered_mw,
        "pipeline_mw": pipeline_mw,
        "peak_load_mw": peak_load,
        "saturation_ratio": saturation_ratio,
        "pipeline_ratio": pipeline_ratio,
        "dilution_estimate": dilution_estimate,
    }


def _build_timeline(data, regions: list[str]) -> list[dict]:
    """Build capacity growth timeline from pipeline projects.

    Returns projects sorted by expected commissioning date, with cumulative MW
    per region.
    """
    # Filter projects in the target regions that have expected commissioning dates
    pipeline_projects = [
        p
        for p in data.projects
        if p.region in regions and p.expected_commissioning_date is not None
    ]

    # Sort by expected commissioning date
    pipeline_projects.sort(key=lambda p: p.expected_commissioning_date)

    # Build cumulative timeline per region
    cumulative: dict[str, float] = {}
    # Initialize with registered capacity
    for region in regions:
        summary = data.get_region_summary(region)
        cumulative[region] = summary["registered_mw"]

    timeline = []
    for project in pipeline_projects:
        region = project.region
        # Only add non-registered projects to the timeline growth
        if project.status != "registered":
            cumulative[region] = cumulative.get(region, 0) + project.capacity_mw

        timeline.append(
            {
                "date": project.expected_commissioning_date.isoformat(),
                "region": region,
                "cumulative_mw": cumulative[region],
                "project_name": project.project_name,
            }
        )

    return timeline


# ---------------------------------------------------------------------------
# Route: GET /api/v1/saturation
# ---------------------------------------------------------------------------


@router.get(
    "/saturation",
    summary="Get BESS capacity saturation data",
    description="Returns capacity saturation metrics, revenue dilution estimates, "
    "and capacity growth timeline for NEM and/or WEM markets.",
    response_model=SaturationResponse,
    responses={
        500: {"description": "Capacity data load failure"},
    },
)
async def get_saturation(
    market: str = Query(default="NEM", description="Market: NEM or WEM"),
    region: Optional[str] = Query(default=None, description="Specific region filter"),
) -> SaturationResponse:
    """获取 BESS 容量饱和度数据。

    计算各区域的饱和度指标（已注册容量/峰值负荷比率）、管道比率、
    收入稀释估算，以及容量增长时间线。
    """
    # Validate market parameter
    if market not in ("NEM", "WEM"):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_MARKET",
                "message": f"Invalid market '{market}'. Must be 'NEM' or 'WEM'.",
                "suggested_action": "Use 'NEM' or 'WEM' as the market parameter.",
            },
        )

    # Validate region parameter if provided
    valid_regions = NEM_REGIONS + WEM_REGIONS
    if region is not None and region not in valid_regions:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "REGION_NOT_FOUND",
                "message": f"Invalid region '{region}'. Valid regions: {valid_regions}",
                "suggested_action": "Use a valid region code (e.g., NSW1, QLD1, VIC1, SA1, TAS1, WEM).",
            },
        )

    # Load capacity data
    try:
        data = _capacity_loader.load()
    except CapacityDataLoadError as exc:
        logger.error("Failed to load capacity data for saturation endpoint: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "CAPACITY_DATA_INVALID",
                "message": "容量数据加载失败，请检查数据源文件。",
                "suggested_action": "Verify capacity_data.json exists and is valid.",
            },
        )

    # Determine which regions to include
    if region is not None:
        target_regions = [region]
    else:
        target_regions = _get_regions_for_market(market)

    # Build region saturation metrics
    regions_data = [_build_region_saturation(data, r) for r in target_regions]

    # Build capacity growth timeline
    timeline = _build_timeline(data, target_regions)

    return SaturationResponse(
        market=market,
        last_updated=data.metadata.last_updated.isoformat(),
        regions=regions_data,
        timeline=timeline,
    )
