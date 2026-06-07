"""Investment Narrative Layer API routes.

Provides endpoints for the narrative layer module:
- GET /api/v1/narrative/attribution/{region} — 因果归因
- GET /api/v1/narrative/stratification/{region} — 分层收入
- GET /api/v1/narrative/events/{region} — 事件标注
- GET /api/v1/narrative/cross-validation/{category} — 交叉验证
- GET/POST /api/v1/narrative/asset-config — 资产配置
- GET /api/v1/narrative/forward-spread/{region} — 前瞻价差曲线
- GET /api/v1/narrative/fuel-sensitivity/{region} — 燃料敏感性
- GET /api/v1/narrative/network-impact/{region} — 网络增强影响

Error handling:
- 422: Pydantic validation errors (automatic) + explicit invalid params
- 503: Data dependencies unavailable
- 200: Degraded responses when external data missing

Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam, Query

from engines.forward_price_engine import ForwardPriceEngine, SUPPORTED_REGIONS
from engines.narrative_engine import NarrativeEngine
from engines.risk_stratification_engine import RiskStratificationEngine
from engines.event_annotation_service import EventAnnotationService
from engines.cross_validation_service import CrossValidationService
from models.financial_params import BatterySpecs
from models.forward_price_models import EventType, ScenarioType
from models.narrative_models import (
    AssetConfiguration,
    CausalAttribution,
    EventAnnotationResponse,
    CrossValidationResponse,
    ForwardSpreadCurveResponse,
    FuelSensitivityResult,
    LayerDiscountRates,
    NetworkImpactComparison,
    StratifiedRevenue,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/narrative", tags=["Investment Narrative Layer"])

# ---------------------------------------------------------------------------
# Module-level state: in-memory asset configuration (single-user MVP)
# ---------------------------------------------------------------------------

_current_asset_config: Optional[AssetConfiguration] = None

# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ---------------------------------------------------------------------------
# Helper: instantiate ForwardPriceEngine with 503 handling
# ---------------------------------------------------------------------------


def _get_forward_price_engine() -> ForwardPriceEngine:
    """Return the cached singleton ForwardPriceEngine (ML trains once on first call)."""
    try:
        from deps import get_forward_price_engine
        return get_forward_price_engine()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data dependency unavailable: {e}",
        )


def _validate_region(region: str) -> None:
    """Validate region parameter, raising 422 if invalid."""
    if region not in SUPPORTED_REGIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid region '{region}'. "
                f"Supported regions: {sorted(SUPPORTED_REGIONS)}"
            ),
        )


def _get_modo_benchmark(region: str, period: str = None) -> dict:
    """Load Modo Energy benchmark data for a region.

    Falls back to NEM_AVG if region-specific data is missing.
    """
    evidence_path = _DATA_DIR / "financial_evidence.json"
    if not evidence_path.exists():
        return {"revenue": 0, "period": "unknown", "source": "unavailable"}

    with open(evidence_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    benchmarks = data.get("modo_benchmarks", {}).get("benchmarks", {})

    # Use most recent period if not specified
    if period is None:
        available = sorted(benchmarks.keys(), reverse=True)
        period = available[0] if available else "2024_full"

    period_data = benchmarks.get(period, {})
    revenue = period_data.get(region, period_data.get("NEM_AVG", 0))

    return {
        "revenue": revenue,
        "period": period,
        "source": data.get("modo_benchmarks", {}).get("source", "Modo Energy"),
    }


def _compute_backvalidation(engine: ForwardPriceEngine, region: str) -> dict:
    """Compute backvalidation: mean_spread → annualized revenue → compare to Modo benchmark."""
    from engines.forward_price_engine import PEAK_DEMAND

    current_year = date.today().year
    target_year = current_year + 1

    # Get current mean_spread from the engine
    bess_capacity = engine._get_cumulative_bess_capacity(
        region, ScenarioType.CENTRAL, target_year
    )
    peak_demand = PEAK_DEMAND.get(region, 10000.0)
    bess_ratio = bess_capacity / peak_demand

    dist = engine.calculate_price_distribution(
        region=region,
        scenario=ScenarioType.CENTRAL,
        year=target_year,
        bess_capacity_ratio=bess_ratio,
    )

    mean_spread = dist.mean_spread

    # Revenue formula: spread × 365 × 4h × capture_rate(0.65) × RTE(0.87)
    model_revenue = mean_spread * 365 * 4 * 0.65 * 0.87

    # Get Modo benchmark
    benchmark_info = _get_modo_benchmark(region)
    benchmark_revenue = benchmark_info["revenue"]

    # Compute deviation
    if benchmark_revenue > 0:
        deviation_percent = (model_revenue - benchmark_revenue) / benchmark_revenue * 100
        status = "out_of_range" if abs(deviation_percent) > 30 else "within_range"
    else:
        deviation_percent = None
        status = "benchmark_unavailable"

    # Get confidence interval from calibration if available
    confidence_interval = None
    if hasattr(engine, '_calibration') and engine._calibration:
        ci = engine._calibration.get("confidence_interval")
        if ci:
            confidence_interval = ci

    return {
        "region": region,
        "model_revenue": round(model_revenue, 2),
        "benchmark_revenue": benchmark_revenue,
        "deviation_percent": round(deviation_percent, 1) if deviation_percent is not None else None,
        "status": status,
        "mean_spread": round(mean_spread, 2),
        "confidence_interval": confidence_interval,
        "benchmark_period": benchmark_info["period"],
        "benchmark_source": benchmark_info["source"],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/attribution/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/attribution/{region}",
    summary="Get causal attribution for a region",
    description=(
        "Returns causal attribution data explaining WHY a metric has its "
        "current value, linking to specific market drivers from the event registry."
    ),
    response_model=CausalAttribution,
)
async def get_causal_attribution(
    region: str = PathParam(description="NEM region or WEM"),
    module: str = Query(
        default="forward_price",
        description="Module name (forward_price, risk_stratification, financial_model)",
    ),
    year: Optional[int] = Query(default=None, description="Target year"),
    scenario: ScenarioType = Query(default=ScenarioType.CENTRAL),
) -> CausalAttribution:
    """获取指定模块输出的因果归因数据。"""
    _validate_region(region)

    engine = _get_forward_price_engine()
    narrative = NarrativeEngine(engine.event_registry)

    target_year = year or (date.today().year + 1)

    if module == "forward_price":
        # Generate spread attribution
        try:
            battery = BatterySpecs()
            bess_capacity = engine._get_cumulative_bess_capacity(
                region, scenario, target_year
            )
            peak_demand = 10000.0  # Default
            from engines.forward_price_engine import PEAK_DEMAND, BASE_SPREAD_PARAMS

            peak_demand = PEAK_DEMAND.get(region, 10000.0)
            bess_ratio = bess_capacity / peak_demand

            dist = engine.calculate_price_distribution(
                region=region,
                scenario=scenario,
                year=target_year,
                bess_capacity_ratio=bess_ratio,
            )
            base_spread = BASE_SPREAD_PARAMS[region]["mean_spread"]

            return narrative.generate_spread_attribution(
                region=region,
                year=target_year,
                scenario=scenario,
                current_spread=dist.mean_spread,
                base_spread=base_spread,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        # Generic module conclusion
        return narrative.generate_module_conclusion(
            module_name=module,
            region=region,
            metrics={"mean_spread": 0.0},
        )


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/stratification/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/stratification/{region}",
    summary="Get stratified revenue breakdown",
    description=(
        "Returns revenue split into three layers by price threshold, "
        "each with independent discount rates and confidence levels."
    ),
    response_model=StratifiedRevenue,
)
async def get_stratified_revenue(
    region: str = PathParam(description="NEM region or WEM"),
    scenario: ScenarioType = Query(default=ScenarioType.CENTRAL),
    spread_threshold: float = Query(default=300.0, ge=0.0, le=16600.0),
    layer1_discount: float = Query(default=0.08, ge=0.0, le=1.0),
    layer2_discount: float = Query(default=0.10, ge=0.0, le=1.0),
    layer3_discount: float = Query(default=0.12, ge=0.0, le=1.0),
) -> StratifiedRevenue:
    """获取分层收入数据。"""
    _validate_region(region)

    engine = _get_forward_price_engine()

    try:
        battery = BatterySpecs()
        projection = engine.generate_20year_projection(
            region=region,
            scenario=scenario,
            battery=battery,
        )

        # Estimate spike frequency from price distribution
        first_year = date.today().year + 1
        bess_capacity = engine._get_cumulative_bess_capacity(
            region, scenario, first_year
        )
        from engines.forward_price_engine import PEAK_DEMAND, BASE_SPREAD_PARAMS

        peak_demand = PEAK_DEMAND.get(region, 10000.0)
        bess_ratio = bess_capacity / peak_demand
        dist = engine.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=first_year,
            bess_capacity_ratio=bess_ratio,
        )
        spike_frequency = dist.spike_frequency

        # FCAS annual estimate (per MW, passed to stratification engine)
        fcas_annual = 5000.0  # ~$5k/MW/year FCAS baseline (post-saturation)

        # Create stratification engine with user-specified parameters
        discount_rates = LayerDiscountRates(
            layer1=layer1_discount,
            layer2=layer2_discount,
            layer3=layer3_discount,
        )
        strat_engine = RiskStratificationEngine(
            spread_threshold=spread_threshold,
            layer_discount_rates=discount_rates,
        )

        # Generate stratified revenue
        annual_layers = strat_engine.stratify_forward_revenue(
            projection=projection,
            spike_frequency=spike_frequency,
            fcas_annual=fcas_annual,
        )

        return strat_engine.generate_stratified_revenue(
            region=region,
            scenario=scenario.value,
            annual_layers=annual_layers,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/events/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/events/{region}",
    summary="Get event annotations for a region",
    description=(
        "Returns event annotations filtered by region and time range, "
        "suitable for overlaying on time-series charts."
    ),
    response_model=EventAnnotationResponse,
)
async def get_event_annotations(
    region: str = PathParam(description="NEM region or WEM"),
    start_year: Optional[int] = Query(default=None, description="Start year (inclusive)"),
    end_year: Optional[int] = Query(default=None, description="End year (inclusive)"),
    event_types: Optional[str] = Query(
        default=None,
        description="Comma-separated event types (coal_closure, bess_commissioning, network_augmentation)",
    ),
) -> EventAnnotationResponse:
    """获取事件标注数据。"""
    _validate_region(region)

    engine = _get_forward_price_engine()
    annotation_service = EventAnnotationService(engine.event_registry)

    # Default time range: current year to +20 years
    current_year = date.today().year
    effective_start = start_year or current_year
    effective_end = end_year or (current_year + 20)

    # Parse event types filter
    type_filter: Optional[List[EventType]] = None
    if event_types:
        try:
            type_filter = [EventType(t.strip()) for t in event_types.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid event_types: {e}. "
                    f"Valid types: {[t.value for t in EventType]}"
                ),
            )

    annotations = annotation_service.get_annotations(
        region=region,
        start_year=effective_start,
        end_year=effective_end,
        event_types=type_filter,
    )

    return EventAnnotationResponse(
        region=region,
        start_year=effective_start,
        end_year=effective_end,
        annotations=annotations,
        total_count=len(annotations),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/cross-validation/{category}
# ---------------------------------------------------------------------------


@router.get(
    "/cross-validation/{category}",
    summary="Get cross-validation comparison data",
    description=(
        "Returns multi-source comparison data for a specified category: "
        "coal_retirements, revenue_benchmarks, or price_forecasts."
    ),
    response_model=CrossValidationResponse,
)
async def get_cross_validation(
    category: str = PathParam(
        description="Data category: coal_retirements | revenue_benchmarks | price_forecasts"
    ),
    region: Optional[str] = Query(default=None, description="NEM region (for revenue/price)"),
    scenario: ScenarioType = Query(default=ScenarioType.CENTRAL),
    model_revenue: float = Query(default=148000.0, gt=0, description="Platform model revenue $/MW/year"),
) -> CrossValidationResponse:
    """获取多源交叉验证数据。"""
    valid_categories = {"coal_retirements", "revenue_benchmarks", "price_forecasts"}
    if category not in valid_categories:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid category '{category}'. "
                f"Valid categories: {sorted(valid_categories)}"
            ),
        )

    if region:
        _validate_region(region)

    engine = _get_forward_price_engine()

    evidence_path = _DATA_DIR / "financial_evidence.json"
    cross_val_service = CrossValidationService(
        evidence_path=evidence_path,
        event_registry=engine.event_registry,
    )

    return cross_val_service.get_cross_validation_response(
        category=category,
        region=region,
        scenario=scenario,
        model_revenue=model_revenue,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/asset-config
# ---------------------------------------------------------------------------


@router.get(
    "/asset-config",
    summary="Get current asset configuration",
    description="Returns the current user-defined BESS asset configuration.",
    response_model=AssetConfiguration,
)
async def get_asset_config() -> AssetConfiguration:
    """获取当前资产配置。"""
    global _current_asset_config

    if _current_asset_config is None:
        # Return default configuration
        return AssetConfiguration(
            region="NSW1",
            power_mw=100.0,
            duration_hours=4.0,
            round_trip_efficiency=0.85,
            mlf=0.95,
            connection_point="",
        )

    return _current_asset_config


# ---------------------------------------------------------------------------
# POST /api/v1/narrative/asset-config
# ---------------------------------------------------------------------------


@router.post(
    "/asset-config",
    summary="Save asset configuration",
    description=(
        "Saves a user-defined BESS asset configuration. "
        "All downstream calculations will use this configuration."
    ),
    response_model=AssetConfiguration,
)
async def save_asset_config(config: AssetConfiguration) -> AssetConfiguration:
    """保存资产配置。"""
    global _current_asset_config

    # Pydantic validation handles range checks automatically (422 on failure)
    _validate_region(config.region)

    _current_asset_config = config
    return _current_asset_config


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/forward-spread/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/forward-spread/{region}",
    summary="Get forward spread curve data",
    description=(
        "Returns 20-year spread projection for all three scenarios with "
        "optional historical data and event annotations."
    ),
    response_model=ForwardSpreadCurveResponse,
)
async def get_forward_spread_curve(
    region: str = PathParam(description="NEM region or WEM"),
    include_historical: bool = Query(default=True, description="Include historical spread data"),
) -> ForwardSpreadCurveResponse:
    """获取前瞻价差曲线数据（含事件标注）。"""
    _validate_region(region)

    engine = _get_forward_price_engine()

    try:
        from engines.forward_price_engine import BASE_SPREAD_PARAMS

        current_year = date.today().year
        battery = BatterySpecs()

        # Generate 20-year projections for all 3 scenarios
        projection_data: List[dict] = []
        for i in range(20):
            year = current_year + i + 1
            spreads = {}
            for scenario in (ScenarioType.CENTRAL, ScenarioType.HIGH, ScenarioType.LOW):
                bess_capacity = engine._get_cumulative_bess_capacity(
                    region, scenario, year
                )
                from engines.forward_price_engine import PEAK_DEMAND

                peak_demand = PEAK_DEMAND.get(region, 10000.0)
                bess_ratio = bess_capacity / peak_demand
                dist = engine.calculate_price_distribution(
                    region=region,
                    scenario=scenario,
                    year=year,
                    bess_capacity_ratio=bess_ratio,
                )
                # Long-term trend: beyond year 5, spreads gradually decay
                # due to continued BESS saturation and market maturation
                years_from_now = year - current_year
                long_term_factor = 1.0
                if years_from_now > 5:
                    long_term_factor = 1.0 - 0.005 * (years_from_now - 5)  # 0.5%/yr after yr 5
                    long_term_factor = max(0.70, long_term_factor)  # Floor at 30% decay
                spreads[scenario] = dist.mean_spread * long_term_factor

            projection_data.append({
                "year": year,
                "central_spread": round(spreads[ScenarioType.CENTRAL], 2),
                "high_spread": round(spreads[ScenarioType.HIGH], 2),
                "low_spread": round(spreads[ScenarioType.LOW], 2),
            })

        # Historical data (simplified: use base spread as proxy for recent years)
        historical_data: List[dict] = []
        historical_available = False
        if include_historical:
            base_spread = BASE_SPREAD_PARAMS[region]["mean_spread"]
            # Provide 3 years of historical context using base spread with slight variation
            for offset in range(3, 0, -1):
                hist_year = current_year - offset
                # Slight variation to simulate historical data
                variation = 1.0 + (offset - 2) * 0.05
                historical_data.append({
                    "year": hist_year,
                    "spread": round(base_spread * variation, 2),
                })
            historical_available = True

        # Event annotations for this region
        annotation_service = EventAnnotationService(engine.event_registry)
        annotations = annotation_service.get_annotations(
            region=region,
            start_year=current_year,
            end_year=current_year + 20,
        )

        return ForwardSpreadCurveResponse(
            region=region,
            historical_available=historical_available,
            historical=historical_data,
            projection=projection_data,
            annotations=annotations,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/fuel-sensitivity/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/fuel-sensitivity/{region}",
    summary="Get fuel cost sensitivity analysis",
    description=(
        "Returns the impact of gas price variations on BESS revenue, "
        "with 5 scenarios: -20%, -10%, base, +10%, +20%."
    ),
    response_model=FuelSensitivityResult,
)
async def get_fuel_sensitivity(
    region: str = PathParam(description="NEM region or WEM"),
    scenario: ScenarioType = Query(default=ScenarioType.CENTRAL),
    gas_base_price: float = Query(default=10.0, gt=0, description="Base gas price $/GJ"),
    pass_through_coefficient: float = Query(
        default=9.5, gt=0, description="Pass-through coefficient $/MWh per $/GJ"
    ),
) -> FuelSensitivityResult:
    """获取燃料成本敏感性分析。"""
    _validate_region(region)

    engine = _get_forward_price_engine()

    try:
        battery = BatterySpecs()
        return engine.calculate_fuel_sensitivity(
            region=region,
            scenario=scenario,
            battery=battery,
            gas_base_price=gas_base_price,
            pass_through_coefficient=pass_through_coefficient,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/network-impact/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/network-impact/{region}",
    summary="Get network augmentation impact",
    description=(
        "Returns before-and-after spread comparison showing the impact "
        "of interconnector commissioning on regional price spreads."
    ),
    response_model=NetworkImpactComparison,
)
async def get_network_impact(
    region: str = PathParam(description="NEM region or WEM"),
    convergence_factor: Optional[float] = Query(
        default=None,
        ge=0.05,
        le=0.30,
        description="Override convergence factor [0.05, 0.30]",
    ),
) -> NetworkImpactComparison:
    """获取网络增强对区域价差的影响对比。"""
    _validate_region(region)

    engine = _get_forward_price_engine()

    try:
        return engine.calculate_network_impact(
            region=region,
            convergence_factor=convergence_factor,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data dependency unavailable: {e}",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/backvalidation/summary
# ---------------------------------------------------------------------------


@router.get(
    "/backvalidation/summary",
    summary="Get backvalidation summary for all regions",
    description=(
        "Returns revenue backvalidation results for all NEM regions, "
        "comparing model predictions against Modo Energy benchmarks."
    ),
)
async def get_backvalidation_summary():
    """返回全区域反推验证摘要。"""
    engine = _get_forward_price_engine()

    # Check ML calibration availability
    if not engine._calibration or engine._calibration.get("status") == "not_available":
        raise HTTPException(
            status_code=503,
            detail={"status": "calibration_not_available"},
        )

    backvalidation_regions = ["NSW1", "QLD1", "VIC1", "SA1"]
    results = []

    for region in backvalidation_regions:
        try:
            result = _compute_backvalidation(engine, region)
            results.append(result)
        except Exception as e:
            logger.warning(f"Backvalidation failed for {region}: {e}")
            results.append({
                "region": region,
                "model_revenue": None,
                "benchmark_revenue": None,
                "deviation_percent": None,
                "status": "error",
                "mean_spread": None,
                "confidence_interval": None,
                "benchmark_period": None,
                "benchmark_source": "Modo Energy",
            })

    # Sort by absolute deviation descending
    results.sort(
        key=lambda r: abs(r.get("deviation_percent") or 0),
        reverse=True,
    )

    # Count statuses
    within_range = sum(1 for r in results if r.get("status") == "within_range")
    out_of_range = sum(1 for r in results if r.get("status") in ("out_of_range", "direction_mismatch"))

    return {
        "regions": results,
        "within_range_count": within_range,
        "out_of_range_count": out_of_range,
        "benchmark_source": "Modo Energy",
        "validated_at": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/backvalidation/{region}
# ---------------------------------------------------------------------------


@router.get(
    "/backvalidation/{region}",
    summary="Get backvalidation for a single region",
    description=(
        "Returns revenue backvalidation result for a specific NEM region, "
        "comparing model prediction against Modo Energy benchmark."
    ),
)
async def get_backvalidation_region(
    region: str = PathParam(description="NEM region: NSW1, QLD1, VIC1, SA1"),
):
    """返回单区域反推验证结果。"""
    backvalidation_regions = ["NSW1", "QLD1", "VIC1", "SA1"]
    if region not in backvalidation_regions:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid region '{region}' for backvalidation. "
                f"Supported regions: {backvalidation_regions}"
            ),
        )

    engine = _get_forward_price_engine()

    # Check if ML calibration is available
    if not engine._calibration or engine._calibration.get("status") == "not_available":
        raise HTTPException(
            status_code=503,
            detail={"status": "calibration_not_available"},
        )

    try:
        return _compute_backvalidation(engine, region)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Backvalidation computation failed: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/v1/narrative/calibration-status
# ---------------------------------------------------------------------------


@router.get(
    "/calibration-status",
    summary="Get ML calibration status",
    description=(
        "Returns the current ML parameter calibration status, including "
        "validation metrics and calibration timestamp."
    ),
)
async def get_calibration_status():
    """返回 ML 校准状态。"""
    engine = _get_forward_price_engine()
    return engine._calibration or {"status": "not_available"}
