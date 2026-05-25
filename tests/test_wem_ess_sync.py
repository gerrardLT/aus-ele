"""Unit tests for WemEssSyncJob pipeline.

Tests the incremental sync logic, failure handling, data_completeness
status updates, and job registration.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pipelines.wem_ess_sync import (
    WemEssSyncJob,
    WemEssSourceClientStub,
    register_wem_ess_job,
    _wem_ess_sync_handler,
    _LAST_SYNC_KEY,
    _DATA_COMPLETENESS_KEY,
    _DEFAULT_SYNC_START,
)
from job_framework import JobContext, JobRegistry


class FakeSourceClient:
    """Fake source client that returns configurable records."""

    def __init__(self, records: list[dict] | None = None, error: Exception | None = None):
        self.records = records or []
        self.error = error
        self.calls: list[dict] = []

    def fetch_ess_data(self, *, since: str) -> list[dict]:
        self.calls.append({"since": since})
        if self.error:
            raise self.error
        return self.records


class FakeDB:
    """Minimal fake DatabaseManager for testing sync logic."""

    def __init__(self):
        self._system_status: dict[str, str] = {}
        self._upserted_records: list[dict] = []
        self._progress_updates: list[tuple[str, int, str]] = []
        self._job_events: list[dict] = []

    def get_system_status(self, key: str, default=None, *, parse_json: bool = False):
        return self._system_status.get(key, default)

    def set_system_status(self, key: str, value):
        self._system_status[key] = value

    def batch_upsert_wem_ess_market(self, records: list[dict]) -> int:
        self._upserted_records.extend(records)
        return len(records)

    def update_job_progress(self, job_id: str, progress_pct: int, progress_message: str):
        self._progress_updates.append((job_id, progress_pct, progress_message))

    def append_job_event(self, job_id: str, event_type: str, detail: dict, created_at: str):
        self._job_events.append({
            "job_id": job_id,
            "event_type": event_type,
            "detail": detail,
            "created_at": created_at,
        })

    def fetch_job(self, job_id: str) -> dict | None:
        return {"job_id": job_id, "cancel_requested": 0}


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def fake_context(fake_db):
    return JobContext(db=fake_db, job_id="test-job-001", lake=None)


@pytest.fixture
def sample_records():
    return [
        {
            "dispatch_interval": "2024-01-15 08:00:00",
            "energy_price": 45.50,
            "regulation_raise_price": 12.0,
            "regulation_lower_price": 8.0,
            "contingency_raise_price": 15.0,
            "contingency_lower_price": 10.0,
            "rocof_price": 5.0,
        },
        {
            "dispatch_interval": "2024-01-15 08:05:00",
            "energy_price": 47.20,
            "regulation_raise_price": 11.5,
            "regulation_lower_price": 7.5,
            "contingency_raise_price": 14.0,
            "contingency_lower_price": 9.5,
            "rocof_price": 4.8,
        },
    ]


class TestWemEssSyncJobRun:
    """Tests for WemEssSyncJob.run() method."""

    def test_successful_sync_first_time(self, fake_db, fake_context, sample_records):
        """First sync uses default start date and marks completeness."""
        source = FakeSourceClient(records=sample_records)
        job = WemEssSyncJob(db=fake_db, source_client=source)

        result = job.run(fake_context)

        # Verify source was called with default start
        assert len(source.calls) == 1
        assert source.calls[0]["since"] == _DEFAULT_SYNC_START

        # Verify records were upserted
        assert result["records_synced"] == 2
        assert "sync_timestamp" in result
        assert fake_db._upserted_records == sample_records

        # Verify system status updated
        assert fake_db.get_system_status(_LAST_SYNC_KEY) == result["sync_timestamp"]
        assert fake_db.get_system_status(_DATA_COMPLETENESS_KEY) == "complete"

    def test_incremental_sync_uses_last_timestamp(self, fake_db, fake_context, sample_records):
        """Subsequent syncs use the stored last_sync timestamp."""
        last_sync = "2024-01-14T00:00:00Z"
        fake_db.set_system_status(_LAST_SYNC_KEY, last_sync)

        source = FakeSourceClient(records=sample_records)
        job = WemEssSyncJob(db=fake_db, source_client=source)

        job.run(fake_context)

        assert source.calls[0]["since"] == last_sync

    def test_sync_with_empty_records(self, fake_db, fake_context):
        """Sync with no new records still updates timestamp and completeness."""
        source = FakeSourceClient(records=[])
        job = WemEssSyncJob(db=fake_db, source_client=source)

        result = job.run(fake_context)

        assert result["records_synced"] == 0
        assert fake_db.get_system_status(_DATA_COMPLETENESS_KEY) == "complete"
        assert fake_db.get_system_status(_LAST_SYNC_KEY) is not None

    def test_fetch_failure_preserves_old_data(self, fake_db, fake_context):
        """When fetch fails, existing data is preserved and error propagates."""
        fake_db.set_system_status(_LAST_SYNC_KEY, "2024-01-10T00:00:00Z")
        fake_db.set_system_status(_DATA_COMPLETENESS_KEY, "preview")

        source = FakeSourceClient(error=ConnectionError("WEM source unavailable"))
        job = WemEssSyncJob(db=fake_db, source_client=source)

        with pytest.raises(ConnectionError, match="WEM source unavailable"):
            job.run(fake_context)

        # Old data preserved — status not changed
        assert fake_db.get_system_status(_LAST_SYNC_KEY) == "2024-01-10T00:00:00Z"
        assert fake_db.get_system_status(_DATA_COMPLETENESS_KEY) == "preview"
        assert fake_db._upserted_records == []

    def test_upsert_failure_preserves_old_timestamp(self, fake_db, fake_context, sample_records):
        """When upsert fails, sync timestamp is not updated."""
        fake_db.set_system_status(_LAST_SYNC_KEY, "2024-01-10T00:00:00Z")

        # Make batch_upsert raise
        fake_db.batch_upsert_wem_ess_market = MagicMock(
            side_effect=RuntimeError("DB write failed")
        )

        source = FakeSourceClient(records=sample_records)
        job = WemEssSyncJob(db=fake_db, source_client=source)

        with pytest.raises(RuntimeError, match="DB write failed"):
            job.run(fake_context)

        # Timestamp not updated
        assert fake_db.get_system_status(_LAST_SYNC_KEY) == "2024-01-10T00:00:00Z"

    def test_progress_reporting(self, fake_db, fake_context, sample_records):
        """Job reports progress at key stages."""
        source = FakeSourceClient(records=sample_records)
        job = WemEssSyncJob(db=fake_db, source_client=source)

        job.run(fake_context)

        # Check progress was reported (via job events)
        progress_events = [
            e for e in fake_db._job_events if e["event_type"] == "progress"
        ]
        assert len(progress_events) >= 3  # 10%, 50%, 100%

        pcts = [e["detail"]["progress_pct"] for e in progress_events]
        assert 10 in pcts
        assert 50 in pcts
        assert 100 in pcts

    def test_cancellation_before_upsert(self, fake_db, fake_context, sample_records):
        """If cancellation is requested, job stops before upsert."""
        # Override fetch_job to return cancel_requested=1
        fake_db.fetch_job = lambda job_id: {"job_id": job_id, "cancel_requested": 1}

        source = FakeSourceClient(records=sample_records)
        job = WemEssSyncJob(db=fake_db, source_client=source)

        result = job.run(fake_context)

        assert result["cancelled"] is True
        assert result["records_synced"] == 0
        assert fake_db._upserted_records == []


class TestWemEssSyncJobInit:
    """Tests for WemEssSyncJob initialization."""

    def test_default_source_client_is_stub(self, fake_db):
        """Without explicit source_client, uses the stub."""
        job = WemEssSyncJob(db=fake_db)
        assert isinstance(job.source, WemEssSourceClientStub)

    def test_custom_source_client(self, fake_db):
        """Custom source client is used when provided."""
        source = FakeSourceClient()
        job = WemEssSyncJob(db=fake_db, source_client=source)
        assert job.source is source


class TestWemEssSourceClientStub:
    """Tests for the stub source client."""

    def test_stub_raises_not_implemented(self):
        """Stub always raises NotImplementedError."""
        stub = WemEssSourceClientStub()
        with pytest.raises(NotImplementedError):
            stub.fetch_ess_data(since="2024-01-01T00:00:00Z")


class TestJobRegistration:
    """Tests for job registration with JobRegistry."""

    def test_register_wem_ess_job(self):
        """register_wem_ess_job adds the handler to the registry."""
        registry = JobRegistry()
        register_wem_ess_job(registry)

        handler = registry.get(WemEssSyncJob.JOB_TYPE)
        assert handler is _wem_ess_sync_handler

    def test_handler_invokes_sync_job(self, fake_db, fake_context):
        """The registered handler creates and runs WemEssSyncJob."""
        job_record = {
            "job_id": "test-job-001",
            "job_type": "wem_ess_sync",
            "payload_json": {},
        }

        # The handler will use the stub which raises NotImplementedError
        with pytest.raises(NotImplementedError):
            _wem_ess_sync_handler(job_record, fake_context)

    def test_registered_job_type_constant(self):
        """Job type constant matches expected value."""
        assert WemEssSyncJob.JOB_TYPE == "wem_ess_sync"
