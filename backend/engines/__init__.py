# Engines package
from .market_adapter import MarketAdapter
from .battery_model import BatteryModel
from .dispatch_optimizer import DispatchOptimizer
from .revenue_model import RevenueModel
from .financial_model import FinancialModel
from .exceptions import DimensionMismatchError
from .price_analysis_engine import PriceAnalysisEngine, PriceAnalysisResult, AnalysisMetadata
from .revenue_analysis_engine import RevenueAnalysisEngine, RevenueAnalysisResult
from .benchmark_engine import (
    build_nem_bess_benchmark,
    build_nem_bess_region_compare,
)
from .degradation_model import DegradationModel
from .bess_backtest_v2 import (
    BacktestConstraints,
    BacktestV2Params,
    BacktestV2Result,
    BindingConstraintRecord,
    run_bess_backtest_v2,
)

__all__ = [
    "MarketAdapter",
    "BatteryModel",
    "DispatchOptimizer",
    "RevenueModel",
    "FinancialModel",
    "DimensionMismatchError",
    "PriceAnalysisEngine",
    "PriceAnalysisResult",
    "AnalysisMetadata",
    "RevenueAnalysisEngine",
    "RevenueAnalysisResult",
    "build_nem_bess_benchmark",
    "build_nem_bess_region_compare",
    "DegradationModel",
    "BacktestConstraints",
    "BacktestV2Params",
    "BacktestV2Result",
    "BindingConstraintRecord",
    "run_bess_backtest_v2",
]
