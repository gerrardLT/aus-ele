"""Cost structure data models for BESS fee component classification.

Provides Pydantic models for decomposing network fees into individual components:
AEMO Participant Fees, TUOS (Transmission), DUOS (Distribution), MLF, and FPP.
Each component is classified as FIXED or VARIABLE with region-specific defaults.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.5, 11.1, 14.1, 14.2
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FeeType(str, Enum):
    """Fee classification: fixed costs are independent of throughput,
    variable costs scale with energy volume."""

    FIXED = "fixed"
    VARIABLE = "variable"


class ConnectionType(str, Enum):
    """BESS grid connection type — determines DUOS applicability."""

    TRANSMISSION = "transmission"
    DISTRIBUTION = "distribution"


class AemoParticipantFee(BaseModel):
    """AEMO Participant Fee — VARIABLE, calculated on Gross Energy (charge + discharge).

    Rate range: $0.30–$0.50/MWh (Requirement 1.1)
    """

    fee_type: FeeType = FeeType.VARIABLE
    rate_per_mwh: float = Field(default=0.40, ge=0.30, le=0.50)


class AemoRegistrationFee(BaseModel):
    """AEMO Registration Fee — one-time FIXED cost at project commencement.

    Amount range: $5,000–$50,000 (Requirement 1.2)
    """

    fee_type: FeeType = FeeType.FIXED
    amount: float = Field(default=10000.0, ge=5000.0, le=50000.0)


class TuosDemandCharge(BaseModel):
    """TUOS Demand Component — FIXED, $/MW/year.

    Rate range: $5,000–$15,000/MW/year depending on region and TNSP (Requirement 1.3)
    """

    fee_type: FeeType = FeeType.FIXED
    rate_per_mw_year: float = Field(default=10000.0, ge=5000.0, le=15000.0)


class TuosEnergyCharge(BaseModel):
    """TUOS Energy Component — VARIABLE, $/MWh.

    Rate range: $1.0–$3.0/MWh (Requirement 1.4)
    """

    fee_type: FeeType = FeeType.VARIABLE
    rate_per_mwh: float = Field(default=2.0, ge=1.0, le=3.0)


class DuosCharge(BaseModel):
    """DUOS Distribution Fee — VARIABLE, connection-type dependent.

    Transmission-connected BESS: rate = 0 (exempt).
    Distribution-connected BESS: time-of-use rate $5–$30/MWh (Requirement 1.5).
    Default assumes transmission connection (rate = 0).
    """

    fee_type: FeeType = FeeType.VARIABLE
    connection_type: ConnectionType = ConnectionType.TRANSMISSION
    rate_per_mwh: float = Field(default=0.0, ge=0.0, le=30.0)


class MlfConfig(BaseModel):
    """Marginal Loss Factor — settlement price multiplier per connection point.

    Applied multiplicatively to settlement price, NOT as an additive fee (Requirement 1.6).
    Valid range: 0.50–1.50 (Requirement 14.1)
    """

    value: float = Field(default=0.98, ge=0.50, le=1.50)


class FppConfig(BaseModel):
    """Frequency Performance Payments — double-sided VARIABLE mechanism.

    Net earning range: $500–$1,500/MW/year for BESS (Requirement 1.7)
    """

    fee_type: FeeType = FeeType.VARIABLE
    net_earning_per_mw_year: float = Field(default=1000.0, ge=500.0, le=1500.0)


class RegionalFeeConfig(BaseModel):
    """Complete regional fee parameter set for a single NEM/WEM region.

    Maintains separate fee parameters for each of the six regions:
    NSW1, QLD1, VIC1, SA1, TAS1, WEM (Requirement 2.1).
    """

    region: str
    aemo_participant_fee: AemoParticipantFee = Field(default_factory=AemoParticipantFee)
    aemo_registration_fee: AemoRegistrationFee = Field(default_factory=AemoRegistrationFee)
    tuos_demand: TuosDemandCharge = Field(default_factory=TuosDemandCharge)
    tuos_energy: TuosEnergyCharge = Field(default_factory=TuosEnergyCharge)
    duos: DuosCharge = Field(default_factory=DuosCharge)
    mlf: MlfConfig = Field(default_factory=MlfConfig)
    fpp: FppConfig = Field(default_factory=FppConfig)


class CostStructureOverrides(BaseModel):
    """User-overridable subset of fee parameters.

    Any field set to a non-None value overrides the regional default;
    unset fields retain their regional defaults (Requirement 2.5).
    """

    aemo_participant_rate: Optional[float] = Field(default=None, ge=0.30, le=0.50)
    tuos_demand_rate: Optional[float] = Field(default=None, ge=5000.0, le=15000.0)
    tuos_energy_rate: Optional[float] = Field(default=None, ge=1.0, le=3.0)
    duos_rate: Optional[float] = Field(default=None, ge=0.0, le=30.0)
    mlf_value: Optional[float] = Field(default=None, ge=0.50, le=1.50)
    fpp_net_earning: Optional[float] = Field(default=None, ge=500.0, le=1500.0)
    connection_type: Optional[ConnectionType] = None


class CostLineItem(BaseModel):
    """Single fee component calculation result for annual cost breakdown."""

    name: str
    fee_type: FeeType
    annual_amount: float
    percentage_of_total: float


class AnnualCostBreakdown(BaseModel):
    """Full annual cost breakdown with component-level detail.

    Invariant: total_annual_cost == total_fixed_costs + total_variable_costs
    Invariant: sum(line_items[].annual_amount) == total_annual_cost
    Invariant: sum(line_items[].percentage_of_total) ≈ 100.0
    """

    region: str
    total_fixed_costs: float
    total_variable_costs: float
    total_annual_cost: float
    line_items: list[CostLineItem]
    mlf_applied: float = Field(description="MLF multiplier value (not a cost line item)")
    evidence_sources: list[str] = Field(
        default_factory=lambda: [
            "AER Revenue Determination 2024-29 (TUOS rates)",
            "AEMO Energy Market Fees and Charges 2024-25 (Participant fees)",
            "AEMO Marginal Loss Factors 2024-25 (MLF values)",
            "AEMC IESS Rule Change 2024 (Gross Energy billing)",
            "AEMO FPP Implementation June 2025 (replaced Causer Pays)",
        ],
        description="Data sources supporting the fee parameters used in this calculation",
    )
