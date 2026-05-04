from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorSpec:
    source_id: str
    market: str
    entrypoint: str
    run_modes: tuple[str, ...]
    backfill_policy: str
    rate_limit: str
    schema_mapping: str
    quality_checks: tuple[str, ...]
    dataset_family: str
    observation_kind: str
    adapter: str
    notes: str = ""


CONNECTOR_SPECS = (
    ConnectorSpec(
        source_id="aemo_nem_trading_price",
        market="NEM",
        entrypoint="scrapers.aemo_nem_scraper",
        run_modes=("backfill",),
        backfill_policy="year_sharded_table_backfill",
        rate_limit="manual_batch_source",
        schema_mapping="map_nem_trading_price_row",
        quality_checks=("coverage", "duplicate_interval", "null_price"),
        dataset_family="settlement",
        observation_kind="actual",
        adapter="map_nem_trading_price_row",
        notes="Uses trading_price_* yearly tables as the current landing model.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_operational_demand",
        market="NEM",
        entrypoint="scrapers.aemo_operational_demand_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_load_actual_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="load_actual",
        observation_kind="actual",
        adapter="build_aemo_load_actual_series",
        notes="Represents the AEMO operational demand dataset in canonical load-actual form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_load_forecast",
        market="NEM",
        entrypoint="scrapers.aemo_load_forecast_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_load_forecast_series",
        quality_checks=("coverage", "duplicate_interval", "null_value", "forecast_horizon"),
        dataset_family="load_forecast",
        observation_kind="forecast",
        adapter="build_aemo_load_forecast_series",
        notes="Represents AEMO demand forecast in canonical load-forecast form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_wind_forecast",
        market="NEM",
        entrypoint="scrapers.aemo_wind_forecast_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_wind_forecast_series",
        quality_checks=("coverage", "duplicate_interval", "null_value", "forecast_horizon"),
        dataset_family="wind_forecast",
        observation_kind="forecast",
        adapter="build_aemo_wind_forecast_series",
        notes="Represents AEMO wind forecast in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_wind_actual",
        market="NEM",
        entrypoint="scrapers.aemo_wind_actual_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_wind_actual_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="wind_actual",
        observation_kind="actual",
        adapter="build_aemo_wind_actual_series",
        notes="Represents AEMO wind actual output in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_solar_forecast",
        market="NEM",
        entrypoint="scrapers.aemo_solar_forecast_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_solar_forecast_series",
        quality_checks=("coverage", "duplicate_interval", "null_value", "forecast_horizon"),
        dataset_family="solar_forecast",
        observation_kind="forecast",
        adapter="build_aemo_solar_forecast_series",
        notes="Represents AEMO solar forecast in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_solar_actual",
        market="NEM",
        entrypoint="scrapers.aemo_solar_actual_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_solar_actual_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="solar_actual",
        observation_kind="actual",
        adapter="build_aemo_solar_actual_series",
        notes="Represents AEMO solar actual output in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_rooftop_pv",
        market="NEM",
        entrypoint="scrapers.aemo_rooftop_pv_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_rooftop_pv_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="rooftop_pv",
        observation_kind="actual",
        adapter="build_aemo_rooftop_pv_series",
        notes="Represents AEMO rooftop PV estimate in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_outage",
        market="NEM",
        entrypoint="scrapers.aemo_outage_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_event_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_outage_series",
        quality_checks=("coverage", "duplicate_event", "null_value"),
        dataset_family="outage",
        observation_kind="event",
        adapter="build_aemo_outage_series",
        notes="Represents AEMO outage events in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_interconnector_flow",
        market="NEM",
        entrypoint="scrapers.aemo_interconnector_flow_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_interconnector_flow_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="interconnector_flow",
        observation_kind="actual",
        adapter="build_aemo_interconnector_flow_series",
        notes="Represents AEMO interconnector flows in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_reserve_requirement",
        market="NEM",
        entrypoint="scrapers.aemo_reserve_requirement_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_reserve_requirement_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="reserve_requirement",
        observation_kind="state",
        adapter="build_aemo_reserve_requirement_series",
        notes="Represents AEMO reserve requirement in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_wem_reserve_shortfall",
        market="WEM",
        entrypoint="scrapers.aemo_reserve_shortfall_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_reserve_shortfall_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="reserve_shortfall",
        observation_kind="event",
        adapter="build_aemo_reserve_shortfall_series",
        notes="Represents AEMO reserve shortfall events in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_weather",
        market="NEM",
        entrypoint="scrapers.aemo_weather_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_weather_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="weather",
        observation_kind="actual",
        adapter="build_aemo_weather_series",
        notes="Represents weather inputs in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_nem_unit_availability",
        market="NEM",
        entrypoint="scrapers.aemo_unit_availability_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="windowed_series_backfill",
        rate_limit="market_api_windowed",
        schema_mapping="build_aemo_unit_availability_series",
        quality_checks=("coverage", "duplicate_interval", "null_value"),
        dataset_family="unit_availability",
        observation_kind="state",
        adapter="build_aemo_unit_availability_series",
        notes="Represents unit availability state in canonical form.",
    ),
    ConnectorSpec(
        source_id="aemo_wem_ess_market",
        market="WEM",
        entrypoint="scrapers.wem_ess_slim_scraper",
        run_modes=("incremental", "backfill"),
        backfill_policy="rolling_month_plus_explicit_backfill",
        rate_limit="single_market_slim_sync",
        schema_mapping="map_wem_ess_market_row",
        quality_checks=("coverage", "duplicate_interval", "null_price"),
        dataset_family="settlement",
        observation_kind="actual",
        adapter="map_wem_ess_market_row",
        notes="Targets the slim preview WEM ESS market tables.",
    ),
    ConnectorSpec(
        source_id="fingrid_dataset_317",
        market="FINGRID",
        entrypoint="fingrid.service.sync_dataset",
        run_modes=("incremental", "backfill"),
        backfill_policy="dataset_windowed_backfill",
        rate_limit="per_dataset_month_window",
        schema_mapping="map_fingrid_timeseries_row",
        quality_checks=("coverage", "resolution_mix", "staleness"),
        dataset_family="reserve_requirement",
        observation_kind="actual",
        adapter="map_fingrid_timeseries_row",
        notes="Represents Fingrid dataset 317 using the normalized timeseries pipeline.",
    ),
)

CONNECTOR_BY_ID = {spec.source_id: spec for spec in CONNECTOR_SPECS}


def list_connector_specs() -> list[ConnectorSpec]:
    return list(CONNECTOR_SPECS)


def get_connector_spec(source_id: str) -> ConnectorSpec:
    try:
        return CONNECTOR_BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown connector source_id: {source_id}") from exc
