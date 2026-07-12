"""
Dependency injection module for the AEMO Intelligence platform.

Provides singleton factory functions for shared infrastructure (database,
cache, artifact lake, job orchestrator) and FastAPI Depends-compatible
async wrappers for use in route modules.
"""

from __future__ import annotations

import os
import datetime
from functools import lru_cache
from pathlib import Path

from database import DatabaseManager
from job_framework import JobOrchestrator, JobRegistry
from response_cache import RedisResponseCache
from storage_lake import LocalArtifactLake

# ---------------------------------------------------------------------------
# Path resolution (mirrors server.py conventions)
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


def _load_env_file() -> None:
    """Load .env file into os.environ (setdefault, no overwrite)."""
    candidates = [_REPO_ROOT / ".env", _BACKEND_DIR / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                os.environ.setdefault(key, value)
            return


_load_env_file()


# ---------------------------------------------------------------------------
# Shared utility functions
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format (e.g. '2026-07-11T12:00:00Z')."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Singleton factory functions
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_db() -> DatabaseManager:
    """Return the singleton DatabaseManager instance (PostgreSQL)."""
    return DatabaseManager()


@lru_cache(maxsize=1)
def get_cache() -> RedisResponseCache:
    """Return the singleton RedisResponseCache instance."""
    return RedisResponseCache()


@lru_cache(maxsize=1)
def get_lake() -> LocalArtifactLake:
    """Return the singleton LocalArtifactLake instance."""
    lake_root = Path(
        os.environ.get("AUS_ELE_LAKE_ROOT", str(_REPO_ROOT / "data_lake"))
    ).resolve()
    return LocalArtifactLake(str(lake_root))


@lru_cache(maxsize=1)
def get_job_registry() -> JobRegistry:
    """Return the singleton JobRegistry instance with all pipeline jobs registered."""
    registry = JobRegistry()

    # Register pipeline job handlers
    from pipelines.wem_ess_sync import register_wem_ess_job
    from pipelines.fcas_4s_ingest import register_fcas_4s_job

    register_wem_ess_job(registry)
    register_fcas_4s_job(registry)

    # Register core job handlers (market_sync, report_generate, fingrid)
    import server as _server

    registry.register(
        "market_sync",
        lambda job, context: _server.run_sync_scrapers(bool(job["payload_json"].get("manual"))),
    )
    registry.register(
        "report_generate",
        lambda job, context: _server.generate_report(
            report_type=job["payload_json"]["report_type"],
            year=int(job["payload_json"]["year"]),
            region=str(job["payload_json"]["region"]),
            month=job["payload_json"].get("month"),
            organization_id=job["payload_json"].get("organization_id"),
            workspace_id=job["payload_json"].get("workspace_id"),
        ),
    )
    registry.register(
        "fingrid_dataset_sync",
        lambda job, context: _server.run_fingrid_dataset_sync(
            job["payload_json"]["dataset_id"],
            str(job["payload_json"].get("mode", "incremental")),
        ),
    )
    registry.register(
        "fingrid_hourly_sync",
        lambda job, context: _server.run_fingrid_hourly_sync(),
    )
    registry.register(
        "fingrid_daily_sync",
        lambda job, context: _server.run_fingrid_daily_sync(),
    )

    return registry


@lru_cache(maxsize=1)
def get_job_orchestrator() -> JobOrchestrator:
    """Return the singleton JobOrchestrator instance."""
    return JobOrchestrator(
        get_db(),
        registry=get_job_registry(),
        lake=get_lake(),
        worker_id="api-worker-1",
        source_rate_limits={
            "aemo": 60,
            "fingrid": 10,
            "reporting": 1,
        },
    )


# ---------------------------------------------------------------------------
# FastAPI Depends injection functions
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_forward_price_engine():
    """Return the singleton ForwardPriceEngine instance (process-level cache).

    ML calibration runs once on first call (~16s); all subsequent calls
    return the same instance instantly. The engine is effectively read-only
    after initialization, so sharing across requests is safe.
    """
    from engines.forward_price_engine import ForwardPriceEngine

    return ForwardPriceEngine()


async def db_dependency() -> DatabaseManager:
    """FastAPI dependency that yields the shared DatabaseManager."""
    return get_db()


async def cache_dependency() -> RedisResponseCache:
    """FastAPI dependency that yields the shared RedisResponseCache."""
    return get_cache()
