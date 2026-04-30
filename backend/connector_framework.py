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
        notes="Uses trading_price_* yearly tables as the current landing model.",
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
