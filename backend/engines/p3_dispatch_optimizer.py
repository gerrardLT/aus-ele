from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import pulp


@dataclass
class DispatchScenarioConfig:
    name: str
    spread_multiplier: float
    fcas_multiplier: float


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * pct))))
    return float(ordered[idx])


def _scenario_configs(spike_probability: float, negative_probability: float, risk_mode: str) -> list[DispatchScenarioConfig]:
    risk_bias = {
        "conservative": -0.06,
        "balanced": 0.0,
        "aggressive": 0.06,
    }.get(risk_mode, 0.0)
    regime_bias = ((spike_probability + negative_probability) * 0.18) + risk_bias
    base_spread = max(0.7, 1.0 + regime_bias)
    return [
        DispatchScenarioConfig(name="bear", spread_multiplier=max(0.55, base_spread - 0.22), fcas_multiplier=max(0.65, 0.9 + risk_bias)),
        DispatchScenarioConfig(name="base", spread_multiplier=base_spread, fcas_multiplier=1.0 + risk_bias),
        DispatchScenarioConfig(name="bull", spread_multiplier=base_spread + 0.22, fcas_multiplier=1.12 + risk_bias),
    ]


def _build_interval_rows(
    *,
    timeline: list[dict],
    fcas_score: float,
    charge_window_score: float,
    discharge_window_score: float,
    spike_probability: float,
    negative_probability: float,
    primary_regime: str,
    scenario: DispatchScenarioConfig,
) -> list[dict]:
    prices = [float(item.get("price", 0.0) or 0.0) for item in timeline]
    if not prices:
        return []

    price_mid = float(median(prices))
    lower_band = _percentile(prices, 0.25)
    upper_band = _percentile(prices, 0.75)
    fcas_intensity = max(0.0, min(1.5, fcas_score / 100.0))
    charge_bias = charge_window_score / 100.0
    discharge_bias = discharge_window_score / 100.0
    scarcity_bonus = 0.35 if primary_regime in {"scarcity", "price_spike", "reserve_stress"} else 0.0
    oversupply_bonus = 0.35 if primary_regime in {"oversupply", "negative_price"} else 0.0

    rows = []
    for item in timeline:
        raw_price = float(item.get("price", 0.0) or 0.0)
        dt = float(item.get("interval_hours", 5.0 / 60.0) or (5.0 / 60.0))
        spread = raw_price - price_mid

        if spread >= 0:
            adjusted_price = price_mid + (spread * scenario.spread_multiplier * (1.0 + discharge_bias * 0.15 + spike_probability * 0.12))
        else:
            adjusted_price = price_mid + (spread * scenario.spread_multiplier * (1.0 + charge_bias * 0.15 + negative_probability * 0.12))

        raise_signal = max(raw_price - price_mid, 0.0)
        lower_signal = max(price_mid - raw_price, 0.0)
        if raw_price >= upper_band:
            raise_signal += max(raw_price, 0.0) * 0.15
        if raw_price <= lower_band:
            lower_signal += max(abs(raw_price), abs(price_mid), 0.0) * 0.15
        if raw_price < 0:
            lower_signal += abs(raw_price) * (0.25 + negative_probability * 0.4)

        base_raise = (10.0 + raise_signal) * fcas_intensity * (0.55 + discharge_bias * 0.45 + spike_probability * 0.35 + scarcity_bonus)
        base_lower = (10.0 + lower_signal) * fcas_intensity * (0.55 + charge_bias * 0.45 + negative_probability * 0.35 + oversupply_bonus)

        rows.append(
            {
                "timestamp": item.get("timestamp"),
                "interval_hours": dt,
                "energy_price": round(adjusted_price, 6),
                "raise_price": round(base_raise * scenario.fcas_multiplier, 6),
                "lower_price": round(base_lower * scenario.fcas_multiplier, 6),
            }
        )
    return rows


def _solve_dispatch_scenario(
    *,
    rows: list[dict],
    power_mw: float,
    energy_mwh: float,
    round_trip_efficiency: float,
    reserve_soc_mwh: float,
    initial_soc_mwh: float,
    min_soc_pct: float,
    max_soc_pct: float,
    degradation_cost_per_mwh: float,
    variable_om_per_mwh: float,
    network_fee_per_mwh: float,
    risk_mode: str,
) -> dict:
    if not rows:
        return {
            "status": "no_rows",
            "net_revenue": 0.0,
            "gross_energy_revenue": 0.0,
            "reserve_value_revenue": 0.0,
            "degradation_cost": 0.0,
            "variable_om_cost": 0.0,
            "network_fee_cost": 0.0,
            "dispatch_summary": {
                "total_charge_mwh": 0.0,
                "total_discharge_mwh": 0.0,
                "total_raise_reserve_mwh": 0.0,
                "total_lower_reserve_mwh": 0.0,
                "average_soc_mwh": initial_soc_mwh,
                "reserve_soc_mwh": reserve_soc_mwh,
                "dispatch_intervals": 0,
            },
        }

    if not hasattr(pulp, "LpProblem"):
        return _heuristic_dispatch_scenario(
            rows=rows,
            power_mw=power_mw,
            energy_mwh=energy_mwh,
            round_trip_efficiency=round_trip_efficiency,
            reserve_soc_mwh=reserve_soc_mwh,
            initial_soc_mwh=initial_soc_mwh,
            min_soc_pct=min_soc_pct,
            max_soc_pct=max_soc_pct,
            degradation_cost_per_mwh=degradation_cost_per_mwh,
            variable_om_per_mwh=variable_om_per_mwh,
            network_fee_per_mwh=network_fee_per_mwh,
            risk_mode=risk_mode,
        )

    eta = round_trip_efficiency ** 0.5
    min_soc_mwh = energy_mwh * (min_soc_pct / 100.0)
    max_soc_mwh = energy_mwh * (max_soc_pct / 100.0)
    reserve_penalty_multiplier = {
        "conservative": 0.35,
        "balanced": 0.22,
        "aggressive": 0.12,
    }.get(risk_mode, 0.22)
    reserve_penalty_rate = (degradation_cost_per_mwh + variable_om_per_mwh) * reserve_penalty_multiplier

    problem = pulp.LpProblem("P3_Dispatch_Optimizer", pulp.LpMaximize)
    n = len(rows)
    charge = [pulp.LpVariable(f"charge_{idx}", lowBound=0, upBound=power_mw) for idx in range(n)]
    discharge = [pulp.LpVariable(f"discharge_{idx}", lowBound=0, upBound=power_mw) for idx in range(n)]
    raise_reserve = [pulp.LpVariable(f"raise_{idx}", lowBound=0, upBound=power_mw) for idx in range(n)]
    lower_reserve = [pulp.LpVariable(f"lower_{idx}", lowBound=0, upBound=power_mw) for idx in range(n)]
    soc = [pulp.LpVariable(f"soc_{idx}", lowBound=min_soc_mwh, upBound=max_soc_mwh) for idx in range(n)]
    is_charging = [pulp.LpVariable(f"is_charging_{idx}", cat=pulp.LpBinary) for idx in range(n)]
    is_discharging = [pulp.LpVariable(f"is_discharging_{idx}", cat=pulp.LpBinary) for idx in range(n)]

    for idx, row in enumerate(rows):
        dt = row["interval_hours"]
        problem += is_charging[idx] + is_discharging[idx] <= 1
        problem += charge[idx] <= power_mw * is_charging[idx]
        problem += discharge[idx] <= power_mw * is_discharging[idx]
        problem += charge[idx] + lower_reserve[idx] <= power_mw
        problem += discharge[idx] + raise_reserve[idx] <= power_mw
        problem += raise_reserve[idx] + lower_reserve[idx] <= power_mw

        if idx == 0:
            problem += soc[idx] == initial_soc_mwh + charge[idx] * dt * eta - discharge[idx] * dt / eta
        else:
            problem += soc[idx] == soc[idx - 1] + charge[idx] * dt * eta - discharge[idx] * dt / eta

        problem += soc[idx] >= min_soc_mwh + reserve_soc_mwh
        problem += soc[idx] - min_soc_mwh >= (raise_reserve[idx] * dt / eta) + reserve_soc_mwh
        problem += max_soc_mwh - soc[idx] >= lower_reserve[idx] * dt * eta

    problem += soc[-1] >= initial_soc_mwh

    gross_energy_revenue = pulp.lpSum(
        (discharge[idx] - charge[idx]) * rows[idx]["interval_hours"] * rows[idx]["energy_price"]
        for idx in range(n)
    )
    reserve_value_revenue = pulp.lpSum(
        (
            raise_reserve[idx] * rows[idx]["raise_price"]
            + lower_reserve[idx] * rows[idx]["lower_price"]
        ) * rows[idx]["interval_hours"]
        for idx in range(n)
    )
    throughput_cost_basis = pulp.lpSum(
        (charge[idx] + discharge[idx]) * rows[idx]["interval_hours"]
        for idx in range(n)
    )
    discharge_mwh = pulp.lpSum(discharge[idx] * rows[idx]["interval_hours"] for idx in range(n))
    network_fee_cost = discharge_mwh * network_fee_per_mwh
    variable_om_cost = throughput_cost_basis * variable_om_per_mwh
    degradation_cost = throughput_cost_basis * degradation_cost_per_mwh
    reserve_penalty_cost = pulp.lpSum(
        (raise_reserve[idx] + lower_reserve[idx]) * rows[idx]["interval_hours"] * reserve_penalty_rate
        for idx in range(n)
    )
    net_revenue = gross_energy_revenue + reserve_value_revenue - network_fee_cost - variable_om_cost - degradation_cost - reserve_penalty_cost
    problem += net_revenue

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=30)
    problem.solve(solver)
    status = pulp.LpStatus[problem.status]
    if status != "Optimal":
        raise RuntimeError(f"P3 dispatch solve failed: {status}")

    total_charge_mwh = 0.0
    total_discharge_mwh = 0.0
    total_raise_reserve_mwh = 0.0
    total_lower_reserve_mwh = 0.0
    average_soc_acc = 0.0
    for idx, row in enumerate(rows):
        dt = row["interval_hours"]
        total_charge_mwh += float(pulp.value(charge[idx]) or 0.0) * dt
        total_discharge_mwh += float(pulp.value(discharge[idx]) or 0.0) * dt
        total_raise_reserve_mwh += float(pulp.value(raise_reserve[idx]) or 0.0) * dt
        total_lower_reserve_mwh += float(pulp.value(lower_reserve[idx]) or 0.0) * dt
        average_soc_acc += float(pulp.value(soc[idx]) or 0.0)

    return {
        "status": "optimal",
        "net_revenue": round(float(pulp.value(net_revenue) or 0.0), 4),
        "gross_energy_revenue": round(float(pulp.value(gross_energy_revenue) or 0.0), 4),
        "reserve_value_revenue": round(float(pulp.value(reserve_value_revenue) or 0.0), 4),
        "degradation_cost": round(float(pulp.value(degradation_cost) or 0.0), 4),
        "variable_om_cost": round(float(pulp.value(variable_om_cost) or 0.0), 4),
        "network_fee_cost": round(float(pulp.value(network_fee_cost) or 0.0), 4),
        "reserve_penalty_cost": round(float(pulp.value(reserve_penalty_cost) or 0.0), 4),
        "dispatch_summary": {
            "total_charge_mwh": round(total_charge_mwh, 4),
            "total_discharge_mwh": round(total_discharge_mwh, 4),
            "total_raise_reserve_mwh": round(total_raise_reserve_mwh, 4),
            "total_lower_reserve_mwh": round(total_lower_reserve_mwh, 4),
            "average_soc_mwh": round((average_soc_acc / n) if n else initial_soc_mwh, 4),
            "reserve_soc_mwh": round(reserve_soc_mwh, 4),
            "dispatch_intervals": n,
        },
    }


def _heuristic_dispatch_scenario(
    *,
    rows: list[dict],
    power_mw: float,
    energy_mwh: float,
    round_trip_efficiency: float,
    reserve_soc_mwh: float,
    initial_soc_mwh: float,
    min_soc_pct: float,
    max_soc_pct: float,
    degradation_cost_per_mwh: float,
    variable_om_per_mwh: float,
    network_fee_per_mwh: float,
    risk_mode: str,
) -> dict:
    eta = round_trip_efficiency ** 0.5
    min_soc_mwh = energy_mwh * (min_soc_pct / 100.0)
    max_soc_mwh = energy_mwh * (max_soc_pct / 100.0)
    prices = [row["energy_price"] for row in rows]
    low_band = _percentile(prices, 0.25)
    high_band = _percentile(prices, 0.75)
    reserve_penalty_multiplier = {
        "conservative": 0.35,
        "balanced": 0.22,
        "aggressive": 0.12,
    }.get(risk_mode, 0.22)
    reserve_penalty_rate = (degradation_cost_per_mwh + variable_om_per_mwh) * reserve_penalty_multiplier

    soc = initial_soc_mwh
    total_charge_mwh = 0.0
    total_discharge_mwh = 0.0
    total_raise_reserve_mwh = 0.0
    total_lower_reserve_mwh = 0.0
    average_soc_acc = 0.0
    gross_energy_revenue = 0.0
    reserve_value_revenue = 0.0

    for row in rows:
        dt = row["interval_hours"]
        price = row["energy_price"]
        charge_mw = 0.0
        discharge_mw = 0.0

        available_charge_mw = max(0.0, min(power_mw, (max_soc_mwh - soc) / max(dt * eta, 1e-9)))
        available_discharge_mw = max(0.0, min(power_mw, (soc - min_soc_mwh - reserve_soc_mwh) * eta / max(dt, 1e-9)))

        if price <= low_band:
            charge_mw = min(available_charge_mw, power_mw * 0.8)
        elif price >= high_band:
            discharge_mw = min(available_discharge_mw, power_mw * 0.8)

        soc = soc + charge_mw * dt * eta - discharge_mw * dt / eta
        soc = max(min_soc_mwh + reserve_soc_mwh, min(max_soc_mwh, soc))

        raise_reserve_mw = max(0.0, min(power_mw - discharge_mw, (soc - min_soc_mwh - reserve_soc_mwh) * eta / max(dt, 1e-9)))
        lower_reserve_mw = max(0.0, min(power_mw - charge_mw, (max_soc_mwh - soc) / max(dt * eta, 1e-9)))
        reserve_split = power_mw / max(raise_reserve_mw + lower_reserve_mw, power_mw) if (raise_reserve_mw + lower_reserve_mw) > power_mw else 1.0
        raise_reserve_mw *= reserve_split
        lower_reserve_mw *= reserve_split

        charge_mwh = charge_mw * dt
        discharge_mwh = discharge_mw * dt
        raise_reserve_mwh = raise_reserve_mw * dt
        lower_reserve_mwh = lower_reserve_mw * dt

        gross_energy_revenue += (discharge_mwh - charge_mwh) * price
        reserve_value_revenue += (raise_reserve_mwh * row["raise_price"]) + (lower_reserve_mwh * row["lower_price"])
        total_charge_mwh += charge_mwh
        total_discharge_mwh += discharge_mwh
        total_raise_reserve_mwh += raise_reserve_mwh
        total_lower_reserve_mwh += lower_reserve_mwh
        average_soc_acc += soc

    throughput_cost_basis = total_charge_mwh + total_discharge_mwh
    network_fee_cost = total_discharge_mwh * network_fee_per_mwh
    variable_om_cost = throughput_cost_basis * variable_om_per_mwh
    degradation_cost = throughput_cost_basis * degradation_cost_per_mwh
    reserve_penalty_cost = (total_raise_reserve_mwh + total_lower_reserve_mwh) * reserve_penalty_rate
    net_revenue = gross_energy_revenue + reserve_value_revenue - network_fee_cost - variable_om_cost - degradation_cost - reserve_penalty_cost

    return {
        "status": "heuristic_fallback",
        "net_revenue": round(net_revenue, 4),
        "gross_energy_revenue": round(gross_energy_revenue, 4),
        "reserve_value_revenue": round(reserve_value_revenue, 4),
        "degradation_cost": round(degradation_cost, 4),
        "variable_om_cost": round(variable_om_cost, 4),
        "network_fee_cost": round(network_fee_cost, 4),
        "reserve_penalty_cost": round(reserve_penalty_cost, 4),
        "dispatch_summary": {
            "total_charge_mwh": round(total_charge_mwh, 4),
            "total_discharge_mwh": round(total_discharge_mwh, 4),
            "total_raise_reserve_mwh": round(total_raise_reserve_mwh, 4),
            "total_lower_reserve_mwh": round(total_lower_reserve_mwh, 4),
            "average_soc_mwh": round((average_soc_acc / len(rows)) if rows else initial_soc_mwh, 4),
            "reserve_soc_mwh": round(reserve_soc_mwh, 4),
            "dispatch_intervals": len(rows),
        },
    }


def build_p3_strategy_bundle(
    *,
    timeline: list[dict],
    power_mw: float,
    energy_mwh: float,
    round_trip_efficiency: float,
    reserve_soc_pct: float,
    min_soc_pct: float,
    max_soc_pct: float,
    initial_soc_mwh: float,
    degradation_cost_per_mwh: float,
    variable_om_per_mwh: float,
    network_fee_per_mwh: float,
    risk_mode: str,
    fcas_score: float,
    charge_window_score: float,
    discharge_window_score: float,
    spike_probability: float,
    negative_probability: float,
    primary_regime: str,
) -> dict:
    reserve_soc_mwh = energy_mwh * (reserve_soc_pct / 100.0)
    scenarios = []
    for scenario in _scenario_configs(spike_probability, negative_probability, risk_mode):
        rows = _build_interval_rows(
            timeline=timeline,
            fcas_score=fcas_score,
            charge_window_score=charge_window_score,
            discharge_window_score=discharge_window_score,
            spike_probability=spike_probability,
            negative_probability=negative_probability,
            primary_regime=primary_regime,
            scenario=scenario,
        )
        result = _solve_dispatch_scenario(
            rows=rows,
            power_mw=power_mw,
            energy_mwh=energy_mwh,
            round_trip_efficiency=round_trip_efficiency,
            reserve_soc_mwh=reserve_soc_mwh,
            initial_soc_mwh=initial_soc_mwh,
            min_soc_pct=min_soc_pct,
            max_soc_pct=max_soc_pct,
            degradation_cost_per_mwh=degradation_cost_per_mwh,
            variable_om_per_mwh=variable_om_per_mwh,
            network_fee_per_mwh=network_fee_per_mwh,
            risk_mode=risk_mode,
        )
        result["name"] = scenario.name
        scenarios.append(result)

    scenario_map = {item["name"]: item for item in scenarios}
    base = scenario_map["base"]
    bear = scenario_map["bear"]
    bull = scenario_map["bull"]
    return {
        "reserve_soc_mwh": round(reserve_soc_mwh, 4),
        "forecast_driven_dispatch": base,
        "stochastic_dispatch": {
            "scenario_count": len(scenarios),
            "base_case_net_revenue": base["net_revenue"],
            "bear_case_net_revenue": bear["net_revenue"],
            "bull_case_net_revenue": bull["net_revenue"],
            "scenario_spread": round(bull["net_revenue"] - bear["net_revenue"], 4),
            "scenarios": scenarios,
        },
    }
