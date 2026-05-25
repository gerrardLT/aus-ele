"""Investment Outlook Scenarios API routes.

Provides 4 forward-looking investment analysis endpoints:
- Cannibalization Simulator: revenue dilution from capacity growth
- FCAS Collapse Forecaster: FCAS price ceiling projections
- Regional Timing Scorer: multi-dimensional region investment scoring
- Merchant Risk Quantifier: Monte Carlo revenue distribution

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from deps import get_db
from exceptions import MarketModuleError
from models.capacity_models import CapacityDataLoader
from models.outlook_models import (
    CoalRetirementSchedule,
    CannibalizationResponse,
    FcasCollapseResponse,
    MerchantRiskRequest,
    MerchantRiskResponse,
    RegionalTimingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/outlook", tags=["Investment Outlook"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Shared dependencies (lazy-initialized)
# ---------------------------------------------------------------------------

_capacity_loader = CapacityDataLoader()


def _load_coal_retirement_schedule() -> Optional[CoalRetirementSchedule]:
    """Load coal retirement schedule from JSON data file.

    Returns None if file is missing or invalid (graceful degradation).
    """
    schedule_path = _PROJECT_ROOT / "data" / "coal_retirement_schedule.json"
    try:
        if not schedule_path.exists():
            logger.warning("Coal retirement schedule not found: %s", schedule_path)
            return None
        with open(schedule_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CoalRetirementSchedule(**data)
    except Exception as e:
        logger.warning("Failed to load coal retirement schedule: %s", e)
        return None


def _validate_region(region: str) -> None:
    """Validate that region is a valid NEM region code.

    Raises MarketModuleError if invalid.
    """
    if region not in NEM_REGIONS:
        raise MarketModuleError(
            error_code="INVALID_REGION",
            message=f"Invalid region '{region}'. Valid NEM regions: {NEM_REGIONS}",
            suggested_action="Use a valid NEM region code: NSW1, QLD1, VIC1, SA1, or TAS1.",
            status_code=400,
        )


def _validate_market(market: str) -> None:
    """Validate that market is NEM (only supported market for outlook).

    Raises MarketModuleError if invalid.
    """
    if market != "NEM":
        raise MarketModuleError(
            error_code="INVALID_MARKET",
            message=f"Invalid market '{market}'. Only 'NEM' is supported for outlook endpoints.",
            suggested_action="Use 'NEM' as the market parameter.",
            status_code=400,
        )


# ---------------------------------------------------------------------------
# GET /api/v1/outlook/cannibalization
# ---------------------------------------------------------------------------


@router.get(
    "/cannibalization",
    summary="Simulate revenue cannibalization from capacity growth",
    description=(
        "Uses a power-law dilution model to project how future BESS capacity "
        "additions will erode per-MW revenue for existing projects."
    ),
    response_model=CannibalizationResponse,
)
async def get_cannibalization(
    market: str = Query(default="NEM", description="Market (NEM)"),
    region: str = Query(default="NSW1", description="NEM region code"),
    alpha: float = Query(default=0.6, ge=0.3, le=1.0, description="Dilution exponent"),
    base_revenue: Optional[float] = Query(
        default=None, ge=0, description="Base revenue AUD/MW/year (None = use default)"
    ),
    projection_years: int = Query(default=3, ge=1, le=5, description="Forward projection years"),
) -> CannibalizationResponse:
    """模拟容量增长对现有项目收入的蚕食效应。

    基于幂律模型: revenue_per_mw = base_revenue / (capacity / base_capacity) ^ alpha
    """
    _validate_market(market)
    _validate_region(region)

    try:
        from engines.cannibalization_engine import CannibalizationEngine

        engine = CannibalizationEngine(capacity_loader=_capacity_loader)
        result = engine.simulate(
            region=region,
            base_revenue_per_mw=base_revenue,
            alpha=alpha,
            projection_years=projection_years,
        )
        return result
    except ValueError as e:
        raise MarketModuleError(
            error_code="CANNIBALIZATION_DATA_ERROR",
            message=str(e),
            suggested_action="Check that capacity data exists for the specified region.",
            status_code=400,
        )
    except Exception as e:
        logger.error("Cannibalization engine error: %s", e)
        raise MarketModuleError(
            error_code="CANNIBALIZATION_ENGINE_FAILURE",
            message=f"Failed to compute cannibalization simulation: {e}",
            suggested_action="Check server logs for details. Verify capacity_data.json is valid.",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# GET /api/v1/outlook/fcas-collapse
# ---------------------------------------------------------------------------


@router.get(
    "/fcas-collapse",
    summary="Forecast FCAS price ceiling based on supply-demand ratio",
    description=(
        "Computes price ceilings for 10 FCAS services based on BESS supply vs "
        "market requirement volumes. Uses a decay model with configurable beta."
    ),
    response_model=FcasCollapseResponse,
)
async def get_fcas_collapse(
    market: str = Query(default="NEM", description="Market (NEM)"),
    region: str = Query(default="NEM-wide", description="Region (NEM-wide or specific region)"),
    year: int = Query(default=2025, ge=2020, le=2035, description="Analysis year"),
    beta: float = Query(default=1.5, ge=0.5, le=3.0, description="Collapse steepness parameter"),
) -> FcasCollapseResponse:
    """预测 FCAS 各服务类型的价格天花板。

    核心模型: price = max(0, base_price * (1 - (supply/demand - 1) ^ beta))
    """
    _validate_market(market)
    # Region can be "NEM-wide" or a specific NEM region
    if region != "NEM-wide":
        _validate_region(region)

    try:
        from engines.fcas_collapse_engine import FcasCollapseEngine

        db = get_db()
        engine = FcasCollapseEngine(db=db)
        result = engine.forecast(
            region=region,
            year=year,
            beta=beta,
        )
        return result
    except Exception as e:
        logger.error("FCAS collapse engine error: %s", e)
        raise MarketModuleError(
            error_code="FCAS_COLLAPSE_ENGINE_FAILURE",
            message=f"Failed to compute FCAS collapse forecast: {e}",
            suggested_action="Check server logs. Verify FCAS price data is available in the database.",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# GET /api/v1/outlook/regional-timing
# ---------------------------------------------------------------------------


@router.get(
    "/regional-timing",
    summary="Score NEM regions for forward-looking investment timing",
    description=(
        "Computes multi-dimensional investment attractiveness scores for all NEM regions "
        "based on coal retirement impact, pipeline growth, renewable penetration, "
        "and revenue trajectory."
    ),
    response_model=RegionalTimingResponse,
)
async def get_regional_timing(
    market: str = Query(default="NEM", description="Market (NEM)"),
    target_year: int = Query(default=2026, ge=2024, le=2035, description="Target investment year"),
    weight_coal: float = Query(default=0.30, ge=0, le=1.0, description="Weight for coal retirement dimension"),
    weight_pipeline: float = Query(default=0.25, ge=0, le=1.0, description="Weight for pipeline growth dimension"),
    weight_renewable: float = Query(default=0.20, ge=0, le=1.0, description="Weight for renewable penetration dimension"),
    weight_revenue: float = Query(default=0.25, ge=0, le=1.0, description="Weight for revenue trajectory dimension"),
) -> RegionalTimingResponse:
    """计算各区域的前瞻性投资吸引力评分。

    评分维度: coal_retirement, pipeline_growth, renewable_penetration, revenue_trajectory
    """
    _validate_market(market)

    # Build weights dict
    weights = {
        "coal_retirement": weight_coal,
        "pipeline_growth": weight_pipeline,
        "renewable_penetration": weight_renewable,
        "revenue_trajectory": weight_revenue,
    }

    # Validate weights sum is positive
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise MarketModuleError(
            error_code="INVALID_WEIGHTS",
            message="Sum of dimension weights must be greater than zero.",
            suggested_action="Provide at least one non-zero weight parameter.",
            status_code=400,
        )

    try:
        from engines.regional_timing_engine import RegionalTimingEngine

        db = get_db()
        coal_schedule = _load_coal_retirement_schedule()

        engine = RegionalTimingEngine(
            db=db,
            capacity_loader=_capacity_loader,
            coal_schedule=coal_schedule,
        )
        result = engine.score_regions(
            target_year=target_year,
            weights=weights,
        )
        return result
    except Exception as e:
        logger.error("Regional timing engine error: %s", e)
        raise MarketModuleError(
            error_code="REGIONAL_TIMING_ENGINE_FAILURE",
            message=f"Failed to compute regional timing scores: {e}",
            suggested_action="Check server logs. Verify capacity data and price database are available.",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/outlook/merchant-risk
# ---------------------------------------------------------------------------


@router.post(
    "/merchant-risk",
    summary="Quantify merchant revenue risk via Monte Carlo simulation",
    description=(
        "Runs Monte Carlo resampling on historical daily revenues to generate "
        "P10/P50/P90 revenue distributions and compute minimum contract coverage "
        "needed for bankability."
    ),
    response_model=MerchantRiskResponse,
)
async def post_merchant_risk(
    request: MerchantRiskRequest,
) -> MerchantRiskResponse:
    """基于蒙特卡洛重采样生成收入概率分布。

    计算 P10/P50/P90 分位数和满足银行融资门槛所需的最低合约覆盖率。
    """
    _validate_market(request.market)
    _validate_region(request.region)

    try:
        from engines.merchant_risk_engine import MerchantRiskEngine

        db = get_db()
        engine = MerchantRiskEngine(db=db)
        result = engine.simulate(
            region=request.region,
            power_mw=request.power_mw,
            duration_hours=request.duration_hours,
            round_trip_efficiency=request.round_trip_efficiency,
            n_simulations=request.n_simulations,
            noise_std_pct=request.noise_std_pct,
            dscr=request.dscr,
            bank_contract_pct=request.bank_contract_pct,
            annual_debt_service=request.annual_debt_service,
        )
        return result
    except Exception as e:
        logger.error("Merchant risk engine error: %s", e)
        raise MarketModuleError(
            error_code="MERCHANT_RISK_ENGINE_FAILURE",
            message=f"Failed to compute merchant risk simulation: {e}",
            suggested_action="Check server logs. Verify historical price data is available in the database.",
            status_code=500,
        )
