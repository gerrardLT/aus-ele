from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Union, TYPE_CHECKING
from enum import Enum

from models.bess_backtest_params import BessBacktestParams
from models.cost_structure_models import CostStructureOverrides, AnnualCostBreakdown
from models.tax_models import TaxConfig, AfterTaxResult, TaxSummary
from models.forward_price_models import ScenarioType, ScenarioComparisonResult

if TYPE_CHECKING:
    from engines.degradation_model import DegradationModel

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


class RevenueModel(str, Enum):
    """收入模型类型 — 反映项目商业结构。"""
    PURE_MERCHANT = "pure_merchant"           # 100% 市场套利（无合约）
    CIS_CONTRACTED = "cis_contracted"         # CIS 合约（floor + ceiling + cap）
    OFFTAKE_CONTRACTED = "offtake_contracted" # 长期 offtake（固定价格）
    HYBRID = "hybrid"                         # 部分容量合约 + 部分 merchant


class CISContract(BaseModel):
    """Capacity Investment Scheme 合约参数。

    实际 CIS 三层结构（基于 DCCEEW 官方机制）:
    - Revenue Floor: 政府补贴 floor_share 比例（默认 90%）的差额
    - Revenue Ceiling: 项目交回 ceiling_share 比例（默认 50%）给政府
    - Annual Payment Cap: 双向支付的年度上限

    收入计算:
        adjusted = merchant
                 + max(0, floor_share × (floor × eligible_MWh − merchant))   # 政府补 floor
                 - max(0, ceiling_share × (merchant − ceiling × eligible_MWh)) # 项目交 ceiling
        其中 floor 和 ceiling 支付都受 annual_payment_cap_aud 限制。
    """
    revenue_floor_per_mwh: float = 80.0       # bid floor price ($/MWh of eligible energy)
    revenue_ceiling_per_mwh: float = 200.0    # bid ceiling price ($/MWh of eligible energy)
    annual_payment_cap_aud: float = 15_000_000.0  # 年度支付上限（双向适用）
    floor_share: float = 0.90                 # 政府补贴 floor 差额的比例
    ceiling_share: float = 0.50               # 项目交回 ceiling 超额的比例
    eligible_mwh_per_mw_year: float = 800.0   # 每 MW 容量的 eligible energy（标准 4h × 200 cycles ≈ 800MWh/MW）
    contract_years: int = 13                  # CIS 合约期限（默认 13 年）


class BatterySpecs(BaseModel):
    power_mw: float = 100.0
    duration_hours: float = 4.0
    round_trip_efficiency: float = 0.87
    calendar_degradation_rate: float = 0.015  # 1.5% per year
    base_cycle_degradation_rate: float = 0.00003  # % degradation per full equivalent cycle
    dod_non_linear_factor: float = 1.2 # Exponent for Depth of Discharge impact (Rainflow equivalent)
    augmentation_threshold_soc: float = 0.60 # Augment when capacity drops to 60%

    # --- 收入结构（CIS 合约支持）---
    revenue_model: RevenueModel = RevenueModel.PURE_MERCHANT
    contracted_capacity_share: float = 0.0    # 合约容量比例 [0, 1]，hybrid 项目用
    cis_contract: Optional[CISContract] = None  # CIS 合约参数（仅 cis_contracted/hybrid 项目）
    offtake_price_per_mwh: Optional[float] = None  # 固定 offtake 价格（offtake_contracted 项目）

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

    # Legacy flat fields kept for compatibility with existing tests and UI payloads.
    power_mw: Optional[float] = None
    duration_hours: Optional[float] = None
    degradation_rate: Optional[float] = None
    discount_rate: Optional[float] = None
    
    revenue_capture_rate: float = 0.65
    fcas_revenue_per_mw_year: float = 15000.0
    fcas_revenue_mode: FcasRevenueMode = FcasRevenueMode.AUTO
    fcas_activation_probability: float = 0.15 # Real-world probability that FCAS is called and drains SoC
    
    dispatch_mode: DispatchMode = DispatchMode.HINDSIGHT_OPTIMIZED
    forecast_inefficiency: float = 0.15 # Real-world haircut (15%) for lack of perfect foresight in MPC
    
    backtest_years: List[int] = [2024, 2025]
    
    scenarios: List[ScenarioConfig] = [ScenarioConfig()]
    monte_carlo: MonteCarloConfig = Field(default_factory=MonteCarloConfig)

    # Financial Accuracy Module optional fields (backward-compatible)
    cost_structure_overrides: Optional[CostStructureOverrides] = None
    tax_config: Optional[TaxConfig] = None
    forward_scenario: Optional[ScenarioType] = None

    @model_validator(mode="after")
    def apply_legacy_overrides(self):
        if self.power_mw is not None:
            self.battery.power_mw = self.power_mw
        if self.duration_hours is not None:
            self.battery.duration_hours = self.duration_hours
        if self.degradation_rate is not None:
            self.battery.calendar_degradation_rate = self.degradation_rate
        if self.discount_rate is not None:
            self.financial.discount_rate = self.discount_rate
        return self

    def to_bess_backtest_params(self, year: Optional[int] = None) -> BessBacktestParams:
        return BessBacktestParams.from_investment_params(self, year=year)

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

    # Tax-related fields (Financial Accuracy Modules)
    depreciation: float = 0.0
    tax_payable: float = 0.0
    after_tax_cash_flow: Optional[float] = None

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
    cost_breakdown: Optional[AnnualCostBreakdown] = None

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
    degradation_model: Optional["DegradationModel"] = None
    assumptions: List[str]

    # Financial Accuracy Module optional fields (backward-compatible)
    cost_breakdown: Optional[AnnualCostBreakdown] = None
    tax_summary: Optional[TaxSummary] = None
    scenario_projections: Optional[ScenarioComparisonResult] = None
    after_tax_metrics: Optional[AfterTaxResult] = None


def rebuild_forward_refs() -> None:
    """Resolve forward references after all modules are loaded.

    Call this once at application startup to resolve the DegradationModel
    forward reference in InvestmentAnalysisResponse.
    """
    from engines.degradation_model import DegradationModel  # noqa: F811

    InvestmentAnalysisResponse.model_rebuild()
