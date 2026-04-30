from __future__ import annotations

import datetime as dt
from collections import defaultdict

from entsoe_client import EntsoeClient


FINLAND_BIDDING_ZONE = "10YFI-1--------U"
FINLAND_NEIGHBOR_BIDDING_ZONES = {
    "SE1": "10Y1001A1001A44P",
    "EE": "10Y1001A1001A39I",
}


def _format_period(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M")


def fetch_finland_day_ahead_summary(
    *,
    client: EntsoeClient | None = None,
    now_utc: dt.datetime | None = None,
) -> dict:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    period_start = now_utc.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + dt.timedelta(days=1)
    client = client or EntsoeClient()
    rows = client.fetch_day_ahead_prices(
        in_domain=FINLAND_BIDDING_ZONE,
        out_domain=FINLAND_BIDDING_ZONE,
        period_start=_format_period(period_start),
        period_end=_format_period(period_end),
    )
    if not rows:
        return {
            "dataset": {
                "dataset_id": "entsoe_day_ahead_fi",
                "dataset_code": "A44_A01_FI",
                "name": "Finland day-ahead prices",
                "unit": "EUR/MWh",
                "frequency": "1h",
                "status": "configured",
                "record_count": 0,
                "coverage_start_utc": None,
                "coverage_end_utc": None,
            },
            "summary": {
                "latest_price": None,
                "average_price": None,
            },
        }

    prices = [float(row["price"]) for row in rows]
    dataset = {
        "dataset_id": "entsoe_day_ahead_fi",
        "dataset_code": "A44_A01_FI",
        "name": "Finland day-ahead prices",
        "unit": "EUR/MWh",
        "frequency": "1h",
        "status": "live",
        "record_count": len(rows),
        "coverage_start_utc": rows[0]["timestamp_utc"],
        "coverage_end_utc": rows[-1]["timestamp_utc"],
    }
    summary = {
        "latest_price": prices[-1],
        "average_price": round(sum(prices) / len(prices), 2),
    }
    return {"dataset": dataset, "summary": summary, "series": rows}


def fetch_finland_total_load_summary(
    *,
    client: EntsoeClient | None = None,
    now_utc: dt.datetime | None = None,
) -> dict:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    period_start = now_utc.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + dt.timedelta(days=1)
    client = client or EntsoeClient()
    rows = client.fetch_total_load(
        out_bidding_zone_domain=FINLAND_BIDDING_ZONE,
        period_start=_format_period(period_start),
        period_end=_format_period(period_end),
    )
    if not rows:
        return {
            "dataset": {
                "dataset_id": "entsoe_total_load_fi",
                "dataset_code": "A65_A16_FI",
                "name": "Finland total load",
                "unit": "MW",
                "frequency": "1h",
                "status": "configured",
                "record_count": 0,
                "coverage_start_utc": None,
                "coverage_end_utc": None,
            },
            "summary": {
                "latest_load_mw": None,
                "average_load_mw": None,
            },
            "series": [],
        }

    loads = [float(row["load_mw"]) for row in rows]
    dataset = {
        "dataset_id": "entsoe_total_load_fi",
        "dataset_code": "A65_A16_FI",
        "name": "Finland total load",
        "unit": "MW",
        "frequency": "1h",
        "status": "live",
        "record_count": len(rows),
        "coverage_start_utc": rows[0]["timestamp_utc"],
        "coverage_end_utc": rows[-1]["timestamp_utc"],
    }
    summary = {
        "latest_load_mw": loads[-1],
        "average_load_mw": round(sum(loads) / len(loads), 2),
    }
    return {"dataset": dataset, "summary": summary, "series": rows}


def fetch_finland_generation_mix_summary(
    *,
    client: EntsoeClient | None = None,
    now_utc: dt.datetime | None = None,
) -> dict:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    period_start = now_utc.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + dt.timedelta(days=1)
    client = client or EntsoeClient()
    rows = client.fetch_aggregated_generation_per_type(
        in_domain=FINLAND_BIDDING_ZONE,
        period_start=_format_period(period_start),
        period_end=_format_period(period_end),
    )
    if not rows:
        return {
            "dataset": {
                "dataset_id": "entsoe_generation_mix_fi",
                "dataset_code": "A75_A16_FI",
                "name": "Finland generation mix",
                "unit": "MW",
                "frequency": "1h",
                "status": "configured",
                "record_count": 0,
                "coverage_start_utc": None,
                "coverage_end_utc": None,
            },
            "summary": {
                "latest_total_generation_mw": None,
                "production_type_count": 0,
                "top_production_type": None,
            },
            "series": [],
        }

    latest_timestamp = rows[-1]["timestamp_utc"]
    totals_by_type: dict[str, float] = defaultdict(float)
    latest_total = 0.0
    for row in rows:
        psr_type = row.get("psr_type") or "unknown"
        quantity_mw = float(row["quantity_mw"])
        totals_by_type[psr_type] += quantity_mw
        if row["timestamp_utc"] == latest_timestamp:
            latest_total += quantity_mw

    top_production_type = max(totals_by_type.items(), key=lambda item: item[1])[0] if totals_by_type else None
    return {
        "dataset": {
            "dataset_id": "entsoe_generation_mix_fi",
            "dataset_code": "A75_A16_FI",
            "name": "Finland generation mix",
            "unit": "MW",
            "frequency": "1h",
            "status": "live",
            "record_count": len(rows),
            "coverage_start_utc": rows[0]["timestamp_utc"],
            "coverage_end_utc": rows[-1]["timestamp_utc"],
        },
        "summary": {
            "latest_total_generation_mw": round(latest_total, 2),
            "production_type_count": len(totals_by_type),
            "top_production_type": top_production_type,
        },
        "series": rows,
    }


def fetch_finland_cross_border_flow_summary(
    *,
    client: EntsoeClient | None = None,
    now_utc: dt.datetime | None = None,
) -> dict:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    period_start = now_utc.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + dt.timedelta(days=1)
    client = client or EntsoeClient()

    rows = []
    for border_key, border_domain in FINLAND_NEIGHBOR_BIDDING_ZONES.items():
        border_rows = client.fetch_physical_flows(
            in_domain=FINLAND_BIDDING_ZONE,
            out_domain=border_domain,
            period_start=_format_period(period_start),
            period_end=_format_period(period_end),
        )
        for row in border_rows:
            rows.append({**row, "border_key": border_key})

    if not rows:
        return {
            "dataset": {
                "dataset_id": "entsoe_cross_border_flow_fi",
                "dataset_code": "A11_FI_BORDERS",
                "name": "Finland cross-border physical flows",
                "unit": "MW",
                "frequency": "1h",
                "status": "configured",
                "record_count": 0,
                "coverage_start_utc": None,
                "coverage_end_utc": None,
            },
            "summary": {
                "latest_total_flow_mw": None,
                "border_count": 0,
                "largest_border": None,
            },
            "series": [],
        }

    latest_timestamp = max(row["timestamp_utc"] for row in rows)
    latest_total = sum(float(row["flow_mw"]) for row in rows if row["timestamp_utc"] == latest_timestamp)
    totals_by_border: dict[str, float] = defaultdict(float)
    for row in rows:
        totals_by_border[row["border_key"]] += float(row["flow_mw"])

    largest_border = max(totals_by_border.items(), key=lambda item: item[1])[0] if totals_by_border else None
    return {
        "dataset": {
            "dataset_id": "entsoe_cross_border_flow_fi",
            "dataset_code": "A11_FI_BORDERS",
            "name": "Finland cross-border physical flows",
            "unit": "MW",
            "frequency": "1h",
            "status": "live",
            "record_count": len(rows),
            "coverage_start_utc": rows[0]["timestamp_utc"],
            "coverage_end_utc": rows[-1]["timestamp_utc"],
        },
        "summary": {
            "latest_total_flow_mw": round(latest_total, 2),
            "border_count": len(totals_by_border),
            "largest_border": largest_border,
        },
        "series": rows,
    }


def fetch_finland_generation_forecast_summary(
    *,
    client: EntsoeClient | None = None,
    now_utc: dt.datetime | None = None,
) -> dict:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    period_start = now_utc.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + dt.timedelta(days=1)
    client = client or EntsoeClient()
    rows = client.fetch_generation_forecast(
        in_domain=FINLAND_BIDDING_ZONE,
        period_start=_format_period(period_start),
        period_end=_format_period(period_end),
    )
    if not rows:
        return {
            "dataset": {
                "dataset_id": "entsoe_generation_forecast_fi",
                "dataset_code": "A71_A01_FI",
                "name": "Finland generation forecast",
                "unit": "MW",
                "frequency": "1h",
                "status": "configured",
                "record_count": 0,
                "coverage_start_utc": None,
                "coverage_end_utc": None,
            },
            "summary": {
                "latest_generation_forecast_mw": None,
                "average_generation_forecast_mw": None,
            },
            "series": [],
        }

    values = [float(row["generation_forecast_mw"]) for row in rows]
    return {
        "dataset": {
            "dataset_id": "entsoe_generation_forecast_fi",
            "dataset_code": "A71_A01_FI",
            "name": "Finland generation forecast",
            "unit": "MW",
            "frequency": "1h",
            "status": "live",
            "record_count": len(rows),
            "coverage_start_utc": rows[0]["timestamp_utc"],
            "coverage_end_utc": rows[-1]["timestamp_utc"],
        },
        "summary": {
            "latest_generation_forecast_mw": values[-1],
            "average_generation_forecast_mw": round(sum(values) / len(values), 2),
        },
        "series": rows,
    }
