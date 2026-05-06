from __future__ import annotations

from datetime import datetime, timezone

from .catalog import get_dataset_config
from .schemas import normalize_fingrid_row
from .service import seed_dataset_catalog

# Source: Fingrid public reserve market page accessed on 2026-05-05.
# https://www.fingrid.fi/en/electricity-market-information/reserve-market-information/frequency-controlled-disturbance-reserve/
YEARLY_MARKET_ROWS = [
    {"year": 2022, "fcr_n_price": 12.24, "fcr_n_volume": 102.8, "fcr_d_up_price": 1.90, "fcr_d_up_volume": 430.6, "fcr_d_down_price": 10.0, "fcr_d_down_volume": 114.4},
    {"year": 2023, "fcr_n_price": 19.10, "fcr_n_volume": 67.7, "fcr_d_up_price": 2.81, "fcr_d_up_volume": 345.1, "fcr_d_down_price": 9.99, "fcr_d_down_volume": 186.4},
    {"year": 2024, "fcr_n_price": 25.39, "fcr_n_volume": 67.5, "fcr_d_up_price": 4.00, "fcr_d_up_volume": 347.8, "fcr_d_down_price": 9.50, "fcr_d_down_volume": 245.2},
    {"year": 2025, "fcr_n_price": 25.30, "fcr_n_volume": 52.5, "fcr_d_up_price": 4.00, "fcr_d_up_volume": 292.4, "fcr_d_down_price": 8.66, "fcr_d_down_volume": 202.6},
    {"year": 2026, "fcr_n_price": 0.0, "fcr_n_volume": 0.0, "fcr_d_up_price": 3.50, "fcr_d_up_volume": 237.0, "fcr_d_down_price": 6.00, "fcr_d_down_volume": 163.0},
]

DATASET_VALUE_MAP = {
    "288": "fcr_n_volume",
    "290": "fcr_d_up_volume",
    "321": "fcr_d_down_volume",
}


def _year_start(year: int) -> str:
    return f"{year}-01-01T00:00:00Z"


def seed_fingrid_yearly_market_rows(db, *, ingested_at: str | None = None) -> dict:
    seed_dataset_catalog(db)
    ingested_at = ingested_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = {}

    for dataset_id, value_key in DATASET_VALUE_MAP.items():
        dataset = get_dataset_config(dataset_id)
        normalized_rows = []
        for row in YEARLY_MARKET_ROWS:
            normalized_rows.append(
                normalize_fingrid_row(
                    dataset,
                    {
                        "startTime": _year_start(row["year"]),
                        "endTime": _year_start(row["year"] + 1),
                        "value": row[value_key],
                        "quality": "official_page_seed",
                        "updatedAt": ingested_at,
                    },
                    ingested_at=ingested_at,
                )
            )

        db.upsert_fingrid_timeseries(normalized_rows)
        last_timestamp_utc = normalized_rows[-1]["timestamp_utc"] if normalized_rows else None
        db.upsert_fingrid_sync_state(
            dataset_id=dataset_id,
            last_success_at=ingested_at,
            last_attempt_at=ingested_at,
            last_cursor=last_timestamp_utc,
            last_synced_timestamp_utc=last_timestamp_utc,
            sync_status="ok",
            last_error=None,
            backfill_started_at=None,
            backfill_completed_at=None,
        )
        counts[dataset_id] = len(normalized_rows)

    return {
        "mode": "official_page_seed",
        "source": "fingrid_yearly_market_page",
        "dataset_counts": counts,
    }
