from __future__ import annotations

from math import sqrt

import pulp


def run_bess_backtest_v1(params, intervals: list[dict]) -> dict:
    if not intervals:
        return {
            "timeline": [],
            "summary": {
                "soc_start_mwh": params.initial_soc_mwh,
                "soc_end_mwh": params.initial_soc_mwh,
                "soc_min_mwh": params.initial_soc_mwh,
                "soc_max_mwh": params.initial_soc_mwh,
                "charge_throughput_mwh": 0.0,
                "discharge_throughput_mwh": 0.0,
                "equivalent_cycles": 0.0,
                "gross_revenue": 0.0,
                "net_revenue": 0.0,
                "costs": {
                    "network_fees": 0.0,
                    "degradation": 0.0,
                    "variable_om": 0.0,
                },
                "warnings": ["no_intervals"],
            },
        }

    eta = sqrt(params.round_trip_efficiency)
    min_soc_mwh = params.energy_mwh * (params.min_soc_pct / 100.0)
    max_soc_mwh = params.energy_mwh * (params.max_soc_pct / 100.0)
    initial_soc_mwh = params.initial_soc_mwh

    interval_hours = [float(row.get("interval_hours", 5.0 / 60.0)) for row in intervals]
    prices = [float(row.get("price", 0.0)) for row in intervals]
    day_count = sum(interval_hours) / 24.0
    throughput_limit_mwh = params.max_cycles_per_day * day_count * params.energy_mwh

    problem = pulp.LpProblem("BESS_Backtest_V1", pulp.LpMaximize)
    n = len(intervals)
    charge = [pulp.LpVariable(f"charge_{idx}", lowBound=0, upBound=params.power_mw) for idx in range(n)]
    discharge = [pulp.LpVariable(f"discharge_{idx}", lowBound=0, upBound=params.power_mw) for idx in range(n)]
    soc = [pulp.LpVariable(f"soc_{idx}", lowBound=min_soc_mwh, upBound=max_soc_mwh) for idx in range(n)]
    is_charging = [pulp.LpVariable(f"is_charging_{idx}", cat=pulp.LpBinary) for idx in range(n)]

    for idx in range(n):
        dt = interval_hours[idx]
        problem += charge[idx] <= params.power_mw * is_charging[idx]
        problem += discharge[idx] <= params.power_mw * (1 - is_charging[idx])

        if idx == 0:
            problem += soc[idx] == (
                initial_soc_mwh
                + charge[idx] * dt * eta
                - discharge[idx] * dt / eta
            )
        else:
            problem += soc[idx] == (
                soc[idx - 1]
                + charge[idx] * dt * eta
                - discharge[idx] * dt / eta
            )

    total_charge_throughput = pulp.lpSum(charge[idx] * interval_hours[idx] for idx in range(n))
    total_discharge_throughput = pulp.lpSum(discharge[idx] * interval_hours[idx] for idx in range(n))
    problem += total_charge_throughput <= throughput_limit_mwh
    problem += soc[-1] == initial_soc_mwh

    gross_revenue = pulp.lpSum(
        (discharge[idx] - charge[idx]) * interval_hours[idx] * prices[idx]
        for idx in range(n)
    )
    discharge_cost_mwh = pulp.lpSum(discharge[idx] * interval_hours[idx] for idx in range(n))
    network_fees = discharge_cost_mwh * params.network_fee_per_mwh
    degradation_cost = discharge_cost_mwh * params.degradation_cost_per_mwh
    variable_om_cost = discharge_cost_mwh * params.variable_om_per_mwh
    net_revenue = gross_revenue - network_fees - degradation_cost - variable_om_cost
    problem += net_revenue

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=30)
    problem.solve(solver)

    if pulp.LpStatus[problem.status] != "Optimal":
        raise RuntimeError(f"Backtest solve failed: {pulp.LpStatus[problem.status]}")

    timeline = []
    realized_charge = 0.0
    realized_discharge = 0.0
    for idx, row in enumerate(intervals):
        dt = interval_hours[idx]
        charge_mw = float(pulp.value(charge[idx]) or 0.0)
        discharge_mw = float(pulp.value(discharge[idx]) or 0.0)
        soc_mwh = float(pulp.value(soc[idx]) or 0.0)
        charge_mwh = charge_mw * dt
        discharge_mwh = discharge_mw * dt
        interval_gross_revenue = (discharge_mwh - charge_mwh) * prices[idx]
        interval_network_fees = discharge_mwh * params.network_fee_per_mwh
        interval_degradation = discharge_mwh * params.degradation_cost_per_mwh
        interval_variable_om = discharge_mwh * params.variable_om_per_mwh
        realized_charge += charge_mwh
        realized_discharge += discharge_mwh

        timeline.append(
            {
                "timestamp": row.get("timestamp"),
                "price": prices[idx],
                "interval_hours": dt,
                "charge_mw": charge_mw,
                "discharge_mw": discharge_mw,
                "charge_mwh": charge_mwh,
                "discharge_mwh": discharge_mwh,
                "soc_mwh": soc_mwh,
                "gross_revenue": interval_gross_revenue,
                "net_revenue": interval_gross_revenue - interval_network_fees - interval_degradation - interval_variable_om,
            }
        )

    warnings = []
    if params.availability_pct < 100.0:
        warnings.append("availability_pct_not_applied_yet")

    equivalent_cycles = realized_discharge / params.energy_mwh if params.energy_mwh else 0.0
    return {
        "timeline": timeline,
        "summary": {
            "soc_start_mwh": initial_soc_mwh,
            "soc_end_mwh": float(pulp.value(soc[-1]) or initial_soc_mwh),
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
            "warnings": warnings,
        },
    }
