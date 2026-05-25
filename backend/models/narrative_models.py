"""Investment Narrative Layer data models.

Provides Pydantic models for the Narrative Layer module:
- Causal attribution models (因果归因模型)
- Risk stratification models (风险分层模型)
- Event annotation models (事件标注模型)
- Cross-validation models (交叉验证模型)
- Fuel sensitivity models (燃料敏感性模型)
- Asset configuration model (资产配置模型)
- Forward spread curve response (前瞻价差曲线响应)
- Network augmentation models (网络增强模型)

Requirements: 15.1, 15.2, 16.1, 16.2, 8.4, 17.1-17.5
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from models.forward_price_models import EventConfidence, EventType


# =============================================================================
# Causal Attribution Models (因果归因)
# =============================================================================


class DriverType(str, Enum):
    """因果驱动因素类型。"""

    COAL_CLOSURE = "coal_closure"
    BESS_SATURATION = "bess_saturation"
    NETWORK_AUGMENTATION = "network_augmentation"
    GAS_PRICE = "gas_price"
    DEMAND_GROWTH = "demand_growth"
    FCAS_COLLAPSE = "fcas_collapse"


class CausalFactor(BaseModel):
    """单个因果因素。

    Represents a single causal driver contributing to a metric's value,
    with its contribution amount and source reference for traceability.
    """

    driver_name: str = Field(description="驱动因素名称，如 'Eraring closure'")
    driver_type: DriverType
    contribution_amount: float = Field(description="对指标的贡献量（$/MWh 或 $）")
    contribution_pct: Optional[float] = Field(None, description="贡献百分比")
    source_reference: str = Field(description="数据来源引用")


class CausalAttribution(BaseModel):
    """因果归因对象，可序列化为 JSON。

    Contains the full causal explanation for a metric value, including
    the narrative text and structured causal factors for API transmission.
    """

    metric_name: str = Field(description="指标名称，如 'mean_spread'")
    metric_value: float
    metric_unit: str = Field(default="$/MWh")
    narrative_text: str = Field(description="人类可读的因果解释文本")
    causal_factors: List[CausalFactor]
    region: str
    year: int
    scenario: Optional[str] = None


# =============================================================================
# Risk Stratification Models (风险分层)
# =============================================================================


class ConfidenceLevel(str, Enum):
    """收入层级置信度等级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LayerDiscountRates(BaseModel):
    """各层折现率配置。

    Configurable discount rates for each revenue layer, with defaults
    reflecting the risk profile: Layer 1 (8%), Layer 2 (10%), Layer 3 (12%).
    """

    layer1: float = Field(default=0.08, ge=0.0, le=1.0, description="基础套利层折现率")
    layer2: float = Field(default=0.10, ge=0.0, le=1.0, description="FCAS 层折现率")
    layer3: float = Field(default=0.12, ge=0.0, le=1.0, description="极端事件层折现率")


class RevenueLayer(BaseModel):
    """单层收入数据。

    Represents one revenue layer's data for a single year, including
    its confidence level, applied discount rate, and contribution metrics.
    """

    layer_number: int = Field(ge=1, le=3)
    name: str
    confidence: ConfidenceLevel
    discount_rate: float = Field(ge=0.0, le=1.0)
    amount: float = Field(ge=0.0)
    percentage: float = Field(ge=0.0, le=100.0)


class AnnualStratifiedRevenue(BaseModel):
    """单年分层收入。

    Contains the three-layer revenue breakdown for a single year,
    with each layer's amount, confidence, and percentage contribution.
    """

    year: int
    layer1: RevenueLayer
    layer2: RevenueLayer
    layer3: RevenueLayer
    total_revenue: float = Field(ge=0.0)


class StratifiedRevenue(BaseModel):
    """完整分层收入结果（可序列化）。

    Full 20-year stratified revenue breakdown for a region and scenario,
    including layer-weighted NPV comparison with standard single-rate NPV.
    """

    region: str
    scenario: str
    spread_threshold: float = Field(default=300.0, ge=0.0, le=16600.0)
    discount_rates: LayerDiscountRates
    annual_layers: List[AnnualStratifiedRevenue]
    layer_weighted_npv: float
    standard_npv: float
    npv_difference: float = Field(description="layer_weighted_npv - standard_npv")


class LayerWeightedNPV(BaseModel):
    """分层加权 NPV 结果。

    Breakdown of NPV by layer, enabling comparison between the
    layer-weighted approach and a standard single-rate discount.
    """

    layer1_npv: float
    layer2_npv: float
    layer3_npv: float
    total_layer_weighted_npv: float
    standard_single_rate_npv: float
    difference_pct: float


# =============================================================================
# Event Annotation Models (事件标注)
# =============================================================================


class EventAnnotation(BaseModel):
    """单个事件标注。

    Represents a supply-demand event positioned on a time-series chart,
    with visual properties (type determines marker shape/color) and
    impact metadata for the detail panel.
    """

    event_name: str
    event_type: EventType
    region: str
    date: date
    capacity_mw: float
    confidence: EventConfidence
    spread_impact_factor: float
    description: Optional[str] = None


class EventCluster(BaseModel):
    """聚类事件标记。

    When multiple events fall within the same pixel range on a chart,
    they are clustered into a single marker showing the count.
    """

    center_date: date
    event_count: int
    events: List[EventAnnotation]
    dominant_type: EventType


class EventAnnotationResponse(BaseModel):
    """事件标注 API 响应。

    Response format for the event annotations endpoint, containing
    filtered events for a specific region and time range.
    """

    region: str
    start_year: int
    end_year: int
    annotations: List[EventAnnotation]
    total_count: int


# =============================================================================
# Cross-Validation Models (交叉验证)
# =============================================================================


class CrossValidationEntry(BaseModel):
    """单个交叉验证条目。

    Represents one data source's value for a cross-validated data point,
    with discrepancy calculation and staleness detection.
    """

    data_point: str = Field(description="数据点名称")
    category: str = Field(
        description="coal_retirements | revenue_benchmarks | price_forecasts"
    )
    source_name: str
    source_date: date
    source_url: Optional[str] = None
    reported_value: str
    platform_value: str
    discrepancy_pct: Optional[float] = Field(None, description="差异百分比")
    is_stale: bool = Field(default=False, description="来源超过 12 个月未更新")


class CrossValidationResponse(BaseModel):
    """交叉验证 API 响应。

    Response format for the cross-validation endpoint, containing
    all comparison entries for a specific data category.
    """

    category: str
    entries: List[CrossValidationEntry]
    last_updated: date


# =============================================================================
# Fuel Sensitivity Models (燃料敏感性)
# =============================================================================


class GasPriceAssumptions(BaseModel):
    """天然气价格假设。

    User-configurable gas price parameters for fuel cost sensitivity
    analysis. Defaults sourced from financial_evidence.json.
    """

    base_price_per_gj: float = Field(default=10.0, gt=0, description="基础气价 $/GJ")
    annual_escalation_rate: float = Field(default=0.02, ge=0.0, le=0.20)
    pass_through_coefficient: float = Field(
        default=9.5,
        gt=0,
        description="传导系数：$/MWh per $/GJ (范围 7-12)",
    )


class FuelSensitivityScenario(BaseModel):
    """单个敏感性情景。

    One of the 5 gas price sensitivity scenarios (-20%, -10%, base,
    +10%, +20%) with its calculated revenue impact.
    """

    gas_price_change_pct: float = Field(description="-20, -10, 0, +10, +20")
    gas_price: float
    peak_price_impact: float = Field(description="$/MWh 变化")
    revenue_impact: float = Field(description="$ 变化")
    revenue_change_pct: float


class FuelSensitivityResult(BaseModel):
    """燃料敏感性分析结果。

    Complete fuel sensitivity analysis output for a region and scenario,
    including the sensitivity coefficient and all 5 scenario results.
    """

    region: str
    scenario: str
    base_revenue: float
    sensitivity_coefficient: float = Field(
        description="BESS 年收入变化% / 气价变化 10%"
    )
    scenarios: List[FuelSensitivityScenario]


# =============================================================================
# Asset Configuration Model (资产配置)
# =============================================================================


class AssetConfiguration(BaseModel):
    """用户资产配置。

    User-defined BESS project parameters that customize all downstream
    calculations. Validates physically realistic ranges for all inputs.
    """

    region: str = Field(description="NEM region or WEM")
    power_mw: float = Field(ge=1.0, le=2000.0)
    duration_hours: float = Field(ge=0.5, le=12.0)
    round_trip_efficiency: float = Field(ge=0.70, le=0.95)
    mlf: float = Field(ge=0.80, le=1.10)
    connection_point: str = Field(default="", description="接入点标识")

    @property
    def capacity_mwh(self) -> float:
        """Total energy capacity in MWh."""
        return self.power_mw * self.duration_hours

    @property
    def label(self) -> str:
        """Human-readable asset label containing key parameters."""
        return f"{self.power_mw:.0f}MW/{self.duration_hours:.0f}h BESS at {self.region}"


# =============================================================================
# Forward Spread Curve Response (前瞻价差曲线)
# =============================================================================


class ForwardSpreadCurveResponse(BaseModel):
    """前瞻价差曲线 API 响应。

    Response format for the forward spread curve endpoint, containing
    historical data (when available), 20-year projections, and event
    annotations for the specified region.
    """

    region: str
    historical_available: bool
    historical: List[dict] = Field(default_factory=list, description="[{year, spread}]")
    projection: List[dict] = Field(
        default_factory=list,
        description="[{year, central_spread, high_spread, low_spread}]",
    )
    annotations: List[EventAnnotation] = Field(default_factory=list)


# =============================================================================
# Network Augmentation Models (网络增强)
# =============================================================================


class NetworkAugmentationEvent(BaseModel):
    """网络增强事件。

    Represents an interconnector commissioning event that reduces
    regional price spreads through market convergence.
    """

    name: str
    from_region: str
    to_region: str
    capacity_mw: float
    expected_date: date
    convergence_factor: float = Field(ge=0.05, le=0.30)
    spread_impact_factor: float = Field(lt=1.0, description="< 1 表示价差压缩")


class NetworkImpactComparison(BaseModel):
    """网络增强前后对比。

    Before-and-after comparison showing the projected spread with
    and without an interconnector commissioning event.
    """

    project_name: str
    region: str
    spread_before: List[dict] = Field(description="[{year, spread}]")
    spread_after: List[dict] = Field(description="[{year, spread}]")
    reduction_pct: float
