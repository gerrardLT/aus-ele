import argparse
import logging
import sys

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from database import DatabaseManager
import grid_events


logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Sync official grid event sources into PostgreSQL.")
    parser.add_argument("--days", type=int, default=180, help="Lookback window in days for rolling sources")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    db = DatabaseManager()
    result = grid_events.sync_event_sources(db, days=args.days)
    logger.info("Grid event sync completed: %s", result)


if __name__ == "__main__":
    main()
