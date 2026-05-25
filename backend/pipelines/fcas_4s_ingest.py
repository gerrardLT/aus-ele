"""FCAS 4-second data ingest pipeline.

Fetches and stores 4-second resolution FCAS data from AEMO's DISPATCH_FCAS_4S
MMSDM table. Provides the Fcas4sIngestJob class for registration with the
job framework, and resolution fallback logic (4s → 5min).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table schema for 4-second FCAS data
# ---------------------------------------------------------------------------

FCAS_4S_TABLE = "fcas_4s_data"

FCAS_4S_COLUMNS = [
    "timestamp",          # ISO 8601 UTC timestamp (4-second resolution)
    "region_id",          # NEM region (NSW1, QLD1, VIC1, SA1, TAS1)
    "raise6sec_price",
    "raise60sec_price",
    "raise5min_price",
    "raisereg_price",
    "raise1sec_price",
    "lower6sec_price",
    "lower60sec_price",
    "lower5min_price",
    "lowerreg_price",
    "lower1sec_price",
    "total_demand_mw",
    "frequency_hz",
]

CREATE_FCAS_4S_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {FCAS_4S_TABLE} (
    timestamp TEXT NOT NULL,
    region_id TEXT NOT NULL,
    raise6sec_price REAL,
    raise60sec_price REAL,
    raise5min_price REAL,
    raisereg_price REAL,
    raise1sec_price REAL,
    lower6sec_price REAL,
    lower60sec_price REAL,
    lower5min_price REAL,
    lowerreg_price REAL,
    lower1sec_price REAL,
    total_demand_mw REAL,
    frequency_hz REAL,
    PRIMARY KEY (timestamp, region_id)
)
"""

CREATE_FCAS_4S_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{FCAS_4S_TABLE}_region_time
ON {FCAS_4S_TABLE} (region_id, timestamp)
"""

# ---------------------------------------------------------------------------
# Extended FCAS service types (includes 1-second services)
# ---------------------------------------------------------------------------

FCAS_4S_SERVICES = {
    "raise1sec": "Raise 1 Sec",
    "raise6sec": "Raise 6 Sec",
    "raise60sec": "Raise 60 Sec",
    "raise5min": "Raise 5 Min",
    "raisereg": "Raise Reg",
    "lower1sec": "Lower 1 Sec",
    "lower6sec": "Lower 6 Sec",
    "lower60sec": "Lower 60 Sec",
    "lower5min": "Lower 5 Min",
    "lowerreg": "Lower Reg",
}


# ---------------------------------------------------------------------------
# Stub source client (to be replaced with real AEMO MMSDM client)
# ---------------------------------------------------------------------------


class Fcas4sSourceClient:
    """Stub client for AEMO 4-second FCAS data (DISPATCH_FCAS_4S table).

    In production, this would connect to AEMO's MMSDM data model or
    their NEMWeb file server to fetch 4-second dispatch data.
    """

    def fetch_4s_data(
        self,
        *,
        since: str,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch 4-second FCAS data since the given timestamp.

        Args:
            since: ISO 8601 timestamp to fetch data from.
            region: Optional region filter (e.g., "NSW1").

        Returns:
            List of records matching FCAS_4S_COLUMNS schema.
        """
        # Stub: returns empty list. Real implementation would query
        # AEMO MMSDM DISPATCH_FCAS_4S table.
        logger.info(
            f"Fcas4sSourceClient.fetch_4s_data(since={since}, region={region}) "
            f"[stub - returning empty]"
        )
        return []


# ---------------------------------------------------------------------------
# Fcas4sIngestJob — registerable with JobOrchestrator
# ---------------------------------------------------------------------------


class Fcas4sIngestJob:
    """FCAS 4-second data ingest job.

    Fetches 4-second resolution FCAS data from AEMO and batch-writes
    it to the fcas_4s_data table. Designed to be registered with the
    job framework via JobRegistry.
    """

    JOB_TYPE = "fcas_4s_ingest"
    SOURCE_KEY = "aemo"

    def __init__(self, db, source_client: Fcas4sSourceClient | None = None):
        self.db = db
        self.source = source_client or Fcas4sSourceClient()

    def run(self, context) -> dict[str, Any]:
        """Execute the ingest job.

        Args:
            context: JobContext instance with set_progress() and is_cancel_requested().

        Returns:
            Dict with ingest summary (records_ingested, sync_timestamp).
        """
        # Ensure table exists
        self.ensure_fcas_4s_table()

        # Get last sync timestamp
        last_sync = self.db.get_system_status("fcas_4s_last_sync")
        since = last_sync or "2020-01-01T00:00:00Z"

        context.set_progress(10, f"Fetching 4s FCAS data since {since}")

        if context.is_cancel_requested():
            return {"status": "cancelled"}

        # Fetch data from source
        records = self.source.fetch_4s_data(since=since)

        if not records:
            context.set_progress(100, "No new 4s FCAS data available")
            return {"records_ingested": 0, "sync_timestamp": since}

        context.set_progress(50, f"Writing {len(records)} records to database")

        # Batch write
        self._batch_insert(records)

        # Update sync timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        self.db.set_system_status("fcas_4s_last_sync", now_iso)

        context.set_progress(100, "FCAS 4s ingest complete")
        return {"records_ingested": len(records), "sync_timestamp": now_iso}

    def ensure_fcas_4s_table(self) -> None:
        """Create the fcas_4s_data table if it doesn't exist."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(CREATE_FCAS_4S_TABLE_SQL)
            cursor.execute(CREATE_FCAS_4S_INDEX_SQL)
            conn.commit()

    def _batch_insert(self, records: list[dict[str, Any]]) -> None:
        """Batch insert/upsert records into the 4s table."""
        if not records:
            return

        columns = FCAS_4S_COLUMNS
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(CREATE_FCAS_4S_TABLE_SQL)

            insert_sql = (
                f"INSERT OR REPLACE INTO {FCAS_4S_TABLE} ({col_names}) "
                f"VALUES ({placeholders})"
            )

            batch = []
            for record in records:
                row = tuple(record.get(col) for col in columns)
                batch.append(row)

            cursor.executemany(insert_sql, batch)
            conn.commit()

        logger.info(f"Inserted {len(batch)} records into {FCAS_4S_TABLE}")


# ---------------------------------------------------------------------------
# Resolution fallback logic
# ---------------------------------------------------------------------------


def check_4s_data_available(db, *, region: str, year: int) -> bool:
    """Check if 4-second FCAS data is available for the given region and year.

    Args:
        db: DatabaseManager instance.
        region: NEM region ID (e.g., "NSW1").
        year: Year to check.

    Returns:
        True if 4s data exists for the region/year combination.
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Check if table exists
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (FCAS_4S_TABLE,),
            )
            if not cursor.fetchone():
                return False

            # Check if data exists for the region and year
            cursor.execute(
                f"SELECT 1 FROM {FCAS_4S_TABLE} "
                f"WHERE region_id = ? AND timestamp LIKE ? LIMIT 1",
                (region, f"{year}-%"),
            )
            return cursor.fetchone() is not None
    except Exception as e:
        logger.warning(f"Error checking 4s data availability: {e}")
        return False


def resolve_fcas_resolution(
    db,
    *,
    region: str,
    year: int,
    requested_resolution: str = "auto",
) -> dict[str, Any]:
    """Determine the actual FCAS data resolution to use.

    Implements the fallback logic: 4s → 5min.

    Args:
        db: DatabaseManager instance.
        region: NEM region ID.
        year: Year to query.
        requested_resolution: "auto" (default), "4s", or "5min".

    Returns:
        Dict with:
            - resolution_seconds: actual resolution in seconds (4 or 300)
            - source: "fcas_4s_data" or "trading_price_{year}"
            - fallback_used: whether fallback was applied
    """
    if requested_resolution == "5min":
        return {
            "resolution_seconds": 300,
            "source": f"trading_price_{year}",
            "fallback_used": False,
        }

    # For "auto" or "4s", try 4-second data first
    has_4s = check_4s_data_available(db, region=region, year=year)

    if has_4s:
        return {
            "resolution_seconds": 4,
            "source": FCAS_4S_TABLE,
            "fallback_used": False,
        }

    # Fallback to 5-minute data
    if requested_resolution == "4s":
        logger.info(
            f"4s data requested but not available for {region}/{year}, "
            f"falling back to 5min"
        )

    return {
        "resolution_seconds": 300,
        "source": f"trading_price_{year}",
        "fallback_used": True,
    }


# ---------------------------------------------------------------------------
# Job registration
# ---------------------------------------------------------------------------


def _fcas_4s_ingest_handler(job: dict, context) -> dict[str, Any]:
    """Job handler function compatible with JobRegistry.

    Entry point called by JobOrchestrator when the FCAS 4s ingest job
    is dequeued. Instantiates Fcas4sIngestJob with the context's database
    and runs the ingest.

    Args:
        job: Job record dict from the database.
        context: JobContext with db, job_id, and lake references.

    Returns:
        Dict with ingest results.
    """
    db = context.db
    ingest_job = Fcas4sIngestJob(db=db)
    return ingest_job.run(context)


def register_fcas_4s_job(registry) -> None:
    """Register the FCAS 4-second ingest job handler with the given JobRegistry.

    After registration, the job can be enqueued via:
        orchestrator.enqueue(
            "fcas_4s_ingest",
            payload={},
            queue_name="data-pipeline",
            source_key="aemo",
        )

    Args:
        registry: The JobRegistry instance to register with.
    """
    registry.register(Fcas4sIngestJob.JOB_TYPE, _fcas_4s_ingest_handler)
    logger.info("Registered FCAS 4s ingest job handler (type=%s)", Fcas4sIngestJob.JOB_TYPE)
