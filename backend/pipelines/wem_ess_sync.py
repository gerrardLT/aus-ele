"""WEM ESS data incremental sync job.

Implements the WemEssSyncJob class that fetches WEM ESS market data
incrementally (since last sync timestamp), upserts into the database,
and updates the data_completeness status upon success.

The job integrates with the JobOrchestrator framework and can be triggered
via APScheduler cron or manually through the jobs API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

from database import DatabaseManager
from job_framework import JobContext, JobRegistry

logger = logging.getLogger(__name__)

# Default start date for initial sync when no previous sync exists
_DEFAULT_SYNC_START = "2020-01-01T00:00:00Z"

# System status keys
_LAST_SYNC_KEY = "wem_ess_last_sync"
_DATA_COMPLETENESS_KEY = "wem_ess_data_completeness"


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
    """Stub source client for development/testing.

    Raises NotImplementedError for actual HTTP calls. Replace with a real
    implementation that wraps the WEM data API (similar to aemo_wem_ess_scraper).
    """

    def fetch_ess_data(self, *, since: str) -> list[dict]:
        """Fetch ESS data from WEM source.

        In production, this would:
        1. Parse the `since` timestamp to determine the date range
        2. Download dispatch solution files (ZIP for historical, JSON for current)
        3. Extract slim market rows using extract_slim_solution_rows logic
        4. Return merged/deduplicated records

        Raises:
            NotImplementedError: Always, until real HTTP implementation is provided.
        """
        raise NotImplementedError(
            "WemEssSourceClientStub.fetch_ess_data is not implemented. "
            "Replace with a real WEM data API client for production use."
        )


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
                          uses WemEssSourceClientStub (development mode).
        """
        self.db = db
        self.source = source_client or WemEssSourceClientStub()

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
