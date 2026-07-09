import os
import sys
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database import DatabaseManager
from fingrid.client import FingridClient
from fingrid.service import sync_dataset


BACKFILL_STARTS = {
    "281": "2022-01-01T00:00:00Z",
    "283": "2021-04-01T00:00:00Z",
    "315": "2020-01-01T00:00:00Z",
    "316": "2020-01-01T00:00:00Z",
    "317": "2020-01-01T00:00:00Z",
    "318": "2021-01-01T00:00:00Z",
    "319": "2022-01-01T00:00:00Z",
}


def load_env():
    for env_path in (REPO_ROOT / ".env", BACKEND_ROOT / ".env"):
        if not env_path.exists():
            continue
        values = dotenv_values(env_path)
        for key, value in values.items():
            if value is not None and key not in os.environ:
                os.environ[key] = value


def main() -> int:
    load_env()
    db = DatabaseManager()
    client = FingridClient(request_interval_seconds=8.0, timeout_seconds=60)

    for dataset_id, start in BACKFILL_STARTS.items():
        coverage_before = db.fetch_fingrid_dataset_coverage(dataset_id)
        print(
            f"[start] dataset={dataset_id} from={start} "
            f"coverage_before={coverage_before.get('coverage_start_utc')}..{coverage_before.get('coverage_end_utc')} "
            f"rows={coverage_before.get('record_count')}",
            flush=True,
        )
        try:
            result = sync_dataset(
                db,
                dataset_id=dataset_id,
                mode="backfill",
                start=start,
                client=client,
            )
        except Exception as exc:
            print(f"[error] dataset={dataset_id} error={exc}", flush=True)
            continue

        coverage_after = db.fetch_fingrid_dataset_coverage(dataset_id)
        print(
            f"[done] dataset={dataset_id} windows={result['windows_synced']} rows_upserted={result['records_upserted']} "
            f"coverage_after={coverage_after.get('coverage_start_utc')}..{coverage_after.get('coverage_end_utc')} "
            f"rows={coverage_after.get('record_count')}",
            flush=True,
        )

    print("[complete] fingrid hourly backfill queue finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
