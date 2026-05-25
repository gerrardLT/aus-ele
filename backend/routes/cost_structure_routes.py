"""Cost Structure API routes.

Provides BESS fee component decomposition for NEM and WEM regions.
Returns annual cost breakdown with FIXED/VARIABLE classification
and region-specific fee parameters.

Requirements: 15.1
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from engines.cost_structure_engine import CostStructureEngine, SUPPORTED_REGIONS
from models.cost_structure_models import AnnualCostBreakdown, ConnectionType
from models.financial_params import BatterySpecs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Cost Structure"])


@router.get(
    "/cost-structure/{region}",
    summary="Get BESS cost structure breakdown for a region",
    description="Returns the default annual fee breakdown for a specified NEM/WEM region, "
    "decomposed into FIXED and VARIABLE components with line-item detail.",
    response_model=AnnualCostBreakdown,
    responses={
        422: {"description": "Invalid region code"},
    },
)
async def get_cost_structure(
    region: str,
    power_mw: float = Query(default=100.0, description="Battery power capacity in MW"),
    duration_hours: float = Query(default=4.0, description="Battery duration in hours"),
    annual_throughput_mwh: float = Query(
        default=200000.0, description="Total annual energy throughput in MWh"
    ),
    connection_type: ConnectionType = Query(
        default=ConnectionType.TRANSMISSION,
        description="Grid connection type (transmission or distribution)",
    ),
) -> AnnualCostBreakdown:
    """获取指定区域的 BESS 费用结构分解。

    计算年度费用明细，区分 FIXED 和 VARIABLE 组件，
    包含 AEMO 参与者费用、TUOS、DUOS、MLF、FPP 等。
    """
    # Validate region
    if region not in SUPPORTED_REGIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_REGION",
                "message": f"Invalid region '{region}'. Supported regions: {SUPPORTED_REGIONS}",
                "suggested_action": "Use a valid region code (e.g., NSW1, QLD1, VIC1, SA1, TAS1, WEM).",
            },
        )

    battery = BatterySpecs(power_mw=power_mw, duration_hours=duration_hours)

    breakdown = CostStructureEngine.calculate_annual_costs(
        battery=battery,
        region=region,
        annual_throughput_mwh=annual_throughput_mwh,
        connection_type=connection_type,
    )

    return breakdown
