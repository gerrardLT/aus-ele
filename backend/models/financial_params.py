from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Optional, Dict, Union, TYPE_CHECKING
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

    # Optional per-year revenue multipliers (used by Monte Carlo AR(1) draws).
    # When present, they override the scalar multiplier for each project year,
    # allowing year-to-year revenue variation instead of a single persistent shock.
    arbitrage_multipliers_by_year: Optional[List[float]] = None
    fcas_multipliers_by_year: Optional[List[float]] = None

class MonteCarloConfig(BaseModel):
    enabled: bool = False
    iterations: int = 1000
    capex_volatility: float = 0.10  # 10% std dev (log-space sigma)
    market_volatility: float = 0.20  # 20% std dev for revenue (log-space sigma)
    degradation_volatility: float = 0.05

    # Reproducibility: when None a fixed default seed is used so runs are
    # auditable/repeatable. Callers may pass an explicit seed to vary draws.
    seed: Optional[int] = None
    # Correlation between arbitrage and FCAS revenue shocks (0=independent,
    # 1=perfectly correlated). Default reflects a moderate positive linkage.
    arb_fcas_correlation: float = 0.6
    # AR(1) coefficient for year-to-year revenue persistence (0=iid shocks,
    # 1=fully persistent). Avoids the "permanent shock" assumption.
    revenue_autocorrelation: float = 0.3


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
    # End-of-life "knee": below this SoH, degradation accelerates by knee_acceleration_factor.
    # Reflects the well-documented non-linear end-of-life capacity fade of Li-ion cells.
    knee_point_soh: float = 0.70
    knee_acceleration_factor: float = 1.5

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
    # S4/M3: "annuity" (default, constant payment) or "sculpting" (principal
    # repaid proportionally to CFADS to maintain constant DSCR each year).
    debt_repayment_mode: Literal["annuity", "sculpting"] = "annuity"

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
    # Revenue baseline construction (S2/B2). "additive" keeps the historical
    # arbitrage + FCAS sum (default, zero-regression). "co_optimized" derives a
    # single energy+FCAS jointly-optimized baseline from CoOptimizationEngine,
    # eliminating the power-capacity double-count of the additive path.
    revenue_baseline_mode: Literal["additive", "co_optimized"] = "additive"
    fcas_activation_probability: float = 0.15 # Real-world probability that FCAS is called and drains SoC
    
    dispatch_mode: DispatchMode = DispatchMode.HINDSIGHT_OPTIMIZED
    # Realizable arbitrage revenue is decomposed into two independent haircuts:
    #   1. HORIZON haircut - measured empirically by the receding-horizon (MPC)
    #      backtest: rolling net vs perfect-foresight net. Captures the value
    #      lost because a real operator can only see a finite look-ahead window
    #      (typically ~1% for a 24h commit + 24h look-ahead on NEM data).
    #   2. FORECAST-ERROR haircut - this knob. Captures the value lost because a
    #      real operator dispatches against *imperfect* price forecasts (plus
    #      bid/offer slippage and forced outages), which the MPC backtest cannot
    #      model because it optimises against realised prices.
    # The two are multiplicative and NOT double-counted: the MPC rolling net
    # already embeds only the horizon truncation (~1%), so this knob adds the
    # forecast-error loss on top. Default 0.11 is anchored to the literature
    # (Hornek et al. 2025, arXiv:2501.07121: forecast-driven vs perfect-foresight
    # dispatch loses ~11% of arbitrage value on European day-ahead/intraday).
    forecast_inefficiency: float = 0.11
    
    backtest_years: List[int] = [2024, 2025]

    # S3/B3: Cannibalization effect —逐年价差衰减因子注入多年现金流。
    # 幂律模型: decay_factor_t = 1 / (1 + annual_growth_rate * t) ^ alpha
    # 默认关闭，零回归。
    apply_cannibalization: bool = False
    cannibalization_alpha: float = 0.6  # 幂律指数（QLD实证拟合≈0.6）
    cannibalization_annual_growth_rate: float = 0.10  # 市场BESS容量年增长率

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
    payback_years: Optional[float]  # S4/M1: fractional (linear interpolation)
    total_capex: float

    # S4/M2: IRR reliability flag and MIRR fallback
    irr_reliable: bool = True
    mirr: Optional[float] = None

    # S4/M5: ROI is undiscounted (sum of future CF / CAPEX)
    roi_undiscounted: bool = True

    # Project Finance Metrics
    debt_capacity: float = 0.0
    levered_irr: Optional[float] = None
    dscr_avg: float = 0.0
    min_dscr: float = 0.0
    llcr: Optional[float] = None  # S4/M4: Loan Life Coverage Ratio

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

    # Reproducibility metadata (backward-compatible additions).
    seed: Optional[int] = None
    iterations: Optional[int] = None

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
