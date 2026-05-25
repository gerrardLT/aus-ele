"""Investment Outlook Scenarios data models.

Provides Pydantic models for the 4 outlook scenario modules:
- Cannibalization Simulator (收入蚕食模拟器)
- FCAS Collapse Forecaster (FCAS 崩塌预判器)
- Regional Timing Scorer (区域时机评分器)
- Merchant Risk Quantifier (商户风险量化器)

Requirements: 1.1, 2.1, 3.1, 4.1, 5.4
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Coal Retirement Schedule Models
# =============================================================================


class CoalRetirement(BaseModel):
    """A single coal plant retirement entry.

    Represents a planned coal power station closure with its expected
    impact on regional price volatility.
    """

    plant_name: str
    region: str
    capacity_mw: float = Field(gt=0)
    fuel_type: Literal["black_coal", "brown_coal", "gas"]
    expected_closure_date: date
    confidence: Literal["confirmed", "announced", "speculated"]
    volatility_impact_estimate: float = Field(ge=0, le=1.0)


class CoalRetirementSchedule(BaseModel):
    """Coal retirement schedule containing metadata and retirement entries.

    Provides helper methods for querying retirements by region and date.
    """

    metadata: dict
    retirements: list[CoalRetirement]

    def get_retirements_before(self, region: str, target_date: date) -> list[CoalRetirement]:
        """Get all planned retirements in a region before the target date.

        Args:
            region: NEM region code (e.g. 'NSW1', 'VIC1').
            target_date: Upper bound date (inclusive).

        Returns:
            List of CoalRetirement entries matching the criteria.
        """
        return [
            r for r in self.retirements
            if r.region == region and r.expected_closure_date <= target_date
        ]

    def total_retiring_capacity(self, region: str, target_date: date) -> float:
        """Calculate total retiring capacity (MW) in a region before target date.

        Args:
            region: NEM region code.
            target_date: Upper bound date (inclusive).

        Returns:
            Sum of capacity_mw for matching retirements.
        """
        return sum(r.capacity_mw for r in self.get_retirements_before(region, target_date))


# =============================================================================
# FCAS Collapse Forecaster Models
# =============================================================================


class FcasServiceParams(BaseModel):
    """Supply-demand parameters for a single FCAS service type."""

    service_name: str  # e.g. "raise6sec"
    registered_capacity_mw: float = Field(ge=0)
    market_requirement_mw: float = Field(gt=0)
    supply_demand_ratio: float = Field(ge=0)
    historical_base_price: float = Field(ge=0, description="AUD/MW/hr base price")
    classification: Literal["healthy", "at_risk", "collapsed"]
    price_ceiling: float = Field(ge=0, description="AUD/MW/hr price ceiling")


class FcasCollapseParams(BaseModel):
    """Global parameters for the FCAS collapse model."""

    beta: float = Field(default=1.5, ge=0.5, le=3.0, description="Collapse steepness")
    collapse_threshold: float = Field(default=3.0, description="Supply/demand ratio collapse threshold")
    at_risk_threshold: float = Field(default=1.5, description="Supply/demand ratio at-risk threshold")
    enablement_probability: float = Field(
        default=0.3, ge=0, le=1.0,
        description="FCAS enablement probability for weighted annual revenue calculation",
    )


# =============================================================================
# Merchant Risk Quantifier Models
# =============================================================================


class MerchantRiskRequest(BaseModel):
    """Request parameters for Monte Carlo merchant risk simulation."""

    market: Literal["NEM"] = "NEM"
    region: str = Field(..., description="NEM region code")
    power_mw: float = Field(default=100, gt=0)
    duration_hours: float = Field(default=4, gt=0)
    round_trip_efficiency: float = Field(default=0.87, gt=0, le=1)

    # Monte Carlo parameters
    n_simulations: int = Field(default=1000, ge=100, le=10000)
    noise_std_pct: float = Field(
        default=0.10, ge=0, le=0.5,
        description="Daily revenue noise standard deviation percentage",
    )

    # Bankability parameters
    dscr: float = Field(default=1.3, ge=1.0, le=2.0, description="Debt service coverage ratio")
    bank_contract_pct: float = Field(
        default=0.70, ge=0.5, le=0.9,
        description="Bank required contract coverage percentage",
    )
    annual_debt_service: Optional[float] = Field(
        default=None, ge=0,
        description="Annual debt service AUD/MW, defaults to capex-based estimate",
    )


class MonteCarloConfig(BaseModel):
    """Internal Monte Carlo simulation configuration."""

    seed: Optional[int] = None
    min_historical_years: int = Field(default=2, ge=1)
    days_per_year: int = Field(default=365)


# =============================================================================
# API Response Models
# =============================================================================


class DilutionPoint(BaseModel):
    """A single point on the dilution curve."""

    capacity_mw: float
    revenue_per_mw: float  # AUD/MW/year
    dilution_pct: float  # Dilution percentage relative to base revenue


class YearlyProjection(BaseModel):
    """Year-by-year projection of capacity and revenue."""

    year: int
    projected_capacity_mw: float
    projected_revenue_per_mw: float
    dilution_pct: float
    new_projects: list[str]  # Projects expected to commission that year


class MarketExample(BaseModel):
    """A real market data example for trust building."""

    region: str
    description: str
    data_year: int
    actual_value: float
    label: Literal["actual", "projected"]


class CannibalizationResponse(BaseModel):
    """Response model for the Cannibalization Simulator endpoint."""

    metadata: dict  # {market, region, timezone, currency, methodology_version}
    region: str
    alpha: float
    base_capacity_mw: float
    base_revenue_per_mw: float

    dilution_curve: list[DilutionPoint]
    yearly_projections: list[YearlyProjection]
    current_dilution_pct: float
    warning_triggered: bool  # True if dilution > 50%

    market_examples: list[MarketExample]
    conclusion: str  # Plain-text conclusion summary


class FcasServiceResult(BaseModel):
    """Result for a single FCAS service in the collapse forecast."""

    service_name: str
    supply_mw: float
    demand_mw: float
    supply_demand_ratio: float
    classification: Literal["healthy", "at_risk", "collapsed"]
    price_ceiling_per_mwh: float  # AUD/MW/hr
    historical_price_per_mwh: Optional[float] = None


class FcasCollapseResponse(BaseModel):
    """Response model for the FCAS Collapse Forecaster endpoint."""

    metadata: dict
    region: str
    year: int
    beta: float

    services: list[FcasServiceResult]
    total_fcas_ceiling_per_mw_year: float  # Weighted sum across all services

    historical_trajectory: list[dict]  # [{year, total_fcas_revenue_per_mw}]
    market_examples: list[MarketExample]
    conclusion: str


class RegionTimingScore(BaseModel):
    """Score for a single region in the timing analysis."""

    region: str
    rank: int
    total_score: float
    dimensions: dict  # {coal_retirement, pipeline_growth, renewable_penetration, revenue_trajectory}
    key_events: list[str]  # Key events description for this region


class RegionalTimingResponse(BaseModel):
    """Response model for the Regional Timing Scorer endpoint."""

    metadata: dict
    target_year: int
    weights_used: dict

    rankings: list[RegionTimingScore]
    coal_data_available: bool

    market_examples: list[MarketExample]
    conclusion: str  # Recommended region and timing


class RevenueDistribution(BaseModel):
    """Revenue probability distribution from Monte Carlo simulation."""

    p10: float  # AUD/MW/year
    p50: float
    p90: float
    mean: float
    std: float
    min_observed: float
    max_observed: float


class MerchantRiskResponse(BaseModel):
    """Response model for the Merchant Risk Quantifier endpoint."""

    metadata: dict
    region: str
    power_mw: float
    duration_hours: float
    n_simulations: int

    distribution: RevenueDistribution
    histogram_bins: list[dict]  # [{bin_start, bin_end, count, frequency}]

    # Bankability analysis
    min_contract_coverage_pct: float
    contract_revenue_needed: float  # AUD/MW/year
    bankability_met: bool

    # Historical comparison
    historical_revenue_range: dict  # {min, max, years_used}
    years_of_data: int
    data_warning: Optional[str] = None  # Warning when data is insufficient

    market_examples: list[MarketExample]
    conclusion: str
