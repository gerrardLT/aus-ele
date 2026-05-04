from __future__ import annotations

from canonical_market_schema import build_series_contract


def _build_aemo_power_series(
    *,
    dataset_family: str,
    observation_kind: str,
    source_id: str,
    source_version: str,
    rows: list[dict],
    region: str,
    ingested_at: str,
    counterpart_series_id: str | None = None,
    lineage: dict | None = None,
) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
        }
        for row in rows
    ]
    quality = {"completeness": 1.0 if points else 0.0}
    if rows and rows[0].get("run_at"):
        quality["forecast_run_at"] = rows[0]["run_at"]
    return build_series_contract(
        dataset_family=dataset_family,
        observation_kind=observation_kind,
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="MW",
        points=points,
        source_name="AEMO",
        source_version=source_version,
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality=quality,
        lineage={"source_id": source_id, **dict(lineage or {})},
        counterpart_series_id=counterpart_series_id,
    )


def build_aemo_load_actual_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="load_actual",
        observation_kind="actual",
        source_id="aemo_nem_operational_demand",
        source_version="aemo_operational_demand_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
        counterpart_series_id=f"load_forecast:{region}",
    )


def build_aemo_load_forecast_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="load_forecast",
        observation_kind="forecast",
        source_id="aemo_nem_load_forecast",
        source_version="aemo_load_forecast_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
        counterpart_series_id=f"load_actual:{region}",
    )


def build_aemo_wind_forecast_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="wind_forecast",
        observation_kind="forecast",
        source_id="aemo_nem_wind_forecast",
        source_version="aemo_wind_forecast_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
        counterpart_series_id=f"wind_actual:{region}",
    )


def build_aemo_wind_actual_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="wind_actual",
        observation_kind="actual",
        source_id="aemo_nem_wind_actual",
        source_version="aemo_wind_actual_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
        counterpart_series_id=f"wind_forecast:{region}",
        lineage={
            "measurement_basis": "dispatch_clearedmw_proxy",
            "note": "Uses AEMO dispatch cleared MW as a first-pass actual proxy, not direct meter output.",
        },
    )


def build_aemo_solar_forecast_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="solar_forecast",
        observation_kind="forecast",
        source_id="aemo_nem_solar_forecast",
        source_version="aemo_solar_forecast_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
        counterpart_series_id=f"solar_actual:{region}",
    )


def build_aemo_solar_actual_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="solar_actual",
        observation_kind="actual",
        source_id="aemo_nem_solar_actual",
        source_version="aemo_solar_actual_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
        counterpart_series_id=f"solar_forecast:{region}",
        lineage={
            "measurement_basis": "dispatch_clearedmw_proxy",
            "note": "Uses AEMO dispatch cleared MW as a first-pass actual proxy, not direct meter output.",
        },
    )


def build_aemo_rooftop_pv_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    return _build_aemo_power_series(
        dataset_family="rooftop_pv",
        observation_kind="actual",
        source_id="aemo_nem_rooftop_pv",
        source_version="aemo_rooftop_pv_v1",
        rows=rows,
        region=region,
        ingested_at=ingested_at,
    )


def build_aemo_outage_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "unit_id": row["unit_id"],
            "event_start_utc": row["event_start"],
            "event_end_utc": row["event_end"],
            "available_capacity_mw": row["available_capacity_mw"],
            "outage_capacity_mw": row["outage_capacity_mw"],
            "outage_type": row["outage_type"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="outage",
        observation_kind="event",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=None,
        unit=None,
        points=points,
        source_name="AEMO",
        source_version="aemo_outage_v1",
        ingested_at=ingested_at,
        coverage={"event_count": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_nem_outage"},
    )


def build_aemo_interconnector_flow_series(
    *,
    rows: list[dict],
    interconnector_id: str,
    ingested_at: str,
) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
            "from_region": row["from_region"],
            "to_region": row["to_region"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="interconnector_flow",
        observation_kind="actual",
        market="NEM",
        country="Australia",
        region_or_zone=interconnector_id,
        interval_minutes=30,
        unit="MW",
        points=points,
        source_name="AEMO",
        source_version="aemo_interconnector_flow_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_nem_interconnector_flow"},
    )


def build_aemo_reserve_requirement_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
            "reserve_service": row["reserve_service"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="reserve_requirement",
        observation_kind="state",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="MW",
        points=points,
        source_name="AEMO",
        source_version="aemo_reserve_requirement_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_nem_reserve_requirement"},
    )


def build_aemo_reserve_shortfall_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
            "reserve_service": row["reserve_service"],
            "severity": row["severity"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="reserve_shortfall",
        observation_kind="event",
        market="WEM" if region == "WEM" else "NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="MW",
        points=points,
        source_name="AEMO",
        source_version="aemo_reserve_shortfall_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_wem_reserve_shortfall"},
    )


def build_aemo_weather_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "temperature_c": row["temperature_c"],
            "wind_speed_mps": row["wind_speed_mps"],
            "cloud_cover_pct": row["cloud_cover_pct"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="weather",
        observation_kind="actual",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit=None,
        points=points,
        source_name="AEMO",
        source_version="aemo_weather_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_nem_weather"},
    )


def build_aemo_unit_availability_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "unit_id": row["unit_id"],
            "available_capacity_mw": row["available_capacity_mw"],
            "max_capacity_mw": row["max_capacity_mw"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="unit_availability",
        observation_kind="state",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="MW",
        points=points,
        source_name="AEMO",
        source_version="aemo_unit_availability_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_nem_unit_availability"},
    )


def build_aemo_constraint_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "constraint_id": row["constraint_id"],
            "interval_start_utc": row["effective_start"],
            "interval_end_utc": row["effective_end"],
            "binding_flag": bool(row["binding_flag"]),
            "shadow_price": row["shadow_price"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="constraint",
        observation_kind="state",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=5,
        unit=None,
        points=points,
        source_name="AEMO",
        source_version="aemo_constraint_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_constraint"},
    )


def build_aemo_settlement_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
            "component": row["component"],
            "counterparty_type": row.get("counterparty_type", "unknown"),
        }
        for row in rows
    ]
    finality = rows[0]["finality"] if rows else "unknown"
    component = rows[0]["component"] if rows else "unknown"
    settlement_run = rows[0].get("settlement_run", "default") if rows else "unknown"
    counterparty_type = rows[0].get("counterparty_type", "unknown") if rows else "unknown"
    return build_series_contract(
        dataset_family="settlement",
        observation_kind="settlement",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="AUD",
        points=points,
        source_name="AEMO",
        source_version="aemo_settlement_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={
            "completeness": 1.0 if points else 0.0,
            "finality": finality,
            "component": component,
            "settlement_run": settlement_run,
            "counterparty_type": counterparty_type,
        },
        lineage={"source_id": "aemo_settlement"},
    )
