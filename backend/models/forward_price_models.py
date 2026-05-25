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
from typing import List

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
    compression_factor: float = Field(ge=0.0, le=1.0, description="BESS 饱和压缩因子")
    capture_rate: float = Field(ge=0.0, le=1.0, description="BESS 价差捕获率")


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
