"""
Co-Optimization Pydantic models for API request/response.

Defines CoOptimizationParams (request body) and CoOptimizationResult (response)
for the co-optimization backtest endpoint.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CoOptimizationParams(BaseModel):
    """联合优化请求参数"""

    market: Literal["NEM", "WEM"]
    region: str
    year: int
    month: Optional[int] = Field(default=None, ge=1, le=12)  # None = 全年优化

    # BESS 参数
    power_mw: float = Field(default=100, gt=0)
    duration_hours: float = Field(default=4, gt=0)
    round_trip_efficiency: float = Field(default=0.87, gt=0, le=1)
    min_soc_pct: float = Field(default=5, ge=0, le=100)
    max_soc_pct: float = Field(default=95, ge=0, le=100)

    # FCAS 参数
    fcas_services: list[str] = Field(
        default_factory=lambda: ["raise6sec", "raise60sec", "raise5min"]
    )
    fcas_max_capacity_pct: float = Field(
        default=0.5, ge=0, le=1, description="FCAS 最大预留比例"
    )

    # 求解精度模式
    resolution: Literal["fast", "precise"] = Field(
        default="fast",
        description="fast=30min intervals (~6s), precise=5min intervals (~60-90s)",
    )

    # 求解器参数
    time_limit_seconds: int = Field(default=60, ge=10, le=300)
    optimality_gap_tolerance: float = Field(default=0.01, ge=0, le=0.1)

    # 成本参数
    variable_om_per_mwh: float = Field(default=2.5, ge=0)
    network_fee_per_mwh: float = Field(default=0, ge=0)
    degradation_cost_per_mwh: float = Field(default=0, ge=0)


class CoOptimizationResponse(BaseModel):
    """联合优化结果响应"""

    status: Literal["optimal", "feasible", "infeasible", "timeout"]
    optimality_gap: Optional[float] = None

    # 收入分项
    energy_revenue: float
    fcas_revenue: float
    total_gross_revenue: float
    total_net_revenue: float

    # 对比基准
    energy_only_revenue: Optional[float] = None
    co_optimization_uplift: Optional[float] = None

    # 约束绑定报告
    binding_constraints: list[dict] = Field(default_factory=list)

    # 月度分解
    monthly_breakdown: Optional[list[dict]] = None

    # 元数据
    solve_time_seconds: float = 0
    solver_status: str = ""
