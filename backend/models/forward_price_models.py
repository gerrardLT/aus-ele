"""Forward Price Scenario Engine data models.

Provides Pydantic models for the Forward Price Engine module:
- Supply-demand event registry (供需事件注册表)
- Price distribution parameters (价格分布参数)
- Scenario projections (情景预测)
- Scenario definitions and comparison (情景定义与对比)

Requirements: 7.2, 8.1, 8.2, 8.6, 9.1, 9.2, 9.3, 13.1
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class ScenarioType(str, Enum):
    """Three-scenario framework types aligned with AEMO ISP paths."""

    CENTRAL = "central"
    HIGH = "high"
    LOW = "low"


class EventType(str, Enum):
    """Supply-demand event categories affecting future price distributions."""

    COAL_CLOSURE = "coal_closure"
    BESS_COMMISSIONING = "bess_commissioning"
    RENEWABLE_BUILDOUT = "renewable_buildout"
    NETWORK_AUGMENTATION = "network_augmentation"


class EventConfidence(str, Enum):
    """Confidence level for supply-demand events."""

    CONFIRMED = "confirmed"
    ANNOUNCED = "announced"
    SPECULATED = "speculated"


# =============================================================================
# Supply-Demand Event Models
# =============================================================================


class SupplyDemandEvent(BaseModel):
    """供需事件注册表条目。

    Each event represents a known future market change (coal closure,
    BESS commissioning, or renewable buildout) with its expected impact
    on daily price spread distribution.
    """

    event_type: EventType
    name: str
    region: str
    expected_date: date
    capacity_mw: float = Field(gt=0, description="Event capacity in MW")
    confidence: EventConfidence
    spread_impact_factor: float = Field(
        description="对 daily spread 的乘性影响因子。>1 增加 spread，<1 压缩 spread"
    )


class EventRegistry(BaseModel):
    """供需事件注册表。

    Contains all known future supply-demand events and the date
    the registry was last updated.
    """

    events: List[SupplyDemandEvent]
    last_updated: date


# =============================================================================
# Price Distribution Models
# =============================================================================


class PriceDistribution(BaseModel):
    """单年价格分布参数。

    Characterizes the daily price spread distribution for a specific
    region, scenario, and year. Used by the Forward Price Engine to
    estimate BESS arbitrage revenue potential.
    """

    year: int
    region: str
    scenario: ScenarioType
    mean_spread: float = Field(ge=0, le=10000, description="日均价差 $/MWh")
    std_dev: float = Field(ge=0, le=5000, description="标准差 $/MWh")
    spike_frequency: float = Field(ge=0.0, le=1.0, description="价格尖峰频率")
    compression_factor: float = Field(ge=0.0, le=1.0, description="BESS 饱和压缩因子（目标年绝对饱和度）")
    # 实际施加到 mean_spread 上的压缩：ML 校准锚点年后的前瞻方向为增量压缩
    # compression(target)/compression(anchor)，否则等于 compression_factor。
    # capture_rate 衍生计算必须用本字段而非绝对因子，避免重放历史压缩。
    applied_compression: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="实际施加于 mean_spread 的压缩（前瞻=增量，历史/未校准=绝对）",
    )
    capture_rate: float = Field(ge=0.0, le=1.0, description="BESS 价差捕获率")


# =============================================================================
# FCAS Revenue Models
# =============================================================================


class FcasRevenueComponent(BaseModel):
    """FCAS 收入分量（独立于能量套利）。

    Represents the Frequency Control Ancillary Services revenue component
    for a specific year, separated from energy arbitrage revenue.
    When computation fails, degraded=True and revenue defaults to 0.0.
    """

    year: int
    fcas_revenue_per_mw: float = Field(ge=0.0, description="FCAS 年收入 $/MW")
    ceiling_per_mw_year: float = Field(ge=0.0, description="FCAS 价格天花板 $/MW/yr")
    degraded: bool = Field(default=False, description="是否降级（计算失败时为 True）")


# =============================================================================
# Revenue Projection Models
# =============================================================================


class AnnualRevenueProjection(BaseModel):
    """单年收入预测。

    Represents the estimated revenue for a single year within a
    20-year scenario projection, accounting for state-of-health
    degradation and price distribution parameters.
    """

    year: int
    estimated_revenue_per_mw: float
    state_of_health: float
    mean_spread: float
    capture_rate: float
    # --- 新增可选字段（向后兼容）---
    fcas_revenue_per_mw: Optional[float] = None
    structural_risks: List[str] = Field(default_factory=list)
    effective_peak_demand: Optional[float] = None
    duration_efficiency_factor: Optional[float] = None
    autobidder_decay: Optional[float] = None
    # 可达成口径（2026-08-05）：merchant 套利收入 × 实测调度效率折扣。
    # 实测来源：历史 pre-dispatch 闭环滚动回测（详见
    # engines/dispatch_efficiency.py 模块注释）。None = 未启用。
    achievable_revenue_per_mw: Optional[float] = None


class ScenarioProjection(BaseModel):
    """单情景 20 年收入预测。

    Contains the full 20-year revenue projection for a single scenario
    (Central, High, or Low) in a specific region, including aggregate
    metrics (total revenue and NPV per MW).
    """

    scenario: ScenarioType
    region: str
    annual_projections: List[AnnualRevenueProjection]
    total_revenue_per_mw: float
    npv_per_mw: float
    # --- 新增可选字段 ---
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# Scenario Definition Models
# =============================================================================


class ScenarioDefinition(BaseModel):
    """情景定义摘要。

    Describes a scenario's name, purpose, and underlying assumptions
    for display in the frontend ScenarioSelector component.
    """

    scenario: ScenarioType
    name: str
    description: str
    assumptions: List[str]
    evidence_sources: List[str] = Field(
        default_factory=lambda: [
            "AEMO Draft 2026 Integrated System Plan (scenario framework)",
            "AEMO 2025 ESOO October Update (coal closure dates)",
            "Modo Energy NEM 2024 Revenue Review ($148k/MW avg)",
            "Modo Energy FCAS Saturation Report ($384k→$11k/MW decline)",
            "Modo Energy BESS Price-Setting Analysis (22%→41% frequency)",
        ],
        description="Published sources supporting scenario assumptions",
    )


# =============================================================================
# Scenario Comparison Models
# =============================================================================


class ScenarioComparisonResult(BaseModel):
    """三情景对比结果。

    Aggregates the Central, High, and Low scenario projections for a
    single region, enabling side-by-side comparison of revenue outcomes.
    """

    region: str
    central: ScenarioProjection
    high: ScenarioProjection
    low: ScenarioProjection


# =============================================================================
# ML Calibration Metadata Models
# =============================================================================


class CalibrationMetadata(BaseModel):
    """ML 校准元数据。

    Contains metadata about the ML calibration process, including
    quality metrics, drift detection results, and regime indicators.
    All new fields are Optional to maintain backward compatibility.
    """

    status: str
    train_period: Optional[str] = None
    validation_period: Optional[str] = None
    validation_mae: Optional[float] = None
    validation_r2: Optional[float] = None
    direction_accuracy: Optional[float] = None
    confidence_interval_coverage: Optional[float] = None
    sample_count: Optional[int] = None
    calibrated_at: Optional[str] = None
    # --- 新增字段（Concept Drift & Quantile Regression）---
    regime_indicator: Optional[str] = None  # "low" | "medium" | "high"
    extrapolation_warning: Optional[bool] = None
    concept_drift_detected: Optional[bool] = None
    pinball_loss: Optional[Dict[str, float]] = None  # {"p10": x, "p50": y, "p90": z}
