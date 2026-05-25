"""Forward Price Scenario Engine.

基于供需事件注册表（煤电退役、BESS 新增容量）建模未来电价分布，
输出 Central/High/Low 三情景的 20 年收入预测。

Requirements: 7.1-7.5, 8.1-8.6, 9.1-9.5, 10.1-10.5, 13.1-13.5, 14.5, 14.6
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List

import numpy_financial as npf

from models.financial_params import BatterySpecs
from models.forward_price_models import (
    AnnualRevenueProjection,
    EventConfidence,
    EventRegistry,
    EventType,
    PriceDistribution,
    ScenarioDefinition,
    ScenarioProjection,
    ScenarioType,
    SupplyDemandEvent,
)
from models.narrative_models import (
    FuelSensitivityResult,
    FuelSensitivityScenario,
    NetworkAugmentationEvent,
    NetworkImpactComparison,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Base spread parameters from 2024 historical data ($/MWh)
BASE_SPREAD_PARAMS: Dict[str, Dict[str, float]] = {
    "NSW1": {"mean_spread": 120.0, "std_dev": 80.0, "spike_frequency": 0.003},
    "QLD1": {"mean_spread": 100.0, "std_dev": 70.0, "spike_frequency": 0.002},
    "VIC1": {"mean_spread": 110.0, "std_dev": 75.0, "spike_frequency": 0.003},
    "SA1": {"mean_spread": 140.0, "std_dev": 100.0, "spike_frequency": 0.005},
    "TAS1": {"mean_spread": 90.0, "std_dev": 60.0, "spike_frequency": 0.001},
    "WEM": {"mean_spread": 80.0, "std_dev": 50.0, "spike_frequency": 0.001},
}

# Peak demand by region (MW) — used for BESS saturation calculation
PEAK_DEMAND: Dict[str, float] = {
    "NSW1": 14000.0,
    "QLD1": 10000.0,
    "VIC1": 10000.0,
    "SA1": 3500.0,
    "TAS1": 1800.0,
    "WEM": 5000.0,
}

# Saturation sensitivity by scenario
SATURATION_SENSITIVITY: Dict[ScenarioType, float] = {
    ScenarioType.CENTRAL: 1.0,
    ScenarioType.HIGH: 0.7,
    ScenarioType.LOW: 1.3,
}

# Base capture rate for BESS arbitrage
BASE_CAPTURE_RATE: float = 0.65

SUPPORTED_REGIONS = list(BASE_SPREAD_PARAMS.keys())


# =============================================================================
# Engine
# =============================================================================


class ForwardPriceEngine:
    """基于供需事件建模未来电价分布和收入预测。"""

    def __init__(self) -> None:
        self.event_registry: EventRegistry = self._load_event_registry()

    # -------------------------------------------------------------------------
    # Data Loading
    # -------------------------------------------------------------------------

    def _load_event_registry(self) -> EventRegistry:
        """Load and merge coal retirement schedule and BESS capacity data.

        Coal closures produce events with spread_impact_factor > 1 (volatility increase).
        BESS commissionings produce events with spread_impact_factor < 1 (spread compression).

        Raises:
            FileNotFoundError: If required data files are missing.
        """
        events: List[SupplyDemandEvent] = []
        today = date.today()

        # --- Load coal retirement schedule ---
        coal_path = DATA_DIR / "coal_retirement_schedule.json"
        if not coal_path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {coal_path}. "
                "The coal retirement schedule is needed for forward price projections."
            )

        with open(coal_path, "r", encoding="utf-8") as f:
            coal_data = json.load(f)

        for retirement in coal_data.get("retirements", []):
            expected_date = date.fromisoformat(retirement["expected_closure_date"])

            if expected_date <= today:
                logger.warning(
                    "Coal retirement event '%s' has past date %s — excluding from projections.",
                    retirement["plant_name"],
                    expected_date,
                )
                continue

            # Coal closure increases volatility → spread_impact_factor > 1
            impact_factor = 1.0 + retirement["volatility_impact_estimate"]

            events.append(
                SupplyDemandEvent(
                    event_type=EventType.COAL_CLOSURE,
                    name=retirement["plant_name"],
                    region=retirement["region"],
                    expected_date=expected_date,
                    capacity_mw=retirement["capacity_mw"],
                    confidence=EventConfidence(retirement["confidence"]),
                    spread_impact_factor=impact_factor,
                )
            )

        # --- Load BESS capacity data ---
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {capacity_path}. "
                "The capacity data is needed for forward price projections."
            )

        with open(capacity_path, "r", encoding="utf-8") as f:
            capacity_data = json.load(f)

        for project in capacity_data.get("projects", []):
            # Use actual commissioning date if available, otherwise expected
            date_str = (
                project.get("actual_commissioning_date")
                or project["expected_commissioning_date"]
            )
            expected_date = date.fromisoformat(date_str)

            if expected_date <= today:
                logger.warning(
                    "BESS commissioning event '%s' has past date %s — excluding from projections.",
                    project["project_name"],
                    expected_date,
                )
                continue

            # BESS commissioning compresses spreads → spread_impact_factor < 1
            # Impact proportional to capacity relative to regional peak demand
            region = project["region"]
            peak = PEAK_DEMAND.get(region, 10000.0)
            compression = project["capacity_mw"] / peak
            impact_factor = max(0.85, 1.0 - compression * 0.1)

            events.append(
                SupplyDemandEvent(
                    event_type=EventType.BESS_COMMISSIONING,
                    name=project["project_name"],
                    region=region,
                    expected_date=expected_date,
                    capacity_mw=project["capacity_mw"],
                    confidence=EventConfidence(
                        "confirmed"
                        if project["status"] in ("registered", "construction")
                        else "announced"
                        if project["status"] == "committed"
                        else "speculated"
                    ),
                    spread_impact_factor=impact_factor,
                )
            )

        # --- Load network augmentation (interconnector) events ---
        for interconnector in capacity_data.get("interconnectors", []):
            expected_date = date.fromisoformat(interconnector["expected_date"])

            if expected_date <= today:
                logger.warning(
                    "Network augmentation event '%s' has past date %s — excluding from projections.",
                    interconnector["name"],
                    expected_date,
                )
                continue

            convergence_factor = interconnector["convergence_factor"]

            # Validate convergence_factor range [0.05, 0.30]
            if not (0.05 <= convergence_factor <= 0.30):
                raise ValueError(
                    f"convergence_factor for interconnector '{interconnector['name']}' "
                    f"must be in range [0.05, 0.30], got {convergence_factor}."
                )

            # Network augmentation compresses spreads → spread_impact_factor < 1
            # spread_impact_factor = 1 - convergence_factor
            impact_factor = 1.0 - convergence_factor

            # Add events for both connected regions
            for region in (interconnector["from_region"], interconnector["to_region"]):
                events.append(
                    SupplyDemandEvent(
                        event_type=EventType.NETWORK_AUGMENTATION,
                        name=interconnector["name"],
                        region=region,
                        expected_date=expected_date,
                        capacity_mw=interconnector["capacity_mw"],
                        confidence=EventConfidence(interconnector.get("confidence", "announced")),
                        spread_impact_factor=impact_factor,
                    )
                )

        last_updated_str = coal_data.get("metadata", {}).get("last_updated", str(today))
        # Handle datetime strings by taking just the date part
        last_updated = date.fromisoformat(last_updated_str[:10])

        return EventRegistry(events=events, last_updated=last_updated)

    # -------------------------------------------------------------------------
    # Scenario Definitions
    # -------------------------------------------------------------------------

    def get_scenarios(self) -> List[ScenarioDefinition]:
        """返回可用的情景定义列表（Central/High/Low）。"""
        return [
            ScenarioDefinition(
                scenario=ScenarioType.CENTRAL,
                name="Central",
                description="ISP central development path — coal retires on schedule, BESS builds at planned rate.",
                assumptions=[
                    "Coal retires on announced schedule",
                    "BESS capacity builds at ISP planned rate",
                    "Demand growth follows AEMO central forecast",
                    "Saturation sensitivity factor: 1.0",
                ],
            ),
            ScenarioDefinition(
                scenario=ScenarioType.HIGH,
                name="High",
                description="Accelerated coal retirement with slower BESS buildout — higher spreads persist longer.",
                assumptions=[
                    "Coal retires 2 years earlier than announced",
                    "BESS capacity builds 30% slower than planned",
                    "Higher price volatility due to supply tightness",
                    "Saturation sensitivity factor: 0.7",
                ],
            ),
            ScenarioDefinition(
                scenario=ScenarioType.LOW,
                name="Low",
                description="Coal life extensions with faster BESS buildout — spreads compress more quickly.",
                assumptions=[
                    "Coal extends 3 years beyond announced closure",
                    "BESS capacity builds 50% faster than planned",
                    "Lower price volatility due to excess capacity",
                    "Saturation sensitivity factor: 1.3",
                ],
            ),
        ]

    # -------------------------------------------------------------------------
    # Price Distribution Calculation
    # -------------------------------------------------------------------------

    def calculate_price_distribution(
        self,
        region: str,
        scenario: ScenarioType,
        year: int,
        bess_capacity_ratio: float,
    ) -> PriceDistribution:
        """计算指定区域/情景/年份的价格分布参数。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            scenario: Central/High/Low scenario type
            year: Target year for projection
            bess_capacity_ratio: Ratio of total BESS capacity to peak demand

        Returns:
            PriceDistribution with computed parameters.

        Raises:
            ValueError: If region is not supported.
        """
        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        base = BASE_SPREAD_PARAMS[region]
        mean_spread = base["mean_spread"]
        std_dev = base["std_dev"]
        spike_frequency = base["spike_frequency"]

        # Apply event impacts multiplicatively (Property 15)
        today = date.today()
        for event in self.event_registry.events:
            if event.region != region:
                continue
            if event.expected_date <= today:
                continue

            # Determine effective event date based on scenario
            effective_date = self._get_effective_event_date(event, scenario)

            # Only apply events that have occurred by the target year
            if effective_date.year <= year:
                mean_spread *= event.spread_impact_factor
                std_dev *= event.spread_impact_factor

        # BESS saturation compression (Property 16)
        sensitivity = SATURATION_SENSITIVITY[scenario]
        compression_factor = max(0.0, 1.0 - bess_capacity_ratio * sensitivity)

        # Apply compression to mean spread
        mean_spread *= compression_factor

        # Capture rate decreases with BESS penetration
        capture_rate = BASE_CAPTURE_RATE * (compression_factor ** 0.5)

        # Clamp outputs to valid ranges (Property 17)
        mean_spread = max(0.0, min(10000.0, mean_spread))
        std_dev = max(0.0, min(5000.0, std_dev))
        spike_frequency = max(0.0, min(1.0, spike_frequency))
        compression_factor = max(0.0, min(1.0, compression_factor))
        capture_rate = max(0.0, min(1.0, capture_rate))

        return PriceDistribution(
            year=year,
            region=region,
            scenario=scenario,
            mean_spread=mean_spread,
            std_dev=std_dev,
            spike_frequency=spike_frequency,
            compression_factor=compression_factor,
            capture_rate=capture_rate,
        )

    def _get_effective_event_date(
        self, event: SupplyDemandEvent, scenario: ScenarioType
    ) -> date:
        """Adjust event date based on scenario assumptions.

        - High scenario: coal retires 2 years early, BESS builds 30% slower (delayed)
        - Low scenario: coal extends 3 years, BESS builds 50% faster (earlier)
        - Central: as announced
        - Network augmentation: no scenario adjustment (infrastructure timelines fixed)
        """
        base_date = event.expected_date

        if scenario == ScenarioType.CENTRAL:
            return base_date

        if event.event_type == EventType.COAL_CLOSURE:
            if scenario == ScenarioType.HIGH:
                # Coal retires 2 years early
                return base_date.replace(year=base_date.year - 2)
            else:  # LOW
                # Coal extends 3 years
                return base_date.replace(year=base_date.year + 3)

        elif event.event_type == EventType.BESS_COMMISSIONING:
            if scenario == ScenarioType.HIGH:
                # BESS builds 30% slower → delayed by ~1.5 years
                return base_date.replace(year=base_date.year + 2)
            else:  # LOW
                # BESS builds 50% faster → earlier by ~1 year
                adjusted_year = max(date.today().year, base_date.year - 1)
                return base_date.replace(year=adjusted_year)

        elif event.event_type == EventType.NETWORK_AUGMENTATION:
            # Network infrastructure timelines are relatively fixed
            # Minor scenario adjustments: High delays by 1 year, Low accelerates by 1 year
            if scenario == ScenarioType.HIGH:
                return base_date.replace(year=base_date.year + 1)
            else:  # LOW
                adjusted_year = max(date.today().year, base_date.year - 1)
                return base_date.replace(year=adjusted_year)

        return base_date

    # -------------------------------------------------------------------------
    # Revenue Estimation
    # -------------------------------------------------------------------------

    def estimate_annual_revenue(
        self,
        region: str,
        scenario: ScenarioType,
        year: int,
        battery: BatterySpecs,
        soh: float,
    ) -> float:
        """基于价格分布估算年度套利收入。

        Revenue formula:
            annual_revenue = mean_spread × capture_rate × power_mw
                           × duration_hours × 365 × rte × soh

        Args:
            region: NEM region or WEM
            scenario: Scenario type
            year: Target year
            battery: Battery specifications
            soh: State of health (0.0 to 1.0)

        Returns:
            Estimated annual revenue in dollars.
        """
        # Calculate BESS capacity ratio for the region at the target year
        bess_capacity = self._get_cumulative_bess_capacity(region, scenario, year)
        peak_demand = PEAK_DEMAND.get(region, 10000.0)
        bess_capacity_ratio = bess_capacity / peak_demand

        # Get price distribution for this year
        dist = self.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=year,
            bess_capacity_ratio=bess_capacity_ratio,
        )

        # Revenue = mean_spread × capture_rate × power_mw × duration_hours × 365 × rte × soh
        annual_revenue = (
            dist.mean_spread
            * dist.capture_rate
            * battery.power_mw
            * battery.duration_hours
            * 365
            * battery.round_trip_efficiency
            * soh
        )

        return annual_revenue

    def _get_cumulative_bess_capacity(
        self, region: str, scenario: ScenarioType, year: int
    ) -> float:
        """Calculate cumulative BESS capacity in a region by a given year.

        Considers scenario adjustments to commissioning dates.
        """
        total_capacity = 0.0

        for event in self.event_registry.events:
            if event.region != region:
                continue
            if event.event_type != EventType.BESS_COMMISSIONING:
                continue

            effective_date = self._get_effective_event_date(event, scenario)
            if effective_date.year <= year:
                total_capacity += event.capacity_mw

        # Also include already-commissioned BESS (from capacity_data with past dates)
        # These are excluded from event_registry but contribute to saturation
        total_capacity += self._get_existing_bess_capacity(region)

        return total_capacity

    def _get_existing_bess_capacity(self, region: str) -> float:
        """Get already-commissioned BESS capacity for a region (past-date projects).

        Reads from capacity_data.json for projects with past commissioning dates.
        """
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            return 0.0

        with open(capacity_path, "r", encoding="utf-8") as f:
            capacity_data = json.load(f)

        today = date.today()
        total = 0.0

        for project in capacity_data.get("projects", []):
            if project["region"] != region:
                continue
            date_str = (
                project.get("actual_commissioning_date")
                or project["expected_commissioning_date"]
            )
            commissioning_date = date.fromisoformat(date_str)
            if commissioning_date <= today:
                total += project["capacity_mw"]

        return total

    # -------------------------------------------------------------------------
    # 20-Year Projection
    # -------------------------------------------------------------------------

    def generate_20year_projection(
        self,
        region: str,
        scenario: ScenarioType,
        battery: BatterySpecs,
    ) -> ScenarioProjection:
        """生成 20 年收入预测序列。

        Accounts for SoH degradation over the project life.
        Revenue is non-increasing over time due to degradation (Property 18).

        Args:
            region: NEM region or WEM
            scenario: Scenario type
            battery: Battery specifications

        Returns:
            ScenarioProjection with 20-year annual projections.
        """
        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        current_year = date.today().year
        annual_projections: List[AnnualRevenueProjection] = []
        discount_rate = 0.08  # Default discount rate

        for i in range(20):
            year = current_year + i + 1
            # SoH degrades linearly with calendar degradation rate
            soh = max(0.0, 1.0 - battery.calendar_degradation_rate * (i + 1))

            revenue = self.estimate_annual_revenue(
                region=region,
                scenario=scenario,
                year=year,
                battery=battery,
                soh=soh,
            )

            # Get price distribution for capture rate info
            bess_capacity = self._get_cumulative_bess_capacity(region, scenario, year)
            peak_demand = PEAK_DEMAND.get(region, 10000.0)
            bess_ratio = bess_capacity / peak_demand
            dist = self.calculate_price_distribution(
                region=region,
                scenario=scenario,
                year=year,
                bess_capacity_ratio=bess_ratio,
            )

            annual_projections.append(
                AnnualRevenueProjection(
                    year=year,
                    estimated_revenue_per_mw=revenue / battery.power_mw if battery.power_mw > 0 else 0.0,
                    state_of_health=soh,
                    mean_spread=dist.mean_spread,
                    capture_rate=dist.capture_rate,
                )
            )

        # Calculate totals
        total_revenue_per_mw = sum(
            p.estimated_revenue_per_mw for p in annual_projections
        )

        # NPV per MW using discount rate
        revenue_per_mw_series = [p.estimated_revenue_per_mw for p in annual_projections]
        npv_per_mw = float(
            npf.npv(discount_rate, [0.0] + revenue_per_mw_series)
        )

        return ScenarioProjection(
            scenario=scenario,
            region=region,
            annual_projections=annual_projections,
            total_revenue_per_mw=total_revenue_per_mw,
            npv_per_mw=npv_per_mw,
        )

    # -------------------------------------------------------------------------
    # Fuel Cost Sensitivity Analysis (Requirements 13.1-13.5, 17.4)
    # -------------------------------------------------------------------------

    def calculate_fuel_sensitivity(
        self,
        region: str,
        scenario: ScenarioType,
        battery: BatterySpecs,
        gas_base_price: float = 10.0,
        gas_escalation_rate: float = 0.02,
        pass_through_coefficient: float = 9.5,
    ) -> FuelSensitivityResult:
        """计算燃料成本敏感性分析。

        模型天然气价格变化对峰值电价和 BESS 收入的传导效应。
        输出 5 个情景：-20%, -10%, base, +10%, +20% 气价变化。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            scenario: Central/High/Low scenario type
            battery: Battery specifications
            gas_base_price: Base gas price in $/GJ (default 10.0)
            gas_escalation_rate: Annual gas price escalation rate (default 0.02)
            pass_through_coefficient: $/MWh per $/GJ pass-through (default 9.5)

        Returns:
            FuelSensitivityResult with 5 scenarios and sensitivity coefficient.

        Raises:
            ValueError: If pass_through_coefficient <= 0 or region not supported.
        """
        # Validate pass_through_coefficient > 0 (Requirement 17.4)
        if pass_through_coefficient <= 0:
            raise ValueError(
                f"pass_through_coefficient must be greater than 0, got {pass_through_coefficient}. "
                "The pass-through coefficient represents $/MWh impact per $/GJ gas price change "
                "and must be positive."
            )

        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        # Calculate base revenue (first year) without gas price adjustment
        current_year = date.today().year
        first_projection_year = current_year + 1
        soh = max(0.0, 1.0 - battery.calendar_degradation_rate)

        base_revenue = self.estimate_annual_revenue(
            region=region,
            scenario=scenario,
            year=first_projection_year,
            battery=battery,
            soh=soh,
        )

        # Gas price change scenarios: -20%, -10%, 0% (base), +10%, +20%
        change_percentages = [-20.0, -10.0, 0.0, 10.0, 20.0]
        scenarios: List[FuelSensitivityScenario] = []

        for change_pct in change_percentages:
            # Calculate gas price for this scenario
            gas_price = gas_base_price * (1.0 + change_pct / 100.0)

            # Delta gas price from base
            delta_gas = gas_price - gas_base_price

            # Peak electricity price impact: delta_gas × pass_through_coefficient
            # (Requirement 13.1: linear pass-through)
            peak_price_impact = delta_gas * pass_through_coefficient

            # Revenue impact: peak price impact affects the spread available for BESS
            # Higher peak prices → higher spreads → higher BESS revenue
            # Revenue change is proportional to peak_price_impact relative to mean_spread
            bess_capacity = self._get_cumulative_bess_capacity(
                region, scenario, first_projection_year
            )
            peak_demand = PEAK_DEMAND.get(region, 10000.0)
            bess_ratio = bess_capacity / peak_demand

            dist = self.calculate_price_distribution(
                region=region,
                scenario=scenario,
                year=first_projection_year,
                bess_capacity_ratio=bess_ratio,
            )

            # Revenue impact: the peak_price_impact changes the effective spread
            # Revenue scales linearly with spread change
            if dist.mean_spread > 0:
                revenue_change_fraction = peak_price_impact / dist.mean_spread
            else:
                revenue_change_fraction = 0.0

            revenue_impact = base_revenue * revenue_change_fraction
            revenue_change_pct = revenue_change_fraction * 100.0

            scenarios.append(
                FuelSensitivityScenario(
                    gas_price_change_pct=change_pct,
                    gas_price=gas_price,
                    peak_price_impact=peak_price_impact,
                    revenue_impact=revenue_impact,
                    revenue_change_pct=revenue_change_pct,
                )
            )

        # Sensitivity coefficient: revenue change % per 10% gas price change
        # Use the +10% scenario to calculate this
        ten_pct_scenario = next(
            s for s in scenarios if s.gas_price_change_pct == 10.0
        )
        sensitivity_coefficient = ten_pct_scenario.revenue_change_pct

        return FuelSensitivityResult(
            region=region,
            scenario=scenario.value,
            base_revenue=base_revenue,
            sensitivity_coefficient=sensitivity_coefficient,
            scenarios=scenarios,
        )

    # -------------------------------------------------------------------------
    # Network Augmentation Impact Model (Requirements 14.1-14.4, 17.5)
    # -------------------------------------------------------------------------

    def calculate_network_impact(
        self,
        region: str,
        convergence_factor: float | None = None,
    ) -> NetworkImpactComparison:
        """计算网络增强（互联线投运）对区域价差的影响。

        模型新互联线投运如何通过市场收敛降低区域价差。
        输出事件前后的 20 年价差对比。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            convergence_factor: Optional override for convergence factor.
                If provided, must be in [0.05, 0.30]. If None, uses the
                value from capacity_data.json interconnectors field.

        Returns:
            NetworkImpactComparison with before/after spread projections.

        Raises:
            ValueError: If convergence_factor outside [0.05, 0.30] or region not supported.
        """
        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        # Validate convergence_factor if provided (Requirement 17.5)
        if convergence_factor is not None:
            if not (0.05 <= convergence_factor <= 0.30):
                raise ValueError(
                    f"convergence_factor must be in range [0.05, 0.30], got {convergence_factor}. "
                    "The convergence factor represents the degree of regional price convergence "
                    "caused by interconnector commissioning."
                )

        # Load interconnector events for this region from capacity_data.json
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {capacity_path}. "
                "The capacity data is needed for network impact analysis."
            )

        with open(capacity_path, "r", encoding="utf-8") as f:
            capacity_data = json.load(f)

        # Find interconnectors affecting this region
        region_interconnectors: List[NetworkAugmentationEvent] = []
        for ic in capacity_data.get("interconnectors", []):
            if region in (ic["from_region"], ic["to_region"]):
                ic_convergence = convergence_factor if convergence_factor is not None else ic["convergence_factor"]

                # Validate convergence_factor from data (Requirement 17.5)
                if not (0.05 <= ic_convergence <= 0.30):
                    raise ValueError(
                        f"convergence_factor for interconnector '{ic['name']}' "
                        f"must be in range [0.05, 0.30], got {ic_convergence}."
                    )

                region_interconnectors.append(
                    NetworkAugmentationEvent(
                        name=ic["name"],
                        from_region=ic["from_region"],
                        to_region=ic["to_region"],
                        capacity_mw=ic["capacity_mw"],
                        expected_date=date.fromisoformat(ic["expected_date"]),
                        convergence_factor=ic_convergence,
                        spread_impact_factor=1.0 - ic_convergence,
                    )
                )

        # Use the first (earliest) interconnector for the comparison
        # If no interconnectors found, return empty comparison
        if not region_interconnectors:
            current_year = date.today().year
            base_spread = BASE_SPREAD_PARAMS[region]["mean_spread"]
            spread_data = [
                {"year": current_year + i + 1, "spread": base_spread}
                for i in range(20)
            ]
            return NetworkImpactComparison(
                project_name="No interconnector projects",
                region=region,
                spread_before=spread_data,
                spread_after=spread_data,
                reduction_pct=0.0,
            )

        # Sort by expected date and use the earliest project for comparison
        region_interconnectors.sort(key=lambda x: x.expected_date)
        primary_project = region_interconnectors[0]

        # Generate 20-year spread projections: before and after network augmentation
        current_year = date.today().year
        base_spread = BASE_SPREAD_PARAMS[region]["mean_spread"]

        spread_before: List[dict] = []
        spread_after: List[dict] = []

        # Calculate spread WITHOUT network augmentation events
        # (only apply coal closure and BESS events)
        for i in range(20):
            year = current_year + i + 1
            spread_no_network = base_spread

            # Apply non-network events
            for event in self.event_registry.events:
                if event.region != region:
                    continue
                if event.event_type == EventType.NETWORK_AUGMENTATION:
                    continue
                effective_date = self._get_effective_event_date(event, ScenarioType.CENTRAL)
                if effective_date.year <= year:
                    spread_no_network *= event.spread_impact_factor

            spread_before.append({"year": year, "spread": round(max(0.0, spread_no_network), 2)})

        # Calculate spread WITH network augmentation events
        # (apply all events including network augmentation)
        for i in range(20):
            year = current_year + i + 1
            spread_with_network = base_spread

            # Apply all events including network augmentation
            for event in self.event_registry.events:
                if event.region != region:
                    continue
                effective_date = self._get_effective_event_date(event, ScenarioType.CENTRAL)
                if effective_date.year <= year:
                    spread_with_network *= event.spread_impact_factor

            spread_after.append({"year": year, "spread": round(max(0.0, spread_with_network), 2)})

        # Calculate overall reduction percentage
        total_before = sum(entry["spread"] for entry in spread_before)
        total_after = sum(entry["spread"] for entry in spread_after)
        reduction_pct = (
            ((total_before - total_after) / total_before * 100.0)
            if total_before > 0
            else 0.0
        )

        return NetworkImpactComparison(
            project_name=primary_project.name,
            region=region,
            spread_before=spread_before,
            spread_after=spread_after,
            reduction_pct=round(reduction_pct, 2),
        )
