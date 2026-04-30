from __future__ import annotations

import os
from statistics import mean

from data_quality import compute_quality_snapshots
from entsoe_finland import (
    fetch_finland_cross_border_flow_summary,
    fetch_finland_day_ahead_summary,
    fetch_finland_generation_forecast_summary,
    fetch_finland_generation_mix_summary,
    fetch_finland_total_load_summary,
)
from fingrid.catalog import list_dataset_configs
from nordpool_finland import (
    fetch_finland_day_ahead_summary as fetch_nordpool_finland_day_ahead_summary,
    fetch_finland_intraday_summary as fetch_nordpool_finland_intraday_summary,
)
from result_metadata import build_result_metadata


def _quality_score_for_finland(db) -> float | None:
    rows = db.fetch_data_quality_snapshots()
    if not rows:
        rows = compute_quality_snapshots(db)
    scores = [
        float(row["quality_score"])
        for row in rows
        if row.get("market") == "FINGRID" and row.get("quality_score") is not None
    ]
    if not scores:
        return None
    return round(mean(scores) * 100.0, 1)


def _dataset_live_signal(dataset: dict, coverage: dict, sync_state: dict | None) -> dict:
    return {
        "dataset_id": dataset["dataset_id"],
        "dataset_code": dataset.get("dataset_code"),
        "signal_key": dataset["value_kind"],
        "label": dataset["name"],
        "unit": dataset["unit"],
        "source_key": "fingrid",
        "availability": "live" if coverage.get("record_count", 0) > 0 else "catalogued",
        "coverage_end_utc": coverage.get("coverage_end_utc"),
        "sync_status": (sync_state or {}).get("sync_status", "not_started"),
    }


def _build_fingrid_source(db) -> tuple[dict, list[dict]]:
    datasets = []
    live_signals = []
    for dataset in list_dataset_configs():
        coverage = db.fetch_fingrid_dataset_coverage(dataset["dataset_id"])
        sync_state = db.fetch_fingrid_sync_state(dataset["dataset_id"])
        record_count = int(coverage.get("record_count") or 0)
        dataset_status = "live" if record_count > 0 else "catalogued"
        dataset_entry = {
            "dataset_id": dataset["dataset_id"],
            "dataset_code": dataset.get("dataset_code"),
            "name": dataset["name"],
            "value_kind": dataset["value_kind"],
            "unit": dataset["unit"],
            "frequency": dataset["frequency"],
            "status": dataset_status,
            "coverage_start_utc": coverage.get("coverage_start_utc"),
            "coverage_end_utc": coverage.get("coverage_end_utc"),
            "record_count": record_count,
            "sync_status": (sync_state or {}).get("sync_status", "not_started"),
            "source_url": dataset["source_url"],
        }
        datasets.append(dataset_entry)
        if record_count > 0:
            live_signals.append(_dataset_live_signal(dataset, coverage, sync_state))

    live_count = sum(1 for dataset in datasets if dataset["status"] == "live")
    return (
        {
            "source_key": "fingrid",
            "display_name": "Fingrid",
            "status": "live" if live_count > 0 else "partial",
            "role": "system_and_balancing_data",
            "coverage": {
                "datasets_total": len(datasets),
                "datasets_live": live_count,
            },
            "datasets": datasets,
            "notes": [
                "Current Finland v1 is anchored on Fingrid operational and balancing datasets.",
                "Imbalance context is now modeled separately from reserve-capacity pricing.",
            ],
        },
        live_signals,
    )


def _configured_env_value(*keys: str) -> str | None:
    for key in keys:
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _build_nord_pool_source() -> dict:
    base_url = _configured_env_value("NORDPOOL_API_BASE_URL") or "https://data-api.nordpoolgroup.com"
    access_token = _configured_env_value("NORDPOOL_ACCESS_TOKEN", "NORDPOOL_API_KEY", "NORDPOOL_SUBSCRIPTION_KEY")
    token_url = _configured_env_value("NORDPOOL_TOKEN_URL")
    client_id = _configured_env_value("NORDPOOL_CLIENT_ID")
    client_secret = _configured_env_value("NORDPOOL_CLIENT_SECRET")
    configured = bool(access_token or (token_url and client_id and client_secret))
    status = "configured" if configured else "planned"
    readiness = "configured" if configured else "credentials_required"
    notes = [
        "Reserved for Finland day-ahead and intraday price integration.",
        "Official access normally requires commercial API entitlement and credentials.",
    ]
    if not configured:
        notes.append(
            "Set NORDPOOL_ACCESS_TOKEN / NORDPOOL_API_KEY, or provide NORDPOOL_TOKEN_URL + NORDPOOL_CLIENT_ID + NORDPOOL_CLIENT_SECRET."
        )
    return {
        "source_key": "nord_pool",
        "display_name": "Nord Pool",
        "status": status,
        "role": "day_ahead_and_intraday_prices",
        "coverage": {"datasets_total": 0, "datasets_live": 0},
        "datasets": [],
        "integration": {
            "provider_type": "api",
            "auth_mode": "subscription_api_account",
            "configured": configured,
            "readiness": readiness,
            "base_url": base_url,
            "capabilities": ["day_ahead_prices", "intraday_prices"],
            "supported_auth_modes": ["bearer_token", "client_credentials"],
        },
        "notes": notes,
    }


def _enrich_nord_pool_source(source: dict) -> tuple[dict, list[dict]]:
    if not source.get("integration", {}).get("configured"):
        return source, []
    try:
        day_ahead_payload = fetch_nordpool_finland_day_ahead_summary()
        intraday_payload = fetch_nordpool_finland_intraday_summary()
    except Exception as exc:
        return {
            **source,
            "status": "configured",
            "notes": [*source.get("notes", []), f"Latest live fetch failed: {exc}"],
        }, []

    datasets = [day_ahead_payload["dataset"], intraday_payload["dataset"]]
    live_signals = [
        {
            "dataset_id": day_ahead_payload["dataset"]["dataset_id"],
            "dataset_code": day_ahead_payload["dataset"]["dataset_code"],
            "signal_key": "day_ahead_price",
            "label": day_ahead_payload["dataset"]["name"],
            "unit": day_ahead_payload["dataset"]["unit"],
            "source_key": "nord_pool",
            "availability": day_ahead_payload["dataset"]["status"],
            "coverage_end_utc": day_ahead_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        },
        {
            "dataset_id": intraday_payload["dataset"]["dataset_id"],
            "dataset_code": intraday_payload["dataset"]["dataset_code"],
            "signal_key": "intraday_price",
            "label": intraday_payload["dataset"]["name"],
            "unit": intraday_payload["dataset"]["unit"],
            "source_key": "nord_pool",
            "availability": intraday_payload["dataset"]["status"],
            "coverage_end_utc": intraday_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        }
    ]
    enriched = {
        **source,
        "status": "live" if any(item["status"] == "live" for item in datasets) else "configured",
        "coverage": {
            "datasets_total": len(datasets),
            "datasets_live": sum(1 for item in datasets if item["status"] == "live"),
        },
        "datasets": datasets,
        "summary": {
            "day_ahead_latest_price": day_ahead_payload["summary"].get("latest_price"),
            "day_ahead_average_price": day_ahead_payload["summary"].get("average_price"),
            "intraday_latest_price": intraday_payload["summary"].get("latest_price"),
            "intraday_average_price": intraday_payload["summary"].get("average_price"),
            "intraday_total_volume_mwh": intraday_payload["summary"].get("total_volume_mwh"),
        },
    }
    return enriched, live_signals


def _build_entsoe_source() -> dict:
    base_url = _configured_env_value("ENTSOE_API_BASE_URL") or "https://web-api.tp.entsoe.eu/api"
    security_token = _configured_env_value("ENTSOE_SECURITY_TOKEN")
    configured = bool(security_token)
    status = "configured" if configured else "planned"
    readiness = "configured" if configured else "credentials_required"
    notes = [
        "Reserved for cross-border flow, generation mix, and transparency context.",
        "Official access requires a registered Transparency Platform security token.",
    ]
    if not configured:
        notes.append("Set ENTSOE_SECURITY_TOKEN to enable connector configuration.")
    return {
        "source_key": "entsoe",
        "display_name": "ENTSO-E",
        "status": status,
        "role": "transparency_and_cross_border",
        "coverage": {"datasets_total": 0, "datasets_live": 0},
        "datasets": [],
        "integration": {
            "provider_type": "api",
            "auth_mode": "security_token",
            "configured": configured,
            "readiness": readiness,
            "base_url": base_url,
            "capabilities": ["cross_border_flows", "generation_mix", "transparency_context"],
        },
        "notes": notes,
    }


def _enrich_entsoe_source(source: dict) -> tuple[dict, list[dict]]:
    if not source.get("integration", {}).get("configured"):
        return source, []
    try:
        day_ahead_payload = fetch_finland_day_ahead_summary()
        total_load_payload = fetch_finland_total_load_summary()
        generation_mix_payload = fetch_finland_generation_mix_summary()
        cross_border_flow_payload = fetch_finland_cross_border_flow_summary()
        generation_forecast_payload = fetch_finland_generation_forecast_summary()
    except Exception as exc:
        return {
            **source,
            "status": "configured",
            "notes": [*source.get("notes", []), f"Latest live fetch failed: {exc}"],
        }, []

    datasets = [
        day_ahead_payload["dataset"],
        total_load_payload["dataset"],
        generation_mix_payload["dataset"],
        cross_border_flow_payload["dataset"],
        generation_forecast_payload["dataset"],
    ]
    summary = {
        **day_ahead_payload["summary"],
        **total_load_payload["summary"],
        **generation_mix_payload["summary"],
        **cross_border_flow_payload["summary"],
        **generation_forecast_payload["summary"],
    }
    live_signals = [
        {
            "dataset_id": day_ahead_payload["dataset"]["dataset_id"],
            "dataset_code": day_ahead_payload["dataset"]["dataset_code"],
            "signal_key": "day_ahead_price",
            "label": day_ahead_payload["dataset"]["name"],
            "unit": day_ahead_payload["dataset"]["unit"],
            "source_key": "entsoe",
            "availability": day_ahead_payload["dataset"]["status"],
            "coverage_end_utc": day_ahead_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        },
        {
            "dataset_id": total_load_payload["dataset"]["dataset_id"],
            "dataset_code": total_load_payload["dataset"]["dataset_code"],
            "signal_key": "total_load",
            "label": total_load_payload["dataset"]["name"],
            "unit": total_load_payload["dataset"]["unit"],
            "source_key": "entsoe",
            "availability": total_load_payload["dataset"]["status"],
            "coverage_end_utc": total_load_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        },
        {
            "dataset_id": generation_mix_payload["dataset"]["dataset_id"],
            "dataset_code": generation_mix_payload["dataset"]["dataset_code"],
            "signal_key": "generation_mix",
            "label": generation_mix_payload["dataset"]["name"],
            "unit": generation_mix_payload["dataset"]["unit"],
            "source_key": "entsoe",
            "availability": generation_mix_payload["dataset"]["status"],
            "coverage_end_utc": generation_mix_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        },
        {
            "dataset_id": cross_border_flow_payload["dataset"]["dataset_id"],
            "dataset_code": cross_border_flow_payload["dataset"]["dataset_code"],
            "signal_key": "cross_border_flow",
            "label": cross_border_flow_payload["dataset"]["name"],
            "unit": cross_border_flow_payload["dataset"]["unit"],
            "source_key": "entsoe",
            "availability": cross_border_flow_payload["dataset"]["status"],
            "coverage_end_utc": cross_border_flow_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        },
        {
            "dataset_id": generation_forecast_payload["dataset"]["dataset_id"],
            "dataset_code": generation_forecast_payload["dataset"]["dataset_code"],
            "signal_key": "generation_forecast",
            "label": generation_forecast_payload["dataset"]["name"],
            "unit": generation_forecast_payload["dataset"]["unit"],
            "source_key": "entsoe",
            "availability": generation_forecast_payload["dataset"]["status"],
            "coverage_end_utc": generation_forecast_payload["dataset"]["coverage_end_utc"],
            "sync_status": "live",
        },
    ]
    enriched = {
        **source,
        "status": "live" if any(item["status"] == "live" for item in datasets) else "configured",
        "coverage": {
            "datasets_total": len(datasets),
            "datasets_live": sum(1 for item in datasets if item["status"] == "live"),
        },
        "datasets": datasets,
        "summary": summary,
    }
    return enriched, live_signals


def build_finland_market_model_payload(db) -> dict:
    fingrid_source, live_signals = _build_fingrid_source(db)
    nord_pool_source, nord_pool_live_signals = _enrich_nord_pool_source(_build_nord_pool_source())
    entsoe_source, entsoe_live_signals = _enrich_entsoe_source(_build_entsoe_source())
    live_signals = [*live_signals, *nord_pool_live_signals, *entsoe_live_signals]
    quality_score = _quality_score_for_finland(db)
    live_dataset_count = fingrid_source["coverage"]["datasets_live"]
    metadata_warnings = ["planned_external_sources"]
    if live_dataset_count == 0:
        metadata_warnings.append("no_live_finland_datasets")
    configured_external_source_count = sum(
        1
        for source in (nord_pool_source, entsoe_source)
        if source.get("integration", {}).get("configured")
    )
    if configured_external_source_count:
        metadata_warnings.append("external_sources_configured")

    sources = [
        fingrid_source,
        nord_pool_source,
        entsoe_source,
    ]

    return {
        "country": "Finland",
        "market": "Finland",
        "model_status": "multi-source-live" if (nord_pool_live_signals or entsoe_live_signals) else "partial-live",
        "summary": {
            "live_source_count": 1 + (1 if nord_pool_live_signals else 0) + (1 if entsoe_live_signals else 0),
            "planned_source_count": 2,
            "configured_external_source_count": configured_external_source_count,
            "live_dataset_count": live_dataset_count + len(nord_pool_live_signals) + len(entsoe_live_signals),
            "live_signal_keys": [signal["signal_key"] for signal in live_signals],
            "coverage_scope": "Finland market model v1",
        },
        "sources": sources,
        "live_signals": live_signals,
        "metadata": build_result_metadata(
            market="FINLAND",
            region_or_zone="FI",
            timezone="Europe/Helsinki",
            currency="mixed",
            unit="mixed",
            interval_minutes=None,
            data_grade="analytical-preview",
            data_quality_score=quality_score,
            coverage={"live_dataset_count": live_dataset_count + len(nord_pool_live_signals) + len(entsoe_live_signals)},
            freshness={"last_updated_at": db.get_last_update_time()},
            source_name="Fingrid+NordPool+ENTSOE",
            source_version=db.get_last_update_time() or "finland_market_model_v1",
            methodology_version="finland_market_model_v1",
            warnings=metadata_warnings,
        ),
    }
