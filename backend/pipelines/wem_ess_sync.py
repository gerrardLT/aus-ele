"""WEM ESS data incremental sync job.

Implements the WemEssSyncJob class that fetches WEM ESS market data
incrementally (since last sync timestamp), upserts into the database,
and updates the data_completeness status upon success.

The job integrates with the JobOrchestrator framework and can be triggered
via APScheduler cron or manually through the jobs API.
"""

from __future__ import annotations

import io
import logging
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from database import DatabaseManager
from job_framework import JobContext, JobRegistry

logger = logging.getLogger(__name__)

# Default start date for initial sync when no previous sync exists
_DEFAULT_SYNC_START = "2020-01-01T00:00:00Z"

# Maximum days to fetch in a single sync to avoid timeout
_MAX_SYNC_DAYS = 90

# System status keys
_LAST_SYNC_KEY = "wem_ess_last_sync"
_DATA_COMPLETENESS_KEY = "wem_ess_data_completeness"

# Add scrapers directory to path for importing aemo_wem_ess_scraper
_SCRAPERS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scrapers")
if _SCRAPERS_DIR not in sys.path:
    sys.path.insert(0, _SCRAPERS_DIR)

from aemo_wem_ess_scraper import (  # noqa: E402
    WEM_BASE,
    download_bytes,
    extract_slim_solution_rows,
    list_current_json_urls,
)


class WemEssSourceClient(Protocol):
    """Protocol for WEM ESS data source clients.

    Implementations should fetch ESS market data from the WEM data source
    (e.g., AEMO WEM dispatch solution files) and return records suitable
    for batch_upsert_wem_ess_market.
    """

    def fetch_ess_data(self, *, since: str) -> list[dict]:
        """Fetch ESS market records since the given ISO timestamp.

        Args:
            since: ISO 8601 timestamp string. Only records after this
                   timestamp should be returned.

        Returns:
            List of dicts with keys matching DatabaseManager.WEM_ESS_MARKET_COLUMNS.
        """
        ...


class WemEssSourceClientStub:
    """Stub source client for offline development/testing.

    Returns an empty list instead of making HTTP calls.
    Use WemEssAemoClient for production.
    """

    def fetch_ess_data(self, *, since: str) -> list[dict]:
        logger.warning("WemEssSourceClientStub used — returning empty dataset")
        return []


class WemEssAemoClient:
    """Production WEM ESS data client.

    Fetches dispatch solution files from AEMO's public WEM data portal,
    extracts slim market rows, and returns them for batch upsert.

    Reuses download/parse logic from scrapers/aemo_wem_ess_scraper.py.
    """

    def fetch_ess_data(self, *, since: str) -> list[dict]:
        """Fetch ESS market records since the given ISO timestamp.

        Iterates day-by-day from `since` to yesterday (AWST), downloading
        dispatch solution ZIP/JSON files and extracting slim market rows.

        Args:
            since: ISO 8601 timestamp string.

        Returns:
            Deduplicated list of market row dicts ordered by dispatch_interval.
        """
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        # AWST = UTC+8; use yesterday in AWST as the end date
        awst_now = datetime.now(timezone.utc) + timedelta(hours=8)
        end_dt = (awst_now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = since_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        # Cap to _MAX_SYNC_DAYS to avoid unbounded fetches
        max_start = end_dt - timedelta(days=_MAX_SYNC_DAYS)
        if start_dt < max_start:
            logger.warning(
                "Sync window capped from %s to %s (%d days max)",
                start_dt.strftime("%Y-%m-%d"),
                max_start.strftime("%Y-%m-%d"),
                _MAX_SYNC_DAYS,
            )
            start_dt = max_start

        all_market_rows: dict[str, dict] = {}  # keyed by dispatch_interval for dedup
        current = start_dt
        day_count = 0

        while current <= end_dt:
            day_count += 1
            date_label = current.strftime("%Y-%m-%d")
            date_compact = current.strftime("%Y%m%d")

            day_rows = self._fetch_day_rows(current, date_label, date_compact)
            for row in day_rows:
                interval = row.get("dispatch_interval")
                if interval:
                    all_market_rows[interval] = row

            if day_count % 10 == 0:
                logger.info("WEM ESS fetch progress: %d days processed, latest=%s", day_count, date_label)

            current += timedelta(days=1)
            time.sleep(0.5)  # Rate limit politeness

        result = sorted(all_market_rows.values(), key=lambda r: r.get("dispatch_interval", ""))
        logger.info(
            "WEM ESS fetch complete: %d days scanned, %d unique market rows",
            day_count,
            len(result),
        )
        return result

    @staticmethod
    def _fetch_day_rows(target_date: datetime, date_label: str, date_compact: str) -> list[dict]:
        """Download and extract market rows for a single day (no DB write)."""
        market_rows: list[dict] = []

        # Try historical ZIP first
        zip_url = f"{WEM_BASE}/previous/DispatchSolutionReference_{date_compact}.zip"
        raw_zip = download_bytes(zip_url, date_label, stream=True, max_retries=2)
        if raw_zip:
            try:
                with zipfile.ZipFile(io.BytesIO(raw_zip)) as zipped:
                    for name in sorted(n for n in zipped.namelist() if n.endswith(".json")):
                        with zipped.open(name) as handle:
                            rows, _ = extract_slim_solution_rows(handle.read())
                            market_rows.extend(rows)
            except zipfile.BadZipFile:
                logger.warning("%s: bad zip file, trying current JSON listing", date_label)
                raw_zip = None

        # Fallback to current JSON listing (for today / recent days)
        if not raw_zip:
            for url in list_current_json_urls(target_date):
                raw_json = download_bytes(url, url.rsplit("/", 1)[-1], stream=False, max_retries=1)
                if not raw_json:
                    continue
                rows, _ = extract_slim_solution_rows(raw_json)
                market_rows.extend(rows)

        return market_rows


class WemEssSyncJob:
    """WEM ESS data incremental sync job.

    Fetches ESS market data from the WEM data source since the last
    successful sync, upserts records into the database, and updates
    the data_completeness status to "complete" on success.

    On failure, the job logs the error details, preserves existing data,
    and relies on the JobOrchestrator retry mechanism for the next attempt.
    """

    # Job type identifier for registration with JobRegistry
    JOB_TYPE = "wem_ess_sync"

    # Default cron schedule: daily at 06:00 UTC (14:00 AWST)
    DEFAULT_CRON_HOUR = 6
    DEFAULT_CRON_MINUTE = 0

    def __init__(self, db: DatabaseManager, source_client: WemEssSourceClient | None = None):
        """Initialize the sync job.

        Args:
            db: DatabaseManager instance for data persistence.
            source_client: Client for fetching WEM ESS data. If None,
                          uses WemEssAemoClient (production mode).
                          Pass WemEssSourceClientStub() for offline dev.
        """
        self.db = db
        self.source = source_client or WemEssAemoClient()

    def run(self, context: JobContext) -> dict:
        """Execute the WEM ESS incremental sync.

        Steps:
        1. Retrieve last_sync_timestamp from system_status
        2. Fetch incremental ESS data since last sync
        3. Upsert records into the database
        4. Update last_sync_timestamp
        5. Set data_completeness to "complete"

        Args:
            context: JobContext providing progress reporting and cancellation.

        Returns:
            Dict with sync results including records_synced and sync_timestamp.

        Raises:
            Exception: Propagated from source client or database operations.
                      The JobOrchestrator handles retry logic.
        """
        # Step 1: Get last sync timestamp
        last_sync = self.db.get_system_status(_LAST_SYNC_KEY)
        since = last_sync or _DEFAULT_SYNC_START

        context.set_progress(10, f"Fetching ESS data since {since}")
        logger.info("WEM ESS sync starting, fetching data since %s", since)

        # Step 2: Fetch incremental data
        try:
            records = self.source.fetch_ess_data(since=since)
        except Exception as exc:
            logger.error(
                "WEM ESS sync failed during data fetch: %s",
                exc,
                exc_info=True,
            )
            # Re-raise to let JobOrchestrator handle retry
            raise

        # Check for cancellation before proceeding with upsert
        if context.is_cancel_requested():
            logger.info("WEM ESS sync cancelled before upsert")
            return {"records_synced": 0, "cancelled": True}

        # Step 3: Upsert records
        context.set_progress(50, f"Upserting {len(records)} ESS records")
        logger.info("Upserting %d ESS market records", len(records))

        try:
            upserted_count = self.db.batch_upsert_wem_ess_market(records)
        except Exception as exc:
            logger.error(
                "WEM ESS sync failed during upsert: %s",
                exc,
                exc_info=True,
            )
            # Re-raise — existing data is preserved since upsert is atomic per batch
            raise

        # Step 4: Update sync timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        self.db.set_system_status(_LAST_SYNC_KEY, now_iso)

        # Step 5: Mark data as complete
        self.db.set_system_status(_DATA_COMPLETENESS_KEY, "complete")

        context.set_progress(100, "ESS sync complete")
        logger.info(
            "WEM ESS sync complete: %d records synced at %s",
            upserted_count,
            now_iso,
        )

        return {
            "records_synced": upserted_count,
            "sync_timestamp": now_iso,
        }


def _wem_ess_sync_handler(job: dict, context: JobContext) -> dict:
    """Job handler function compatible with JobRegistry.

    This is the entry point called by JobOrchestrator when the job is
    dequeued. It instantiates WemEssSyncJob with the context's database
    and runs the sync.

    Args:
        job: Job record dict from the database.
        context: JobContext with db, job_id, and lake references.

    Returns:
        Dict with sync results.
    """
    db = context.db
    # Allow payload to specify a custom source client class in the future
    sync_job = WemEssSyncJob(db=db)
    return sync_job.run(context)


def register_wem_ess_job(registry: JobRegistry) -> None:
    """Register the WEM ESS sync job handler with the given JobRegistry.

    After registration, the job can be enqueued via:
        orchestrator.enqueue(
            "wem_ess_sync",
            payload={},
            queue_name="data-pipeline",
            source_key="aemo",
        )

    Args:
        registry: The JobRegistry instance to register with.
    """
    registry.register(WemEssSyncJob.JOB_TYPE, _wem_ess_sync_handler)
    logger.info("Registered WEM ESS sync job handler (type=%s)", WemEssSyncJob.JOB_TYPE)


def enqueue_wem_ess_sync_job(*, manual: bool = False) -> dict:
    """Enqueue a WEM ESS sync job via the JobOrchestrator.

    This function is designed to be called by APScheduler cron or manually
    via the admin API. It avoids duplicate enqueues by checking for existing
    open jobs of the same type.

    Args:
        manual: Whether this is a manual trigger (affects priority).

    Returns:
        The job record dict (existing or newly created).
    """
    from deps import get_job_orchestrator

    orchestrator = get_job_orchestrator()

    # Check for existing open job to avoid duplicates
    existing_jobs = orchestrator.db.list_jobs(status="queued", limit=100)
    for job in existing_jobs:
        if job.get("job_type") == WemEssSyncJob.JOB_TYPE and job.get("source_key") == "aemo":
            logger.info("WEM ESS sync job already queued (job_id=%s), skipping", job["job_id"])
            return job

    job = orchestrator.enqueue(
        WemEssSyncJob.JOB_TYPE,
        payload={"manual": manual},
        queue_name="data-pipeline",
        source_key="aemo",
        priority=40 if manual else 60,
        max_attempts=3,
    )
    logger.info("Enqueued WEM ESS sync job (job_id=%s, manual=%s)", job["job_id"], manual)
    return job
