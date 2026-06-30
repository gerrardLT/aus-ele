"""Cost Structure Engine for BESS fee component decomposition.

Decomposes network fees into individual components (AEMO Participant Fees, TUOS,
DUOS, MLF, FPP) with FIXED/VARIABLE classification and region-specific defaults.

Requirements: 1.1-1.7, 2.1-2.5, 3.1-3.6
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from models.cost_structure_models import (
    AemoParticipantFee,
    AemoRegistrationFee,
    AnnualCostBreakdown,
    ConnectionType,
    CostLineItem,
    CostStructureOverrides,
    DuosCharge,
    FeeType,
    FppConfig,
    MlfConfig,
    RegionalFeeConfig,
    TuosDemandCharge,
    TuosEnergyCharge,
)
from models.financial_params import BatterySpecs

logger = logging.getLogger(__name__)

# Path to external fee configuration JSON
_FEE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "regional_fee_defaults.json"


def _parse_region_config(raw: dict) -> RegionalFeeConfig:
    """Parse a single region dict from JSON into a RegionalFeeConfig."""
    return RegionalFeeConfig(
        region=raw["region"],
        aemo_participant_fee=AemoParticipantFee(**raw.get("aemo_participant_fee", {})),
        aemo_registration_fee=AemoRegistrationFee(**raw.get("aemo_registration_fee", {})),
        tuos_demand=TuosDemandCharge(**raw.get("tuos_demand", {})),
        tuos_energy=TuosEnergyCharge(**raw.get("tuos_energy", {})),
        duos=DuosCharge(**raw.get("duos", {})),
        mlf=MlfConfig(**raw.get("mlf", {})),
        fpp=FppConfig(**raw.get("fpp", {})),
    )


def _load_regional_defaults() -> dict[str, RegionalFeeConfig]:
    """Load regional fee defaults from external JSON, falling back to hardcoded values."""
    hardcoded = {
        "NSW1": RegionalFeeConfig(
            region="NSW1",
            aemo_participant_fee=AemoParticipantFee(rate_per_mwh=0.40),
            aemo_registration_fee=AemoRegistrationFee(amount=10000.0),
            tuos_demand=TuosDemandCharge(rate_per_mw_year=12000.0),
            tuos_energy=TuosEnergyCharge(rate_per_mwh=2.0),
            duos=DuosCharge(connection_type=ConnectionType.TRANSMISSION, rate_per_mwh=0.0),
            mlf=MlfConfig(value=0.97),
            fpp=FppConfig(net_earning_per_mw_year=1000.0),
        ),
        "QLD1": RegionalFeeConfig(
            region="QLD1",
            aemo_participant_fee=AemoParticipantFee(rate_per_mwh=0.38),
            aemo_registration_fee=AemoRegistrationFee(amount=10000.0),
            tuos_demand=TuosDemandCharge(rate_per_mw_year=10000.0),
            tuos_energy=TuosEnergyCharge(rate_per_mwh=1.8),
            duos=DuosCharge(connection_type=ConnectionType.TRANSMISSION, rate_per_mwh=0.0),
            mlf=MlfConfig(value=0.98),
            fpp=FppConfig(net_earning_per_mw_year=900.0),
        ),
        "VIC1": RegionalFeeConfig(
            region="VIC1",
            aemo_participant_fee=AemoParticipantFee(rate_per_mwh=0.40),
            aemo_registration_fee=AemoRegistrationFee(amount=10000.0),
            tuos_demand=TuosDemandCharge(rate_per_mw_year=9000.0),
            tuos_energy=TuosEnergyCharge(rate_per_mwh=1.5),
            duos=DuosCharge(connection_type=ConnectionType.TRANSMISSION, rate_per_mwh=0.0),
            mlf=MlfConfig(value=0.99),
            fpp=FppConfig(net_earning_per_mw_year=1100.0),
        ),
        "SA1": RegionalFeeConfig(
            region="SA1",
            aemo_participant_fee=AemoParticipantFee(rate_per_mwh=0.42),
            aemo_registration_fee=AemoRegistrationFee(amount=12000.0),
            tuos_demand=TuosDemandCharge(rate_per_mw_year=14000.0),
            tuos_energy=TuosEnergyCharge(rate_per_mwh=2.5),
            duos=DuosCharge(connection_type=ConnectionType.TRANSMISSION, rate_per_mwh=0.0),
            mlf=MlfConfig(value=0.95),
            fpp=FppConfig(net_earning_per_mw_year=1200.0),
        ),
        "TAS1": RegionalFeeConfig(
            region="TAS1",
            aemo_participant_fee=AemoParticipantFee(rate_per_mwh=0.38),
            aemo_registration_fee=AemoRegistrationFee(amount=8000.0),
            tuos_demand=TuosDemandCharge(rate_per_mw_year=11000.0),
            tuos_energy=TuosEnergyCharge(rate_per_mwh=2.2),
            duos=DuosCharge(connection_type=ConnectionType.TRANSMISSION, rate_per_mwh=0.0),
            mlf=MlfConfig(value=0.96),
            fpp=FppConfig(net_earning_per_mw_year=800.0),
        ),
        "WEM": RegionalFeeConfig(
            region="WEM",
            aemo_participant_fee=AemoParticipantFee(rate_per_mwh=0.35),
            aemo_registration_fee=AemoRegistrationFee(amount=15000.0),
            tuos_demand=TuosDemandCharge(rate_per_mw_year=8000.0),
            tuos_energy=TuosEnergyCharge(rate_per_mwh=1.5),
            duos=DuosCharge(connection_type=ConnectionType.TRANSMISSION, rate_per_mwh=0.0),
            mlf=MlfConfig(value=1.00),
            fpp=FppConfig(net_earning_per_mw_year=1000.0),
        ),
    }
    if not _FEE_CONFIG_PATH.exists():
        return hardcoded
    try:
        raw = json.loads(_FEE_CONFIG_PATH.read_text(encoding="utf-8"))
        loaded = {}
        for key, value in raw.items():
            if key.startswith("_"):
                continue  # skip _comment and metadata keys
            loaded[key] = _parse_region_config(value)
        logger.info("Loaded fee defaults from %s (%d regions)", _FEE_CONFIG_PATH.name, len(loaded))
        return loaded
    except Exception as exc:
        logger.warning("Failed to load %s, using hardcoded defaults: %s", _FEE_CONFIG_PATH.name, exc)
        return hardcoded


# Regional default fee parameter sets — loaded from JSON or fallback to hardcoded.
# Sources: AEMO published MLFs, TNSP pricing determinations, AER tariff data.
_REGIONAL_DEFAULTS: dict[str, RegionalFeeConfig] = _load_regional_defaults()

SUPPORTED_REGIONS = list(_REGIONAL_DEFAULTS.keys())


class CostStructureEngine:
    """计算 BESS 项目的逐组件费用结构。

    Decomposes annual costs into FIXED and VARIABLE components with
    region-specific defaults and user override support.
    """

    @staticmethod
    def get_regional_defaults(region: str) -> RegionalFeeConfig:
        """返回指定区域的默认费用参数集。

        Args:
            region: NEM/WEM region code (NSW1, QLD1, VIC1, SA1, TAS1, WEM).

        Returns:
            RegionalFeeConfig with all default fee parameters for the region.

        Raises:
            ValueError: If region is not in the supported list.
        """
        if region not in _REGIONAL_DEFAULTS:
            raise ValueError(
                f"Unknown region '{region}'. Supported regions: {SUPPORTED_REGIONS}"
            )
        # Return a copy to prevent mutation of internal defaults
        return _REGIONAL_DEFAULTS[region].model_copy(deep=True)

    @staticmethod
    def calculate_annual_costs(
        battery: BatterySpecs,
        region: str,
        annual_throughput_mwh: float,
        connection_type: ConnectionType,
        overrides: Optional[CostStructureOverrides] = None,
    ) -> AnnualCostBreakdown:
        """计算年度费用分解，区分 FIXED 和 VARIABLE 组件。

        Args:
            battery: Battery specifications (power_mw, duration_hours, etc.).
            region: NEM/WEM region code.
            annual_throughput_mwh: Total annual energy throughput in MWh
                (charge + discharge combined).
            connection_type: Grid connection type (TRANSMISSION or DISTRIBUTION).
            overrides: Optional user overrides for fee parameters.

        Returns:
            AnnualCostBreakdown with component-level detail.

        Raises:
            ValueError: If region is not supported.
        """
        # Get regional defaults and apply overrides
        config = CostStructureEngine.get_regional_defaults(region)
        config = CostStructureEngine._apply_overrides(config, connection_type, overrides)

        # Gross Energy = total throughput (charge_energy + discharge_energy)
        # For AEMO Participant Fee calculation (Requirement 3.3)
        gross_energy_mwh = annual_throughput_mwh

        line_items: list[CostLineItem] = []

        # 1. AEMO Participant Fee — VARIABLE, on gross energy (Req 1.1)
        aemo_participant_cost = config.aemo_participant_fee.rate_per_mwh * gross_energy_mwh
        line_items.append(CostLineItem(
            name="AEMO Participant Fee",
            fee_type=FeeType.VARIABLE,
            annual_amount=aemo_participant_cost,
            percentage_of_total=0.0,  # calculated below
        ))

        # 2. TUOS Demand — FIXED, $/MW/year (Req 1.3)
        tuos_demand_cost = config.tuos_demand.rate_per_mw_year * battery.power_mw
        line_items.append(CostLineItem(
            name="TUOS Demand",
            fee_type=FeeType.FIXED,
            annual_amount=tuos_demand_cost,
            percentage_of_total=0.0,
        ))

        # 3. TUOS Energy — VARIABLE, $/MWh (Req 1.4)
        tuos_energy_cost = config.tuos_energy.rate_per_mwh * annual_throughput_mwh
        line_items.append(CostLineItem(
            name="TUOS Energy",
            fee_type=FeeType.VARIABLE,
            annual_amount=tuos_energy_cost,
            percentage_of_total=0.0,
        ))

        # 4. DUOS — VARIABLE, connection-type dependent (Req 1.5)
        # Transmission-connected: rate = 0 (exempt)
        # Distribution-connected: use configured rate
        if config.duos.connection_type == ConnectionType.TRANSMISSION:
            duos_cost = 0.0
        else:
            duos_cost = config.duos.rate_per_mwh * annual_throughput_mwh
        line_items.append(CostLineItem(
            name="DUOS",
            fee_type=FeeType.VARIABLE,
            annual_amount=duos_cost,
            percentage_of_total=0.0,
        ))

        # 5. FPP — net EARNING (reduces costs), not a cost (Req 1.7)
        # FPP is subtracted from total costs as it represents revenue
        fpp_earning = config.fpp.net_earning_per_mw_year * battery.power_mw
        line_items.append(CostLineItem(
            name="FPP (Net Earning)",
            fee_type=FeeType.VARIABLE,
            annual_amount=-fpp_earning,  # Negative = reduces costs
            percentage_of_total=0.0,
        ))

        # Calculate totals
        total_fixed = sum(
            item.annual_amount for item in line_items if item.fee_type == FeeType.FIXED
        )
        total_variable = sum(
            item.annual_amount for item in line_items if item.fee_type == FeeType.VARIABLE
        )
        total_annual = total_fixed + total_variable

        # Calculate percentages (handle zero total case)
        if total_annual != 0.0:
            for item in line_items:
                item.percentage_of_total = (item.annual_amount / total_annual) * 100.0
        else:
            # If total is zero, distribute evenly or set to 0
            for item in line_items:
                item.percentage_of_total = 0.0

        return AnnualCostBreakdown(
            region=region,
            total_fixed_costs=total_fixed,
            total_variable_costs=total_variable,
            total_annual_cost=total_annual,
            line_items=line_items,
            mlf_applied=config.mlf.value,
        )

    @staticmethod
    def apply_mlf(settlement_price: float, mlf: float) -> float:
        """将 MLF 作为乘数应用于结算价格 (Requirement 1.6, 3.4).

        MLF is a multiplicative price adjustment, NOT an additive fee.

        Args:
            settlement_price: Raw settlement price in $/MWh.
            mlf: Marginal Loss Factor value (valid range 0.50-1.50).

        Returns:
            Adjusted settlement price = settlement_price × mlf.
        """
        return settlement_price * mlf

    @staticmethod
    def _apply_overrides(
        config: RegionalFeeConfig,
        connection_type: ConnectionType,
        overrides: Optional[CostStructureOverrides] = None,
    ) -> RegionalFeeConfig:
        """合并用户覆盖到区域默认配置 (Requirement 2.5).

        User overrides replace defaults for specified fields;
        unmodified fields retain their regional defaults.

        Args:
            config: Regional fee configuration (will be mutated).
            connection_type: Grid connection type for DUOS logic.
            overrides: Optional user overrides.

        Returns:
            Modified RegionalFeeConfig with overrides applied.
        """
        # Always apply the connection_type to DUOS config
        config.duos.connection_type = connection_type

        if overrides is None:
            return config

        # Apply individual overrides — only non-None values replace defaults
        if overrides.aemo_participant_rate is not None:
            config.aemo_participant_fee.rate_per_mwh = overrides.aemo_participant_rate

        if overrides.tuos_demand_rate is not None:
            config.tuos_demand.rate_per_mw_year = overrides.tuos_demand_rate

        if overrides.tuos_energy_rate is not None:
            config.tuos_energy.rate_per_mwh = overrides.tuos_energy_rate

        if overrides.duos_rate is not None:
            config.duos.rate_per_mwh = overrides.duos_rate

        if overrides.mlf_value is not None:
            config.mlf.value = overrides.mlf_value

        if overrides.fpp_net_earning is not None:
            config.fpp.net_earning_per_mw_year = overrides.fpp_net_earning

        if overrides.connection_type is not None:
            config.duos.connection_type = overrides.connection_type

        return config
