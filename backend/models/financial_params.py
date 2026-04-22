from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union
from enum import Enum

class DispatchMode(str, Enum):
    HINDSIGHT_OPTIMIZED = "hindsight_optimized"
    ROLLING_FORECAST = "rolling_forecast"

class FcasRevenueMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"

class ScenarioConfig(BaseModel):
    name: str = "Base"
    capex_multiplier: float = 1.0
    arbitrage_multiplier: float = 1.0
    fcas_multiplier: float = 1.0
    degradation_multiplier: float = 1.0

class MonteCarloConfig(BaseModel):
    enabled: bool = False
    iterations: int = 1000
    capex_volatility: float = 0.10  # 10% std dev
    market_volatility: float = 0.20  # 20% std dev for revenue
    degradation_volatility: float = 0.05

class BatterySpecs(BaseModel):
    power_mw: float = 100.0
    duration_hours: float = 4.0
    round_trip_efficiency: float = 0.87
    calendar_degradation_rate: float = 0.015  # 1.5% per year
    base_cycle_degradation_rate: float = 0.00003  # % degradation per full equivalent cycle
    dod_non_linear_factor: float = 1.2 # Exponent for Depth of Discharge impact (Rainflow equivalent)
    augmentation_threshold_soc: float = 0.60 # Augment when capacity drops to 60%
    
    @property
    def capacity_mwh(self) -> float:
        return self.power_mw * self.duration_hours

class FinancialAssumptions(BaseModel):
    capex_per_kwh: float = 350.0
    fixed_om_per_mw_year: float = 12000.0
    variable_om_per_mwh: float = 2.5
    grid_connection_cost: float = 5000000.0
    land_lease_per_year: float = 200000.0
    discount_rate: float = 0.08
    project_life_years: int = 20
    capacity_payment_per_mw_year: float = 0.0
    
    # Project Finance Parameters
    cost_of_debt: float = 0.06
    target_dscr: float = 1.30
    debt_tenor_years: int = 15

class InvestmentParams(BaseModel):
    region: str = "SA1"
    battery: BatterySpecs = Field(default_factory=BatterySpecs)
    financial: FinancialAssumptions = Field(default_factory=FinancialAssumptions)
    
    revenue_capture_rate: float = 0.65
    fcas_revenue_per_mw_year: float = 15000.0
    fcas_revenue_mode: FcasRevenueMode = FcasRevenueMode.AUTO
    fcas_activation_probability: float = 0.15 # Real-world probability that FCAS is called and drains SoC
    
    dispatch_mode: DispatchMode = DispatchMode.HINDSIGHT_OPTIMIZED
    forecast_inefficiency: float = 0.15 # Real-world haircut (15%) for lack of perfect foresight in MPC
    
    backtest_years: List[int] = [2024, 2025]
    
    scenarios: List[ScenarioConfig] = [ScenarioConfig()]
    monte_carlo: MonteCarloConfig = Field(default_factory=MonteCarloConfig)

class CashFlowYear(BaseModel):
    year: int
    revenue_arbitrage: float
    revenue_fcas: float
    revenue_capacity: float
    total_revenue: float
    opex: float
    augmentation_capex: float
    net_cash_flow: float
    debt_service: float = 0.0
    levered_cash_flow: float = 0.0
    cumulative_cash_flow: float
    state_of_health: float
    annual_cycles: float

class FinancialMetrics(BaseModel):
    npv: float
    irr: Optional[float]
    roi_pct: float
    payback_years: Optional[int]
    total_capex: float
    
    # Project Finance Metrics
    debt_capacity: float = 0.0
    levered_irr: Optional[float] = None
    dscr_avg: float = 0.0

class ScenarioResult(BaseModel):
    scenario_name: str
    metrics: FinancialMetrics
    cash_flows: List[CashFlowYear]

class MonteCarloResult(BaseModel):
    npv_p10: float
    npv_p50: float
    npv_p90: float
    irr_p10: Optional[float]
    irr_p50: Optional[float]
    irr_p90: Optional[float]

class InvestmentAnalysisResponse(BaseModel):
    region: str
    params_summary: Dict
    base_metrics: FinancialMetrics
    scenarios: List[ScenarioResult]
    monte_carlo: Optional[MonteCarloResult]
    assumptions: List[str]
