from __future__ import annotations

from datetime import datetime
from statistics import median


NEM_FCAS_SERVICE_GROUPS = {
    "raise1sec": "raise",
    "raise6sec": "raise",
    "raise60sec": "raise",
    "raise5min": "raise",
    "raisereg": "raise",
    "lower1sec": "lower",
    "lower6sec": "lower",
    "lower60sec": "lower",
    "lower5min": "lower",
    "lowerreg": "lower",
}


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _infer_interval_hours(rows: list[dict], default_minutes: int = 5) -> list[float]:
    if not rows:
        return []

    default_hours = default_minutes / 60.0
    timestamps = [_parse_timestamp(row["settlement_date"]) for row in rows]
    intervals = []
    for idx, current in enumerate(timestamps):
        if idx + 1 < len(timestamps):
            delta = (timestamps[idx + 1] - current).total_seconds() / 3600.0
            intervals.append(delta if delta > 0 else default_hours)
        else:
            intervals.append(intervals[-1] if intervals else default_hours)
    return intervals


def summarize_nem_fcas_opportunity(
    rows: list[dict],
    *,
    capacity_mw: float,
    duration_hours: float = 4.0,
    starting_soc_fraction: float = 0.5,
) -> dict:
    if not rows:
        return {
            "service_breakdown": [],
            "summary": {
                "total_gross_revenue_k": 0.0,
                "total_opportunity_cost_k": 0.0,
                "total_net_incremental_revenue_k": 0.0,
                "viable_service_count": 0,
                "assumed_duration_hours": duration_hours,
            },
        }

    interval_hours = _infer_interval_hours(rows)
    energy_prices = [float(row.get("rrp_aud_mwh") or 0.0) for row in rows]
    sorted_prices = sorted(energy_prices)
    low_idx = max(0, int((len(sorted_prices) - 1) * 0.25))
    high_idx = max(0, int((len(sorted_prices) - 1) * 0.75))
    low_threshold = sorted_prices[low_idx]
    high_threshold = sorted_prices[high_idx]
    median_price = median(energy_prices)

    energy_capacity_mwh = max(capacity_mw * duration_hours, 0.0)
    min_soc_mwh = 0.1 * energy_capacity_mwh
    max_soc_mwh = 0.9 * energy_capacity_mwh
    soc_mwh = min(max(energy_capacity_mwh * starting_soc_fraction, min_soc_mwh), max_soc_mwh)

    per_service: dict[str, dict] = {
        key: {
            "service": key,
            "key": key,
            "group": group,
            "prices": [],
            "gross_revenue": 0.0,
            "opportunity_cost": 0.0,
            "net_incremental_revenue": 0.0,
            "reserved_capacity_mw_samples": [],
            "soc_binding_intervals": 0,
            "power_binding_intervals": 0,
            "intervals_with_price": 0,
        }
        for key, group in NEM_FCAS_SERVICE_GROUPS.items()
    }

    for idx, row in enumerate(rows):
        energy_price = float(row.get("rrp_aud_mwh") or 0.0)
        hours = interval_hours[idx]

        raise_soc_headroom_mw = min(capacity_mw, max((soc_mwh - min_soc_mwh) / hours, 0.0)) if hours > 0 else 0.0
        lower_soc_headroom_mw = min(capacity_mw, max((max_soc_mwh - soc_mwh) / hours, 0.0)) if hours > 0 else 0.0

        for service_key, group in NEM_FCAS_SERVICE_GROUPS.items():
            price = float(row.get(f"{service_key}_rrp") or 0.0)
            if price <= 0:
                continue

            if group == "raise":
                reserved_capacity_mw = raise_soc_headroom_mw
                opportunity_price = max(energy_price - median_price, 0.0)
            else:
                reserved_capacity_mw = lower_soc_headroom_mw
                opportunity_price = max(median_price - energy_price, 0.0)

            gross_revenue = reserved_capacity_mw * price * hours
            opportunity_cost = reserved_capacity_mw * opportunity_price * hours
            net_incremental = gross_revenue - opportunity_cost

            bucket = per_service[service_key]
            bucket["prices"].append(price)
            bucket["gross_revenue"] += gross_revenue
            bucket["opportunity_cost"] += opportunity_cost
            bucket["net_incremental_revenue"] += net_incremental
            bucket["reserved_capacity_mw_samples"].append(reserved_capacity_mw)
            bucket["intervals_with_price"] += 1
            if reserved_capacity_mw + 1e-9 < capacity_mw:
                bucket["soc_binding_intervals"] += 1
            if reserved_capacity_mw >= capacity_mw - 1e-9:
                bucket["power_binding_intervals"] += 1

        # Update a notional energy state so binding flags vary through time.
        drift_mwh = capacity_mw * hours * 0.5
        if energy_price >= high_threshold:
            soc_mwh = max(min_soc_mwh, soc_mwh - drift_mwh)
        elif energy_price <= low_threshold:
            soc_mwh = min(max_soc_mwh, soc_mwh + drift_mwh)

    service_breakdown = []
    for service_key, bucket in per_service.items():
        intervals_with_price = bucket["intervals_with_price"]
        if intervals_with_price == 0:
            continue
        avg_reserved = sum(bucket["reserved_capacity_mw_samples"]) / len(bucket["reserved_capacity_mw_samples"])
        service_breakdown.append(
            {
                "service": service_key.replace("raise", "Raise ").replace("lower", "Lower ").replace("sec", " Sec").replace("min", " Min").replace("reg", " Reg").strip(),
                "key": service_key,
                "group": bucket["group"],
                "avg_price": round(sum(bucket["prices"]) / len(bucket["prices"]), 2),
                "max_price": round(max(bucket["prices"]), 2),
                "est_revenue_k": round(bucket["gross_revenue"] / 1000.0, 1),
                "avg_reserved_capacity_mw": round(avg_reserved, 2),
                "opportunity_cost_k": round(bucket["opportunity_cost"] / 1000.0, 3),
                "net_incremental_revenue_k": round(bucket["net_incremental_revenue"] / 1000.0, 3),
                "soc_binding_interval_ratio": round(bucket["soc_binding_intervals"] / intervals_with_price, 4),
                "power_binding_interval_ratio": round(bucket["power_binding_intervals"] / intervals_with_price, 4),
                "incremental_revenue_positive": bucket["net_incremental_revenue"] > 0,
            }
        )

    total_gross = sum(item["est_revenue_k"] for item in service_breakdown)
    total_opp = sum(item["opportunity_cost_k"] for item in service_breakdown)
    total_net = sum(item["net_incremental_revenue_k"] for item in service_breakdown)

    return {
        "service_breakdown": service_breakdown,
        "summary": {
            "total_gross_revenue_k": round(total_gross, 3),
            "total_opportunity_cost_k": round(total_opp, 3),
            "total_net_incremental_revenue_k": round(total_net, 3),
            "viable_service_count": sum(1 for item in service_breakdown if item["incremental_revenue_positive"]),
            "assumed_duration_hours": duration_hours,
            "median_energy_price": round(median_price, 2),
        },
    }
