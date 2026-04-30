FINGRID_DATASETS = {
    "317": {
        "dataset_id": "317",
        "dataset_code": "fcrn_hourly_market_price",
        "name": "FCR-N hourly market prices",
        "description": "FCR-N hourly reserve-capacity market price in Finland.",
        "unit": "EUR/MW",
        "frequency": "1h",
        "timezone": "Europe/Helsinki",
        "value_kind": "reserve_capacity_price",
        "source_url": "https://data.fingrid.fi/en/datasets/317",
        "api_path": "/datasets/317/data",
        "series_key": "fcrn_hourly_market_price",
        "default_backfill_start": "2014-01-01T00:00:00Z",
        "default_incremental_lookback_days": 30,
        "supported_aggregations": ["raw", "1h", "2h", "4h", "day", "week", "month"],
        "metadata_json": {
            "market": "Fingrid",
            "product": "FCR-N",
        },
    },
    "319": {
        "dataset_id": "319",
        "dataset_code": "imbalance_price",
        "name": "Imbalance price",
        "description": "Imbalance price in Finland.",
        "unit": "EUR/MWh",
        "frequency": "1h+",
        "timezone": "Europe/Helsinki",
        "value_kind": "imbalance_price",
        "source_url": "https://data.fingrid.fi/en/datasets/319",
        "api_path": "/datasets/319/data",
        "series_key": "imbalance_price",
        "default_backfill_start": "2025-01-01T00:00:00Z",
        "default_incremental_lookback_days": 30,
        "supported_aggregations": ["raw", "1h", "2h", "4h", "day", "week", "month"],
        "metadata_json": {
            "market": "Fingrid",
            "product": "Imbalance",
        },
    },
}


def get_dataset_config(dataset_id: str) -> dict:
    if dataset_id not in FINGRID_DATASETS:
        raise KeyError(f"Unsupported Fingrid dataset: {dataset_id}")
    return dict(FINGRID_DATASETS[dataset_id])


def list_dataset_configs() -> list[dict]:
    return [dict(FINGRID_DATASETS[key]) for key in sorted(FINGRID_DATASETS)]
