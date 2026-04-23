import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from database import DatabaseManager
from fingrid.service import sync_dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fingrid dataset sync")
    parser.add_argument("--dataset", required=True, help="Fingrid dataset id, for example 317")
    parser.add_argument("--mode", required=True, choices=["backfill", "incremental"])
    parser.add_argument("--start", help="Optional UTC ISO-8601 start")
    parser.add_argument("--end", help="Optional UTC ISO-8601 end")
    parser.add_argument("--db", default="../data/aemo_data.db")
    args = parser.parse_args()

    db = DatabaseManager(args.db)
    result = sync_dataset(
        db,
        dataset_id=args.dataset,
        mode=args.mode,
        start=args.start,
        end=args.end,
    )
    print(result)
