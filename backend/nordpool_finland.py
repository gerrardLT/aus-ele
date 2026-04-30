from __future__ import annotations

import datetime as dt

from nordpool_client import NordPoolClient


def fetch_finland_day_ahead_summary(
    *,
    client: NordPoolClient | None = None,
    delivery_date: dt.date | None = None,
) -> dict:
    delivery_date = delivery_date or dt.datetime.now(dt.timezone.utc).date()
    client = client or NordPoolClient()
    rows = client.fetch_day_ahead_area_prices(
        delivery_area="FI",
        delivery_date=delivery_date,
        currency="EUR",
    )

    if not rows:
        return {
            "dataset": {
                "dataset_id": "nordpool_day_ahead_fi",
                "dataset_code": "prices_area_fi",
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
            "series": [],
        }

    prices = [float(row["price"]) for row in rows]
    return {
        "dataset": {
            "dataset_id": "nordpool_day_ahead_fi",
            "dataset_code": "prices_area_fi",
            "name": "Finland day-ahead prices",
            "unit": "EUR/MWh",
            "frequency": "1h",
            "status": "live",
            "record_count": len(rows),
            "coverage_start_utc": rows[0]["timestamp_utc"],
            "coverage_end_utc": rows[-1]["timestamp_utc"],
        },
        "summary": {
            "latest_price": prices[-1],
            "average_price": round(sum(prices) / len(prices), 2),
        },
        "series": rows,
    }


def fetch_finland_intraday_summary(
    *,
    client: NordPoolClient | None = None,
    delivery_date: dt.date | None = None,
) -> dict:
    delivery_date = delivery_date or dt.datetime.now(dt.timezone.utc).date()
    client = client or NordPoolClient()
    delivery_start_from = dt.datetime.combine(delivery_date, dt.time.min, tzinfo=dt.timezone.utc)
    delivery_start_to = delivery_start_from + dt.timedelta(days=1)
    rows = client.fetch_intraday_trades_by_delivery_start(
        areas=["FI"],
        delivery_start_from=delivery_start_from,
        delivery_start_to=delivery_start_to,
    )

    if not rows:
        return {
            "dataset": {
                "dataset_id": "nordpool_intraday_fi",
                "dataset_code": "intraday_trades_delivery_fi",
                "name": "Finland intraday trades",
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
                "total_volume_mwh": None,
            },
            "series": [],
        }

    prices = [float(row["price"]) for row in rows]
    total_volume_mwh = sum(float(row.get("volume_mwh") or 0.0) for row in rows)
    return {
        "dataset": {
            "dataset_id": "nordpool_intraday_fi",
            "dataset_code": "intraday_trades_delivery_fi",
            "name": "Finland intraday trades",
            "unit": "EUR/MWh",
            "frequency": "1h",
            "status": "live",
            "record_count": len(rows),
            "coverage_start_utc": rows[0]["timestamp_utc"],
            "coverage_end_utc": rows[-1]["timestamp_utc"],
        },
        "summary": {
            "latest_price": prices[-1],
            "average_price": round(sum(prices) / len(prices), 2),
            "total_volume_mwh": round(total_volume_mwh, 2),
        },
        "series": rows,
    }
