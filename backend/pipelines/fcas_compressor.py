"""FCAS 4-second data compression pipeline.

Implements the FcasDataCompressor class that downsamples 4-second FCAS data
older than 90 days to 1-minute resolution. This reduces storage requirements
while preserving aggregate signal quality for historical analysis.

The compressor is registered as a daily job ("fcas_4s_compress") with the
JobOrchestrator framework.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from database import DatabaseManager
from job_framework import JobContext, JobRegistry

logger = logging.getLogger(__name__)

# Numeric columns eligible for averaging during downsampling.
# Non-numeric columns (timestamp, region_id) are handled separately.
_NUMERIC_COLUMNS = [
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


class FcasDataCompressor:
    """FCAS 4-second data compression strategy.

    Retention policy:
    - Records within the last 90 days: kept at original 4-second resolution.
    - Records older than 90 days: downsampled to 1-minute resolution by
      averaging all numeric columns within each (region_id, 1-minute window).
    """

    RETENTION_DAYS = 90
    TARGET_INTERVAL_SECONDS = 60

    def compress(self, db: DatabaseManager) -> dict:
        """Run the compression pass.

        Fetches all 4-second records older than the retention cutoff,
        downsamples them to 1-minute windows, and replaces the originals
        in the database.

        Args:
            db: DatabaseManager instance with fetch_fcas_4s_before() and
                replace_fcas_records() methods.

        Returns:
            Dict with compression statistics:
                - original_count: number of raw records processed
                - compressed_count: number of downsampled records written
                - compression_ratio: compressed / original (lower is better)
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.RETENTION_DAYS)
        old_records = db.fetch_fcas_4s_before(cutoff)

        if not old_records:
            logger.info("FcasDataCompressor: no records older than %s to compress", cutoff.isoformat())
            return {
                "original_count": 0,
                "compressed_count": 0,
                "compression_ratio": 0.0,
            }

        downsampled = self._downsample(old_records, self.TARGET_INTERVAL_SECONDS)
        db.replace_fcas_records(before=cutoff, new_records=downsampled)

        original_count = len(old_records)
        compressed_count = len(downsampled)
        compression_ratio = compressed_count / max(original_count, 1)

        logger.info(
            "FcasDataCompressor: compressed %d records -> %d (ratio=%.4f)",
            original_count,
            compressed_count,
            compression_ratio,
        )

        return {
            "original_count": original_count,
            "compressed_count": compressed_count,
            "compression_ratio": compression_ratio,
        }

    def _downsample(self, records: list[dict], target_seconds: int) -> list[dict]:
        """Downsample 4-second records by averaging within time windows.

        Groups records by (region_id, time_window) where each window spans
        `target_seconds` seconds. For each group, numeric columns are averaged
        and the window start timestamp is used as the representative timestamp.

        Args:
            records: List of record dicts with keys matching FCAS_4S_COLUMNS.
            target_seconds: Window size in seconds (default 60 for 1-minute).

        Returns:
            List of downsampled record dicts, one per (region_id, window).
        """
        if not records:
            return []

        # Group records by (region_id, window_start)
        groups: dict[tuple[str, str], list[dict]] = {}

        for record in records:
            region_id = record.get("region_id", "")
            timestamp_str = record.get("timestamp", "")

            window_start = self._compute_window_start(timestamp_str, target_seconds)
            key = (region_id, window_start)

            if key not in groups:
                groups[key] = []
            groups[key].append(record)

        # Average each group
        downsampled: list[dict] = []
        for (region_id, window_start), group_records in groups.items():
            averaged = self._average_group(region_id, window_start, group_records)
            downsampled.append(averaged)

        # Sort by timestamp, then region_id for deterministic output
        downsampled.sort(key=lambda r: (r.get("timestamp", ""), r.get("region_id", "")))
        return downsampled

    def _compute_window_start(self, timestamp_str: str, target_seconds: int) -> str:
        """Compute the window start timestamp for a given record timestamp.

        Truncates the timestamp to the nearest `target_seconds` boundary.

        Args:
            timestamp_str: ISO 8601 timestamp string.
            target_seconds: Window size in seconds.

        Returns:
            ISO 8601 string representing the window start.
        """
        try:
            # Handle various ISO formats
            ts = timestamp_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            # Fallback: return as-is if parsing fails
            return timestamp_str

        # Truncate to window boundary
        # Calculate seconds since midnight and floor to target_seconds
        total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        window_seconds = (total_seconds // target_seconds) * target_seconds

        window_dt = dt.replace(
            hour=window_seconds // 3600,
            minute=(window_seconds % 3600) // 60,
            second=window_seconds % 60,
            microsecond=0,
        )

        return window_dt.isoformat()

    def _average_group(
        self,
        region_id: str,
        window_start: str,
        records: list[dict],
    ) -> dict:
        """Average numeric columns for a group of records in the same window.

        Args:
            region_id: The region identifier for this group.
            window_start: The window start timestamp (used as output timestamp).
            records: List of records to average.

        Returns:
            A single dict with averaged numeric values and the window metadata.
        """
        result: dict[str, Any] = {
            "timestamp": window_start,
            "region_id": region_id,
        }

        for col in _NUMERIC_COLUMNS:
            values = []
            for record in records:
                val = record.get(col)
                if val is not None:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        pass

            if values:
                result[col] = sum(values) / len(values)
            else:
                result[col] = None

        return result


# ---------------------------------------------------------------------------
# Job handler and registration
# ---------------------------------------------------------------------------

# Job type identifier
FCAS_COMPRESS_JOB_TYPE = "fcas_4s_compress"


def _fcas_compress_handler(job: dict, context: JobContext) -> dict:
    """Job handler function compatible with JobRegistry.

    Entry point called by JobOrchestrator when the FCAS compression job
    is dequeued. Instantiates FcasDataCompressor and runs the compression.

    Args:
        job: Job record dict from the database.
        context: JobContext with db, job_id, and lake references.

    Returns:
        Dict with compression results.
    """
    db = context.db
    context.set_progress(10, "Starting FCAS 4s data compression")

    compressor = FcasDataCompressor()
    result = compressor.compress(db)

    context.set_progress(100, "FCAS 4s compression complete")
    return result


def register_fcas_compress_job(registry: JobRegistry) -> None:
    """Register the FCAS data compression job handler with the given JobRegistry.

    After registration, the job can be enqueued via:
        orchestrator.enqueue(
            "fcas_4s_compress",
            payload={},
            queue_name="data-pipeline",
            source_key="aemo",
        )

    Args:
        registry: The JobRegistry instance to register with.
    """
    registry.register(FCAS_COMPRESS_JOB_TYPE, _fcas_compress_handler)
    logger.info("Registered FCAS compress job handler (type=%s)", FCAS_COMPRESS_JOB_TYPE)


def enqueue_fcas_compress_job(*, manual: bool = False) -> dict:
    """Enqueue a FCAS compression job via the JobOrchestrator.

    Designed to be called by APScheduler cron (daily) or manually via
    the admin API. Avoids duplicate enqueues by checking for existing
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
        if job.get("job_type") == FCAS_COMPRESS_JOB_TYPE and job.get("source_key") == "aemo":
            logger.info(
                "FCAS compress job already queued (job_id=%s), skipping",
                job["job_id"],
            )
            return job

    job = orchestrator.enqueue(
        FCAS_COMPRESS_JOB_TYPE,
        payload={"manual": manual},
        queue_name="data-pipeline",
        source_key="aemo",
        priority=80 if manual else 100,  # Lower priority than ingest/sync jobs
        max_attempts=3,
    )
    logger.info("Enqueued FCAS compress job (job_id=%s, manual=%s)", job["job_id"], manual)
    return job
