"""
BESS Backtest Engine V2 — Enhanced constraint modeling.

Extends V1 with:
- Separate max charge/discharge power limits
- Auxiliary power consumption
- Minimum duration constraints
- Dispatch interval alignment
- Registered capacity limits
- Binding constraint reporting
- Infeasibility handling with constraint conflict reporting
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

import pulp
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Constraint Configuration
# ---------------------------------------------------------------------------


@dataclass
class BacktestConstraints:
    """Backtest Engine V2 constraint configuration."""

    # Physical constraints
    max_charge_mw: float
    max_discharge_mw: float
    min_soc_pct: float
    max_soc_pct: float
    round_trip_efficiency: float
    auxiliary_power_mw: float = 0.0

    # Market constraints
    min_duration_intervals: int = 1
    dispatch_alignment_minutes: int = 5
    registered_capacity_mw: float | None = None

    def validate(self) -> list[str]:
        """Return list of constraint conflicts. Empty list means no conflicts."""
        issues: list[str] = []

        if self.min_soc_pct >= self.max_soc_pct:
            issues.append("min_soc_pct >= max_soc_pct: infeasible SOC range")

        if self.auxiliary_power_mw >= self.max_discharge_mw:
            issues.append("auxiliary_power >= max_discharge: no usable capacity")

        if self.max_charge_mw <= 0:
            issues.append("max_charge_mw <= 0: no charging capacity")

        if self.max_discharge_mw <= 0:
            issues.append("max_discharge_mw <= 0: no discharging capacity")

        if not (0.0 < self.round_trip_efficiency <= 1.0):
            issues.append(
                "round_trip_efficiency must be in (0, 1]: invalid efficiency"
            )

        if self.min_duration_intervals < 1:
            issues.append("min_duration_intervals < 1: invalid minimum duration")

        if self.dispatch_alignment_minutes < 1:
            issues.append(
                "dispatch_alignment_minutes < 1: invalid dispatch alignment"
            )

        if (
            self.registered_capacity_mw is not None
            and self.registered_capacity_mw <= 0
        ):
            issues.append("registered_capacity_mw <= 0: invalid registered capacity")

        if self.auxiliary_power_mw < 0:
            issues.append("auxiliary_power_mw < 0: invalid auxiliary power")

        return issues


# ---------------------------------------------------------------------------
# Result Models
# ---------------------------------------------------------------------------


class BindingConstraintRecord(BaseModel):
    """Record of a binding constraint in the backtest result."""

    constraint_name: str  # e.g. "soc_min", "soc_max", "charge_power_limit", etc.
    intervals_active: int
    first_active_timestamp: str | None = None
    last_active_timestamp: str | None = None


class BacktestV2Result(BaseModel):
    """Backtest Engine V2 result with constraint annotations."""

    status: str  # "optimal" | "infeasible"
    timeline: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    binding_constraints: list[BindingConstraintRecord] = []
    constraint_conflicts: list[str] = []


# ---------------------------------------------------------------------------
# Backtest V2 Parameters (input interface)
# ---------------------------------------------------------------------------


@dataclass
class BacktestV2Params:
    """Parameters for the V2 backtest engine."""

    energy_mwh: float
    initial_soc_mwh: float
    constraints: BacktestConstraints
    max_cycles_per_day: float = 2.0
    network_fee_per_mwh: float = 0.0
    degradation_cost_per_mwh: float = 0.0
    variable_om_per_mwh: float = 0.0


# ---------------------------------------------------------------------------
# Engine Implementation
# ---------------------------------------------------------------------------

_BINDING_TOLERANCE = 1e-4


def run_bess_backtest_v2(
    params: BacktestV2Params, intervals: list[dict]
) -> BacktestV2Result:
    """
    Run BESS backtest with enhanced constraint modeling.

    Args:
        params: Backtest parameters including constraints.
        intervals: List of dicts with keys: timestamp, price, interval_hours (optional).

    Returns:
        BacktestV2Result with status, timeline, summary, and binding constraints.
    """
    constraints = params.constraints

    # --- Pre-validation ---
    validation_issues = constraints.validate()
    if validation_issues:
        return BacktestV2Result(
            status="infeasible",
            constraint_conflicts=validation_issues,
        )

    if not intervals:
        return BacktestV2Result(
            status="optimal",
            timeline=[],
            summary={
                "soc_start_mwh": params.initial_soc_mwh,
                "soc_end_mwh": params.initial_soc_mwh,
                "gross_revenue": 0.0,
                "net_revenue": 0.0,
                "charge_throughput_mwh": 0.0,
                "discharge_throughput_mwh": 0.0,
                "equivalent_cycles": 0.0,
                "warnings": ["no_intervals"],
            },
            binding_constraints=[],
        )

    # --- Derived parameters ---
    eta = sqrt(constraints.round_trip_efficiency)
    min_soc_mwh = params.energy_mwh * (constraints.min_soc_pct / 100.0)
    max_soc_mwh = params.energy_mwh * (constraints.max_soc_pct / 100.0)
    initial_soc_mwh = params.initial_soc_mwh

    interval_hours = [
        float(row.get("interval_hours", 5.0 / 60.0)) for row in intervals
    ]
    prices = [float(row.get("price", 0.0)) for row in intervals]
    n = len(intervals)

    day_count = sum(interval_hours) / 24.0
    throughput_limit_mwh = params.max_cycles_per_day * day_count * params.energy_mwh

    # --- Dispatch alignment grouping ---
    # Determine how many intervals form one dispatch block
    interval_minutes = interval_hours[0] * 60.0 if interval_hours else 5.0
    intervals_per_block = max(
        1, int(round(constraints.dispatch_alignment_minutes / interval_minutes))
    )

    # --- MILP Model ---
    problem = pulp.LpProblem("BESS_Backtest_V2", pulp.LpMaximize)

    # Decision variables
    charge = [
        pulp.LpVariable(
            f"charge_{i}", lowBound=0, upBound=constraints.max_charge_mw
        )
        for i in range(n)
    ]
    discharge = [
        pulp.LpVariable(
            f"discharge_{i}", lowBound=0, upBound=constraints.max_discharge_mw
        )
        for i in range(n)
    ]
    soc = [
        pulp.LpVariable(f"soc_{i}", lowBound=min_soc_mwh, upBound=max_soc_mwh)
        for i in range(n)
    ]
    # Binary: 1 = charging mode, 0 = discharging/idle mode
    is_charging = [
        pulp.LpVariable(f"is_charging_{i}", cat=pulp.LpBinary) for i in range(n)
    ]

    # --- Constraints ---

    # 1. Mutual exclusion: cannot charge and discharge simultaneously
    for i in range(n):
        problem += charge[i] <= constraints.max_charge_mw * is_charging[i]
        problem += discharge[i] <= constraints.max_discharge_mw * (1 - is_charging[i])

    # 2. SOC dynamics with auxiliary power consumption
    for i in range(n):
        dt = interval_hours[i]
        aux_consumption = constraints.auxiliary_power_mw * dt

        if i == 0:
            problem += soc[i] == (
                initial_soc_mwh
                + charge[i] * dt * eta
                - discharge[i] * dt / eta
                - aux_consumption
            )
        else:
            problem += soc[i] == (
                soc[i - 1]
                + charge[i] * dt * eta
                - discharge[i] * dt / eta
                - aux_consumption
            )

    # 3. Registered capacity limit
    if constraints.registered_capacity_mw is not None:
        for i in range(n):
            problem += (
                charge[i] + discharge[i] <= constraints.registered_capacity_mw
            )

    # 4. Dispatch alignment: within each block, charge/discharge decisions are uniform
    if intervals_per_block > 1:
        num_blocks = (n + intervals_per_block - 1) // intervals_per_block
        for block_idx in range(num_blocks):
            block_start = block_idx * intervals_per_block
            block_end = min(block_start + intervals_per_block, n)
            # All intervals in a block share the same charging state
            for i in range(block_start + 1, block_end):
                problem += is_charging[i] == is_charging[block_start]

    # 5. Minimum duration constraints
    # If state changes at interval i, the new state must persist for
    # at least min_duration_intervals consecutive intervals.
    if constraints.min_duration_intervals > 1:
        min_dur = constraints.min_duration_intervals
        for i in range(1, n):
            # If switching from discharge to charge (is_charging goes 0->1)
            # then is_charging must stay 1 for min_dur intervals
            for j in range(i + 1, min(i + min_dur, n)):
                # If is_charging[i] - is_charging[i-1] == 1 (switch to charge),
                # then is_charging[j] >= 1
                # Linearized: is_charging[j] >= is_charging[i] - is_charging[i-1]
                problem += is_charging[j] >= is_charging[i] - is_charging[i - 1]

            # If switching from charge to discharge (is_charging goes 1->0)
            # then is_charging must stay 0 for min_dur intervals
            for j in range(i + 1, min(i + min_dur, n)):
                # If is_charging[i-1] - is_charging[i] == 1 (switch to discharge),
                # then (1 - is_charging[j]) >= 1
                # Linearized: is_charging[j] <= 1 - (is_charging[i-1] - is_charging[i])
                problem += is_charging[j] <= 1 - (is_charging[i - 1] - is_charging[i])

    # 6. Throughput limit (cycle life constraint)
    total_discharge_energy = pulp.lpSum(
        discharge[i] * interval_hours[i] for i in range(n)
    )
    problem += total_discharge_energy <= throughput_limit_mwh

    # 7. Terminal SOC constraint (return to initial)
    problem += soc[n - 1] == initial_soc_mwh

    # --- Objective: maximize net revenue ---
    gross_revenue = pulp.lpSum(
        (discharge[i] - charge[i]) * interval_hours[i] * prices[i] for i in range(n)
    )
    discharge_energy = pulp.lpSum(discharge[i] * interval_hours[i] for i in range(n))
    network_fees = discharge_energy * params.network_fee_per_mwh
    degradation_cost = discharge_energy * params.degradation_cost_per_mwh
    variable_om_cost = discharge_energy * params.variable_om_per_mwh
    net_revenue = gross_revenue - network_fees - degradation_cost - variable_om_cost

    problem += net_revenue

    # --- Solve ---
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60)
    problem.solve(solver)

    solve_status = pulp.LpStatus[problem.status]

    # --- Handle infeasible ---
    if solve_status != "Optimal":
        conflict_info = _detect_constraint_conflicts(params, constraints, intervals)
        return BacktestV2Result(
            status="infeasible",
            constraint_conflicts=conflict_info
            or [f"Solver status: {solve_status}"],
        )

    # --- Extract results ---
    timeline = []
    realized_charge = 0.0
    realized_discharge = 0.0

    for i, row in enumerate(intervals):
        dt = interval_hours[i]
        charge_mw = float(pulp.value(charge[i]) or 0.0)
        discharge_mw = float(pulp.value(discharge[i]) or 0.0)
        soc_mwh = float(pulp.value(soc[i]) or 0.0)
        charge_mwh = charge_mw * dt
        discharge_mwh = discharge_mw * dt
        interval_gross = (discharge_mwh - charge_mwh) * prices[i]
        interval_net_fees = discharge_mwh * params.network_fee_per_mwh
        interval_degradation = discharge_mwh * params.degradation_cost_per_mwh
        interval_vom = discharge_mwh * params.variable_om_per_mwh

        realized_charge += charge_mwh
        realized_discharge += discharge_mwh

        timeline.append(
            {
                "timestamp": row.get("timestamp"),
                "price": prices[i],
                "interval_hours": dt,
                "charge_mw": charge_mw,
                "discharge_mw": discharge_mw,
                "charge_mwh": charge_mwh,
                "discharge_mwh": discharge_mwh,
                "soc_mwh": soc_mwh,
                "gross_revenue": interval_gross,
                "net_revenue": (
                    interval_gross - interval_net_fees - interval_degradation - interval_vom
                ),
            }
        )

    # --- Detect binding constraints ---
    binding = _detect_binding_constraints(
        timeline, constraints, params.energy_mwh, intervals
    )

    # --- Summary ---
    equivalent_cycles = (
        realized_discharge / params.energy_mwh if params.energy_mwh > 0 else 0.0
    )

    summary = {
        "soc_start_mwh": initial_soc_mwh,
        "soc_end_mwh": float(pulp.value(soc[n - 1]) or initial_soc_mwh),
        "soc_min_mwh": min(item["soc_mwh"] for item in timeline),
        "soc_max_mwh": max(item["soc_mwh"] for item in timeline),
        "charge_throughput_mwh": realized_charge,
        "discharge_throughput_mwh": realized_discharge,
        "equivalent_cycles": equivalent_cycles,
        "gross_revenue": float(pulp.value(gross_revenue) or 0.0),
        "net_revenue": float(pulp.value(net_revenue) or 0.0),
        "costs": {
            "network_fees": float(pulp.value(network_fees) or 0.0),
            "degradation": float(pulp.value(degradation_cost) or 0.0),
            "variable_om": float(pulp.value(variable_om_cost) or 0.0),
        },
        "warnings": [],
    }

    return BacktestV2Result(
        status="optimal",
        timeline=timeline,
        summary=summary,
        binding_constraints=binding,
    )


# ---------------------------------------------------------------------------
# Binding Constraint Detection
# ---------------------------------------------------------------------------


def _detect_binding_constraints(
    timeline: list[dict],
    constraints: BacktestConstraints,
    energy_mwh: float,
    intervals: list[dict],
) -> list[BindingConstraintRecord]:
    """Analyze solved timeline to identify binding constraints."""
    binding: list[BindingConstraintRecord] = []

    min_soc_mwh = energy_mwh * (constraints.min_soc_pct / 100.0)
    max_soc_mwh = energy_mwh * (constraints.max_soc_pct / 100.0)

    # SOC min binding
    soc_min_active = [
        i
        for i, item in enumerate(timeline)
        if abs(item["soc_mwh"] - min_soc_mwh) < _BINDING_TOLERANCE
    ]
    if soc_min_active:
        binding.append(
            BindingConstraintRecord(
                constraint_name="soc_min",
                intervals_active=len(soc_min_active),
                first_active_timestamp=timeline[soc_min_active[0]].get("timestamp"),
                last_active_timestamp=timeline[soc_min_active[-1]].get("timestamp"),
            )
        )

    # SOC max binding
    soc_max_active = [
        i
        for i, item in enumerate(timeline)
        if abs(item["soc_mwh"] - max_soc_mwh) < _BINDING_TOLERANCE
    ]
    if soc_max_active:
        binding.append(
            BindingConstraintRecord(
                constraint_name="soc_max",
                intervals_active=len(soc_max_active),
                first_active_timestamp=timeline[soc_max_active[0]].get("timestamp"),
                last_active_timestamp=timeline[soc_max_active[-1]].get("timestamp"),
            )
        )

    # Charge power limit binding
    charge_limit_active = [
        i
        for i, item in enumerate(timeline)
        if abs(item["charge_mw"] - constraints.max_charge_mw) < _BINDING_TOLERANCE
        and item["charge_mw"] > _BINDING_TOLERANCE
    ]
    if charge_limit_active:
        binding.append(
            BindingConstraintRecord(
                constraint_name="charge_power_limit",
                intervals_active=len(charge_limit_active),
                first_active_timestamp=timeline[charge_limit_active[0]].get(
                    "timestamp"
                ),
                last_active_timestamp=timeline[charge_limit_active[-1]].get(
                    "timestamp"
                ),
            )
        )

    # Discharge power limit binding
    discharge_limit_active = [
        i
        for i, item in enumerate(timeline)
        if abs(item["discharge_mw"] - constraints.max_discharge_mw) < _BINDING_TOLERANCE
        and item["discharge_mw"] > _BINDING_TOLERANCE
    ]
    if discharge_limit_active:
        binding.append(
            BindingConstraintRecord(
                constraint_name="discharge_power_limit",
                intervals_active=len(discharge_limit_active),
                first_active_timestamp=timeline[discharge_limit_active[0]].get(
                    "timestamp"
                ),
                last_active_timestamp=timeline[discharge_limit_active[-1]].get(
                    "timestamp"
                ),
            )
        )

    # Registered capacity limit binding
    if constraints.registered_capacity_mw is not None:
        reg_cap_active = [
            i
            for i, item in enumerate(timeline)
            if abs(
                item["charge_mw"] + item["discharge_mw"]
                - constraints.registered_capacity_mw
            )
            < _BINDING_TOLERANCE
            and (item["charge_mw"] + item["discharge_mw"]) > _BINDING_TOLERANCE
        ]
        if reg_cap_active:
            binding.append(
                BindingConstraintRecord(
                    constraint_name="registered_capacity_limit",
                    intervals_active=len(reg_cap_active),
                    first_active_timestamp=timeline[reg_cap_active[0]].get(
                        "timestamp"
                    ),
                    last_active_timestamp=timeline[reg_cap_active[-1]].get(
                        "timestamp"
                    ),
                )
            )

    return binding


# ---------------------------------------------------------------------------
# Constraint Conflict Detection (for infeasible cases)
# ---------------------------------------------------------------------------


def _detect_constraint_conflicts(
    params: BacktestV2Params,
    constraints: BacktestConstraints,
    intervals: list[dict],
) -> list[str]:
    """
    Heuristic analysis of why the model might be infeasible.
    Returns a list of likely constraint conflicts.
    """
    conflicts: list[str] = []

    min_soc_mwh = params.energy_mwh * (constraints.min_soc_pct / 100.0)
    max_soc_mwh = params.energy_mwh * (constraints.max_soc_pct / 100.0)
    usable_range = max_soc_mwh - min_soc_mwh

    if usable_range <= 0:
        conflicts.append(
            f"SOC range is zero or negative: min={min_soc_mwh:.2f} MWh, "
            f"max={max_soc_mwh:.2f} MWh"
        )

    # Check if auxiliary power drains SOC below minimum over the horizon
    total_hours = sum(float(r.get("interval_hours", 5.0 / 60.0)) for r in intervals)
    total_aux_drain = constraints.auxiliary_power_mw * total_hours
    if total_aux_drain > usable_range and constraints.max_charge_mw <= 0:
        conflicts.append(
            f"Auxiliary power drain ({total_aux_drain:.2f} MWh) exceeds usable "
            f"SOC range ({usable_range:.2f} MWh) with no charging capacity"
        )

    # Check if terminal SOC constraint is achievable
    initial_soc = params.initial_soc_mwh
    if initial_soc < min_soc_mwh:
        conflicts.append(
            f"Initial SOC ({initial_soc:.2f} MWh) below minimum "
            f"({min_soc_mwh:.2f} MWh)"
        )
    if initial_soc > max_soc_mwh:
        conflicts.append(
            f"Initial SOC ({initial_soc:.2f} MWh) above maximum "
            f"({max_soc_mwh:.2f} MWh)"
        )

    # Check registered capacity vs required power
    if constraints.registered_capacity_mw is not None:
        if constraints.registered_capacity_mw < constraints.auxiliary_power_mw:
            conflicts.append(
                "Registered capacity less than auxiliary power requirement"
            )

    # Check if min_duration is too long relative to horizon
    if constraints.min_duration_intervals > len(intervals):
        conflicts.append(
            f"min_duration_intervals ({constraints.min_duration_intervals}) "
            f"exceeds total intervals ({len(intervals)})"
        )

    if not conflicts:
        conflicts.append(
            "Constraint combination is infeasible — "
            "try relaxing SOC bounds, power limits, or minimum duration"
        )

    return conflicts
