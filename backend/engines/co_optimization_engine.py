"""
Co-Optimization Engine for BESS Energy + FCAS Joint Dispatch.

Uses PuLP MILP solver to simultaneously optimize energy arbitrage and FCAS
market participation, subject to physical and market coupling constraints.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal, Optional

import pulp

from engines.dispatch_optimizer import DispatchOptimizer
from models.financial_params import BatterySpecs

logger = logging.getLogger(__name__)

# FCAS delivery durations in hours (used for SOC reserve calculation)
FCAS_DELIVERY_DURATIONS: dict[str, float] = {
    "raise1sec": 1.0 / 3600.0,
    "raise6sec": 6.0 / 3600.0,
    "raise60sec": 60.0 / 3600.0,
    "raise5min": 300.0 / 3600.0,
    "raisereg": 300.0 / 3600.0,
    "lower1sec": 1.0 / 3600.0,
    "lower6sec": 6.0 / 3600.0,
    "lower60sec": 60.0 / 3600.0,
    "lower5min": 300.0 / 3600.0,
    "lowerreg": 300.0 / 3600.0,
}


@dataclass
class CoOptConfig:
    """Co-optimization configuration."""

    fcas_services: list[str]
    fcas_max_capacity_pct: float = 0.5
    time_limit_seconds: int = 60
    optimality_gap_tolerance: float = 0.01
    monthly_segmentation: bool = True


@dataclass
class CoOptimizationResult:
    """Co-optimization result."""

    status: Literal["optimal", "feasible", "infeasible", "timeout"]
    optimality_gap: Optional[float] = None

    # Revenue breakdown
    energy_revenue: float = 0.0
    fcas_revenue: float = 0.0
    total_gross_revenue: float = 0.0
    total_net_revenue: float = 0.0

    # Comparison baseline
    energy_only_revenue: Optional[float] = None
    co_optimization_uplift: Optional[float] = None

    # Constraint binding report
    binding_constraints: list[dict] = field(default_factory=list)

    # Monthly breakdown
    monthly_breakdown: Optional[list[dict]] = None

    # Metadata
    solve_time_seconds: float = 0.0
    solver_status: str = ""


class CoOptimizationEngine:
    """
    LP/MILP co-optimization engine.

    Simultaneously optimizes energy arbitrage and FCAS market participation
    for a Battery Energy Storage System (BESS).
    """

    def __init__(self, specs: BatterySpecs, config: CoOptConfig):
        self.specs = specs
        self.config = config

        # Derived battery parameters
        self.power_mw = specs.power_mw
        self.energy_mwh = specs.capacity_mwh
        self.eta = specs.round_trip_efficiency**0.5  # one-way efficiency
        self.min_soc_mwh = self.energy_mwh * 0.05  # 5% min SOC
        self.max_soc_mwh = self.energy_mwh * 0.95  # 95% max SOC
        self.initial_soc_mwh = self.energy_mwh * 0.5  # 50% initial SOC

        # Separate raise and lower services
        self.raise_services = [s for s in config.fcas_services if s.startswith("raise")]
        self.lower_services = [s for s in config.fcas_services if s.startswith("lower")]

    def optimize(
        self,
        energy_prices: list[dict],
        fcas_prices: dict[str, list[float]],
        *,
        variable_om_per_mwh: float = 2.5,
        network_fee_per_mwh: float = 0.0,
        degradation_cost_per_mwh: float = 0.0,
    ) -> CoOptimizationResult:
        """
        Execute co-optimization.

        Args:
            energy_prices: List of dicts with keys: timestamp, price, interval_hours.
            fcas_prices: Dict mapping service name to list of prices per interval.
            variable_om_per_mwh: Variable O&M cost per MWh throughput.
            network_fee_per_mwh: Network fee per MWh discharged.
            degradation_cost_per_mwh: Degradation cost per MWh throughput.

        Returns:
            CoOptimizationResult with revenue breakdown and metadata.
        """
        if not energy_prices:
            return CoOptimizationResult(
                status="infeasible",
                solver_status="no_data",
            )

        # Solve co-optimization
        if self.config.monthly_segmentation and len(energy_prices) > 1000:
            result = self._solve_monthly(
                energy_prices,
                fcas_prices,
                variable_om_per_mwh=variable_om_per_mwh,
                network_fee_per_mwh=network_fee_per_mwh,
                degradation_cost_per_mwh=degradation_cost_per_mwh,
            )
        else:
            result = self._solve_full(
                energy_prices,
                fcas_prices,
                variable_om_per_mwh=variable_om_per_mwh,
                network_fee_per_mwh=network_fee_per_mwh,
                degradation_cost_per_mwh=degradation_cost_per_mwh,
            )

        # Calculate energy-only baseline for uplift comparison
        if result.status in ("optimal", "feasible"):
            energy_only = self._compute_energy_only_baseline(energy_prices)
            result.energy_only_revenue = energy_only
            if energy_only is not None:
                result.co_optimization_uplift = result.total_net_revenue - energy_only

        return result

    def _solve_full(
        self,
        energy_prices: list[dict],
        fcas_prices: dict[str, list[float]],
        *,
        variable_om_per_mwh: float = 2.5,
        network_fee_per_mwh: float = 0.0,
        degradation_cost_per_mwh: float = 0.0,
    ) -> CoOptimizationResult:
        """Build and solve the full MILP model."""
        start_time = time.time()

        n = len(energy_prices)
        prob = pulp.LpProblem("BESS_CoOpt", pulp.LpMaximize)

        # --- Decision Variables ---
        charge = [
            pulp.LpVariable(f"charge_{t}", lowBound=0, upBound=self.power_mw)
            for t in range(n)
        ]
        discharge = [
            pulp.LpVariable(f"discharge_{t}", lowBound=0, upBound=self.power_mw)
            for t in range(n)
        ]
        soc = [
            pulp.LpVariable(
                f"soc_{t}", lowBound=self.min_soc_mwh, upBound=self.max_soc_mwh
            )
            for t in range(n)
        ]
        is_charging = [
            pulp.LpVariable(f"is_charging_{t}", cat=pulp.LpBinary) for t in range(n)
        ]

        # FCAS variables: fcas_raise[t][s] and fcas_lower[t][s]
        fcas_raise: dict[str, list[pulp.LpVariable]] = {}
        for s in self.raise_services:
            fcas_raise[s] = [
                pulp.LpVariable(f"fcas_raise_{s}_{t}", lowBound=0, upBound=self.power_mw)
                for t in range(n)
            ]

        fcas_lower: dict[str, list[pulp.LpVariable]] = {}
        for s in self.lower_services:
            fcas_lower[s] = [
                pulp.LpVariable(f"fcas_lower_{s}_{t}", lowBound=0, upBound=self.power_mw)
                for t in range(n)
            ]

        # --- Constraints ---
        for t in range(n):
            dt = float(energy_prices[t].get("interval_hours", 5.0 / 60.0))

            # Constraint 1: Charge/discharge mutual exclusion
            prob += charge[t] <= self.power_mw * is_charging[t], f"charge_mutex_{t}"
            prob += (
                discharge[t] <= self.power_mw * (1 - is_charging[t]),
                f"discharge_mutex_{t}",
            )

            # Constraint 2: SOC dynamics
            if t == 0:
                prob += (
                    soc[t]
                    == self.initial_soc_mwh
                    + charge[t] * dt * self.eta
                    - discharge[t] * dt / self.eta,
                    f"soc_dynamics_{t}",
                )
            else:
                prob += (
                    soc[t]
                    == soc[t - 1]
                    + charge[t] * dt * self.eta
                    - discharge[t] * dt / self.eta,
                    f"soc_dynamics_{t}",
                )

            # Constraint 3: FCAS coupling with energy dispatch
            # discharge[t] + sum(fcas_raise[t][s]) <= P_max * (1 - is_charging[t])
            sum_raise = pulp.lpSum(
                fcas_raise[s][t] for s in self.raise_services
            )
            prob += (
                discharge[t] + sum_raise <= self.power_mw * (1 - is_charging[t]),
                f"fcas_raise_coupling_{t}",
            )

            # charge[t] + sum(fcas_lower[t][s]) <= P_max * is_charging[t]
            sum_lower = pulp.lpSum(
                fcas_lower[s][t] for s in self.lower_services
            )
            prob += (
                charge[t] + sum_lower <= self.power_mw * is_charging[t],
                f"fcas_lower_coupling_{t}",
            )

            # Constraint 4: FCAS capacity cap
            prob += (
                sum_raise <= self.power_mw * self.config.fcas_max_capacity_pct,
                f"fcas_raise_cap_{t}",
            )
            prob += (
                sum_lower <= self.power_mw * self.config.fcas_max_capacity_pct,
                f"fcas_lower_cap_{t}",
            )

            # Constraint 5: SOC reserve for FCAS delivery
            # soc[t] >= min_soc + sum(fcas_raise[t][s] * delivery_duration[s])
            raise_soc_reserve = pulp.lpSum(
                fcas_raise[s][t] * FCAS_DELIVERY_DURATIONS.get(s, 0.0)
                for s in self.raise_services
            )
            prob += (
                soc[t] >= self.min_soc_mwh + raise_soc_reserve,
                f"soc_reserve_raise_{t}",
            )

            # soc[t] <= max_soc - sum(fcas_lower[t][s] * delivery_duration[s])
            lower_soc_reserve = pulp.lpSum(
                fcas_lower[s][t] * FCAS_DELIVERY_DURATIONS.get(s, 0.0)
                for s in self.lower_services
            )
            prob += (
                soc[t] <= self.max_soc_mwh - lower_soc_reserve,
                f"soc_reserve_lower_{t}",
            )

        # Constraint 6: Terminal SOC
        prob += soc[n - 1] == self.initial_soc_mwh, "terminal_soc"

        # --- Objective Function ---
        # Energy revenue: (discharge - charge) * dt * price
        energy_revenue_expr = pulp.lpSum(
            (discharge[t] - charge[t])
            * float(energy_prices[t].get("interval_hours", 5.0 / 60.0))
            * float(energy_prices[t].get("price", 0.0))
            for t in range(n)
        )

        # FCAS revenue: sum over services and intervals
        fcas_revenue_expr = pulp.lpSum(
            fcas_raise[s][t]
            * float(energy_prices[t].get("interval_hours", 5.0 / 60.0))
            * float(fcas_prices.get(s, [0.0] * n)[t] if t < len(fcas_prices.get(s, [])) else 0.0)
            for s in self.raise_services
            for t in range(n)
        ) + pulp.lpSum(
            fcas_lower[s][t]
            * float(energy_prices[t].get("interval_hours", 5.0 / 60.0))
            * float(fcas_prices.get(s, [0.0] * n)[t] if t < len(fcas_prices.get(s, [])) else 0.0)
            for s in self.lower_services
            for t in range(n)
        )

        # Costs
        throughput_expr = pulp.lpSum(
            (charge[t] + discharge[t])
            * float(energy_prices[t].get("interval_hours", 5.0 / 60.0))
            for t in range(n)
        )
        discharge_mwh_expr = pulp.lpSum(
            discharge[t] * float(energy_prices[t].get("interval_hours", 5.0 / 60.0))
            for t in range(n)
        )

        cost_expr = (
            throughput_expr * (variable_om_per_mwh + degradation_cost_per_mwh)
            + discharge_mwh_expr * network_fee_per_mwh
        )

        # Objective: maximize revenue - costs
        prob += energy_revenue_expr + fcas_revenue_expr - cost_expr

        # --- Solve ---
        solver = pulp.PULP_CBC_CMD(
            msg=False,
            timeLimit=self.config.time_limit_seconds,
            gapRel=self.config.optimality_gap_tolerance,
        )
        prob.solve(solver)

        solve_time = time.time() - start_time
        solver_status = pulp.LpStatus[prob.status]

        # --- Extract Results ---
        if prob.status == pulp.constants.LpStatusInfeasible:
            return CoOptimizationResult(
                status="infeasible",
                solve_time_seconds=round(solve_time, 3),
                solver_status=solver_status,
            )

        if prob.status == pulp.constants.LpStatusNotSolved:
            return CoOptimizationResult(
                status="timeout",
                solve_time_seconds=round(solve_time, 3),
                solver_status=solver_status,
            )

        # Determine status: optimal vs feasible (timeout with solution)
        status: Literal["optimal", "feasible", "infeasible", "timeout"]
        optimality_gap: Optional[float] = None

        if prob.status == pulp.constants.LpStatusOptimal:
            status = "optimal"
        else:
            # Solver found a feasible solution but may not be optimal
            # (e.g., hit time limit)
            if pulp.value(prob.objective) is not None:
                status = "feasible"
                # Estimate optimality gap from solver
                optimality_gap = self._estimate_gap(prob)
            else:
                return CoOptimizationResult(
                    status="timeout",
                    solve_time_seconds=round(solve_time, 3),
                    solver_status=solver_status,
                )

        # Calculate revenue components
        energy_rev = float(pulp.value(energy_revenue_expr) or 0.0)
        fcas_rev = float(pulp.value(fcas_revenue_expr) or 0.0)
        total_cost = float(pulp.value(cost_expr) or 0.0)
        total_gross = energy_rev + fcas_rev
        total_net = total_gross - total_cost

        # Identify binding constraints
        binding = self._identify_binding_constraints(prob, n)

        return CoOptimizationResult(
            status=status,
            optimality_gap=optimality_gap,
            energy_revenue=round(energy_rev, 2),
            fcas_revenue=round(fcas_rev, 2),
            total_gross_revenue=round(total_gross, 2),
            total_net_revenue=round(total_net, 2),
            binding_constraints=binding,
            solve_time_seconds=round(solve_time, 3),
            solver_status=solver_status,
        )

    def _solve_monthly(
        self,
        energy_prices: list[dict],
        fcas_prices: dict[str, list[float]],
        *,
        variable_om_per_mwh: float = 2.5,
        network_fee_per_mwh: float = 0.0,
        degradation_cost_per_mwh: float = 0.0,
    ) -> CoOptimizationResult:
        """Solve by monthly segments and aggregate results."""
        segments = self._segment_by_month(energy_prices, fcas_prices)
        monthly_results: list[CoOptimizationResult] = []

        total_solve_time = 0.0
        for segment in segments:
            result = self._solve_full(
                segment["energy"],
                segment["fcas"],
                variable_om_per_mwh=variable_om_per_mwh,
                network_fee_per_mwh=network_fee_per_mwh,
                degradation_cost_per_mwh=degradation_cost_per_mwh,
            )
            monthly_results.append(result)
            total_solve_time += result.solve_time_seconds

        return self._aggregate_monthly(monthly_results, total_solve_time)

    def _segment_by_month(
        self,
        energy_prices: list[dict],
        fcas_prices: dict[str, list[float]],
    ) -> list[dict]:
        """Split annual data into monthly segments."""
        # Group intervals by month based on timestamp
        month_groups: dict[str, list[int]] = defaultdict(list)

        for idx, row in enumerate(energy_prices):
            ts = str(row.get("timestamp", ""))
            # Extract month key (YYYY-MM) from timestamp
            month_key = ts[:7] if len(ts) >= 7 else f"month_{idx // 8760}"
            month_groups[month_key].append(idx)

        segments = []
        for _month_key, indices in sorted(month_groups.items()):
            month_energy = [energy_prices[i] for i in indices]
            month_fcas: dict[str, list[float]] = {}
            for service, prices in fcas_prices.items():
                month_fcas[service] = [
                    prices[i] for i in indices if i < len(prices)
                ]
            segments.append({"energy": month_energy, "fcas": month_fcas})

        return segments

    def _aggregate_monthly(
        self,
        monthly_results: list[CoOptimizationResult],
        total_solve_time: float,
    ) -> CoOptimizationResult:
        """Aggregate monthly results into annual result."""
        if not monthly_results:
            return CoOptimizationResult(
                status="infeasible",
                solver_status="no_monthly_data",
            )

        # Determine overall status
        statuses = [r.status for r in monthly_results]
        if "infeasible" in statuses:
            overall_status: Literal["optimal", "feasible", "infeasible", "timeout"] = "infeasible"
        elif "feasible" in statuses or "timeout" in statuses:
            overall_status = "feasible"
        else:
            overall_status = "optimal"

        # Aggregate revenues
        total_energy_rev = sum(r.energy_revenue for r in monthly_results)
        total_fcas_rev = sum(r.fcas_revenue for r in monthly_results)
        total_gross = sum(r.total_gross_revenue for r in monthly_results)
        total_net = sum(r.total_net_revenue for r in monthly_results)

        # Aggregate binding constraints
        all_binding: list[dict] = []
        for r in monthly_results:
            all_binding.extend(r.binding_constraints)

        # Compute max optimality gap across months
        gaps = [r.optimality_gap for r in monthly_results if r.optimality_gap is not None]
        max_gap = max(gaps) if gaps else None

        # Build monthly breakdown
        monthly_breakdown = []
        for idx, r in enumerate(monthly_results):
            monthly_breakdown.append(
                {
                    "month_index": idx + 1,
                    "status": r.status,
                    "energy_revenue": r.energy_revenue,
                    "fcas_revenue": r.fcas_revenue,
                    "total_gross_revenue": r.total_gross_revenue,
                    "total_net_revenue": r.total_net_revenue,
                    "solve_time_seconds": r.solve_time_seconds,
                }
            )

        return CoOptimizationResult(
            status=overall_status,
            optimality_gap=max_gap,
            energy_revenue=round(total_energy_rev, 2),
            fcas_revenue=round(total_fcas_rev, 2),
            total_gross_revenue=round(total_gross, 2),
            total_net_revenue=round(total_net, 2),
            binding_constraints=all_binding,
            monthly_breakdown=monthly_breakdown,
            solve_time_seconds=round(total_solve_time, 3),
            solver_status="aggregated",
        )

    def _compute_energy_only_baseline(
        self, energy_prices: list[dict]
    ) -> Optional[float]:
        """
        Compute energy-only optimized revenue using the existing DispatchOptimizer
        as a comparison baseline.
        """
        try:
            # Prepare interval data in the format expected by DispatchOptimizer
            interval_data = []
            for row in energy_prices:
                interval_data.append(
                    {
                        "timestamp": row.get("timestamp"),
                        "energy_price": float(row.get("price", 0.0)),
                        "interval_hours": float(row.get("interval_hours", 5.0 / 60.0)),
                    }
                )

            results = DispatchOptimizer.run_hindsight_optimization(
                interval_data, self.specs
            )

            if not results:
                return None

            # Calculate total energy-only revenue
            interval_hours = 5.0 / 60.0  # Default NEM 5-min intervals
            total_revenue = 0.0
            for row in results:
                mw = float(row.get("optimized_arbitrage_mw", 0.0))
                price = float(row.get("energy_price", 0.0))
                dt = float(row.get("interval_hours", interval_hours))
                total_revenue += mw * dt * price

            return round(total_revenue, 2)

        except Exception as e:
            logger.warning(f"Energy-only baseline calculation failed: {e}")
            return None

    def _estimate_gap(self, prob: pulp.LpProblem) -> Optional[float]:
        """Estimate optimality gap from solver information."""
        try:
            # CBC solver stores gap info; try to extract it
            obj_val = pulp.value(prob.objective)
            if obj_val is None:
                return None
            # If solver provides best bound, compute gap
            # PuLP doesn't always expose this directly, so we use a conservative estimate
            # based on the gap tolerance we set
            return self.config.optimality_gap_tolerance
        except Exception:
            return None

    def _identify_binding_constraints(
        self, prob: pulp.LpProblem, n_intervals: int
    ) -> list[dict]:
        """Identify which constraint categories are frequently binding."""
        binding_counts: dict[str, int] = defaultdict(int)

        for name, constraint in prob.constraints.items():
            # A constraint is binding if its slack is approximately zero
            slack = constraint.slack
            if slack is not None and abs(slack) < 1e-6:
                # Categorize by constraint prefix
                if "charge_mutex" in name or "discharge_mutex" in name:
                    binding_counts["mutual_exclusion"] += 1
                elif "fcas_raise_coupling" in name or "fcas_lower_coupling" in name:
                    binding_counts["fcas_coupling"] += 1
                elif "fcas_raise_cap" in name or "fcas_lower_cap" in name:
                    binding_counts["fcas_capacity_cap"] += 1
                elif "soc_reserve" in name:
                    binding_counts["soc_reserve"] += 1
                elif "soc_dynamics" in name:
                    binding_counts["soc_dynamics"] += 1
                elif "terminal_soc" in name:
                    binding_counts["terminal_soc"] += 1

        # Max possible bindings per category (some have 2 constraints per interval)
        max_bindings = {
            "mutual_exclusion": n_intervals * 2,
            "fcas_coupling": n_intervals * 2,
            "fcas_capacity_cap": n_intervals * 2,
            "soc_reserve": n_intervals * 2,
            "soc_dynamics": n_intervals,
            "terminal_soc": 1,
        }

        results = []
        for category, count in sorted(binding_counts.items(), key=lambda x: -x[1]):
            max_possible = max_bindings.get(category, n_intervals)
            pct = round(count / max(max_possible, 1) * 100, 1)
            results.append(
                {
                    "constraint": category,
                    "binding_intervals": count,
                    "binding_pct": pct,
                }
            )

        return results
