"""Co-optimized energy+FCAS revenue baseline (S2/B2).

Wraps :class:`CoOptimizationEngine` to produce a single energy+FCAS jointly
optimized annual revenue baseline for investment analysis. This replaces the
additive ``arbitrage + FCAS`` path which double-counts power capacity (arbitrage
assumes full power AND FCAS assumes full power on the same MW).

The engine is deliberately run with ZERO internal O&M / network / degradation
costs so the returned energy/FCAS figures are GROSS revenue. This matches the
additive path's convention where the financial model applies operating costs
separately, keeping the two baselines comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engines.co_optimization_engine import CoOptConfig, CoOptimizationEngine
from models.financial_params import BatterySpecs, InvestmentParams

# Raise + lower FCAS services understood by the engine. Excludes the 1-second
# contingency services which are sparsely populated in historical tables; the
# route filters these further against the actual FCAS column map.
DEFAULT_FCAS_SERVICES = [
    "raise6sec",
    "raise60sec",
    "raise5min",
    "raisereg",
    "lower6sec",
    "lower60sec",
    "lower5min",
    "lowerreg",
]


@dataclass
class CoOptimizedBaseline:
    """Averaged co-optimization outcome across the requested backtest years."""

    energy_revenue: float
    fcas_revenue: float
    total_net_revenue: float
    energy_only_revenue: Optional[float]
    co_optimization_uplift: Optional[float]
    years_used: int
    status: str


def derive_co_optimized_baseline(
    params: InvestmentParams,
    yearly_price_data: list[dict],
    *,
    fcas_services: Optional[list[str]] = None,
    fcas_max_capacity_pct: float = 0.5,
    time_limit_seconds: int = 60,
) -> CoOptimizedBaseline:
    """Run the joint optimization per backtest year and average the results.

    Args:
        params: Investment parameters (battery specs drive the engine).
        yearly_price_data: One dict per backtest year with keys ``energy_prices``
            (list of ``{timestamp, price, interval_hours}``) and ``fcas_prices``
            (dict mapping service -> list of prices per interval).
        fcas_services: FCAS services to co-optimize. Defaults to
            :data:`DEFAULT_FCAS_SERVICES`.
        fcas_max_capacity_pct: Cap on power reserved for FCAS enablement.
        time_limit_seconds: Per-year solver time limit.

    Returns:
        A :class:`CoOptimizedBaseline` averaged over the years that produced a
        feasible/optimal solution. ``years_used == 0`` signals the caller should
        fall back to the additive baseline.
    """
    services = list(fcas_services) if fcas_services else list(DEFAULT_FCAS_SERVICES)
    specs = BatterySpecs(
        power_mw=params.battery.power_mw,
        duration_hours=params.battery.duration_hours,
        round_trip_efficiency=params.battery.round_trip_efficiency,
    )
    config = CoOptConfig(
        fcas_services=services,
        fcas_max_capacity_pct=fcas_max_capacity_pct,
        time_limit_seconds=time_limit_seconds,
        monthly_segmentation=True,
    )

    energy_sum = 0.0
    fcas_sum = 0.0
    net_sum = 0.0
    energy_only_sum = 0.0
    uplift_sum = 0.0
    energy_only_years = 0
    uplift_years = 0
    valid_years = 0
    last_status = "no_data"

    for year_data in yearly_price_data:
        energy_prices = year_data.get("energy_prices") or []
        fcas_prices = year_data.get("fcas_prices") or {}
        if not energy_prices:
            continue

        engine = CoOptimizationEngine(specs, config)
        result = engine.optimize(
            energy_prices,
            fcas_prices,
            variable_om_per_mwh=0.0,
            network_fee_per_mwh=0.0,
            degradation_cost_per_mwh=0.0,
        )
        last_status = result.status
        if result.status not in ("optimal", "feasible"):
            continue

        energy_sum += result.energy_revenue
        fcas_sum += result.fcas_revenue
        net_sum += result.total_net_revenue
        if result.energy_only_revenue is not None:
            energy_only_sum += result.energy_only_revenue
            energy_only_years += 1
        if result.co_optimization_uplift is not None:
            uplift_sum += result.co_optimization_uplift
            uplift_years += 1
        valid_years += 1

    if valid_years == 0:
        return CoOptimizedBaseline(
            energy_revenue=0.0,
            fcas_revenue=0.0,
            total_net_revenue=0.0,
            energy_only_revenue=None,
            co_optimization_uplift=None,
            years_used=0,
            status=last_status,
        )

    return CoOptimizedBaseline(
        energy_revenue=energy_sum / valid_years,
        fcas_revenue=fcas_sum / valid_years,
        total_net_revenue=net_sum / valid_years,
        energy_only_revenue=(energy_only_sum / energy_only_years) if energy_only_years else None,
        co_optimization_uplift=(uplift_sum / uplift_years) if uplift_years else None,
        years_used=valid_years,
        status=last_status,
    )
