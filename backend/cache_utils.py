"""
Standardized caching and async job submission utilities.

Provides a shared integration layer on top of RedisResponseCache and
JobOrchestrator for use across all route modules.

Components:
- cached_response: decorator that wraps route handlers with Redis caching
- async_if_slow: utility that measures computation time and submits to
  JobOrchestrator when the threshold is exceeded
- attach_computation_time: helper that adds computation_time_ms to response
  metadata
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache key generation
# ---------------------------------------------------------------------------


def stable_cache_key(payload: dict) -> str:
    """Generate a deterministic SHA-256 cache key from a dict of parameters."""
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# cached_response decorator
# ---------------------------------------------------------------------------


def cached_response(scope: str, ttl_seconds: int = 6 * 60 * 60):
    """Decorator that caches route handler responses in Redis.

    The decorated function must accept a keyword argument ``cache_params``
    (a dict describing the request parameters used as the cache key).
    If the result is already cached, the handler body is skipped and the
    cached value is returned directly.

    Usage::

        @router.get("/api/example")
        @cached_response("api_example_v1", ttl_seconds=3600)
        def get_example(*, cache_params: dict):
            # expensive computation
            return {"data": ...}

    Alternatively, the decorator can be used as a context-manager style
    utility via ``fetch_or_compute``.

    Parameters
    ----------
    scope : str
        Cache namespace/scope passed to RedisResponseCache.
    ttl_seconds : int
        Time-to-live for cached entries (default 6 hours).
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from deps import get_cache

            cache = get_cache()
            cache_params = kwargs.get("cache_params")

            # If no cache_params provided, skip caching and call directly
            if cache_params is None:
                return fn(*args, **kwargs)

            cache_key = stable_cache_key(cache_params)

            # Try cache hit
            cached = cache.get_json(scope, cache_key)
            if cached is not None:
                return cached

            # Cache miss — execute handler
            result = fn(*args, **kwargs)

            # Store result in cache
            if result is not None:
                cache.set_json(scope, cache_key, result, ttl_seconds)

            return result

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Procedural cache helpers (for routes that prefer explicit control)
# ---------------------------------------------------------------------------


def fetch_from_cache(scope: str, cache_params: dict) -> Any | None:
    """Attempt to retrieve a cached response.

    Returns the cached JSON value or None on miss/error.
    """
    from deps import get_cache

    cache = get_cache()
    cache_key = stable_cache_key(cache_params)
    return cache.get_json(scope, cache_key)


def store_in_cache(
    scope: str, cache_params: dict, response: dict, ttl_seconds: int = 6 * 60 * 60
) -> dict:
    """Store a response in the cache and return it (pass-through)."""
    from deps import get_cache

    cache = get_cache()
    cache_key = stable_cache_key(cache_params)
    cache.set_json(scope, cache_key, response, ttl_seconds)
    return response


# ---------------------------------------------------------------------------
# async_if_slow — computation timeout detection and job submission
# ---------------------------------------------------------------------------


def async_if_slow(
    job_type: str,
    *,
    threshold_seconds: float = 5.0,
    queue_name: str = "analysis",
    source_key: str = "api",
    payload_builder: Callable[..., dict] | None = None,
):
    """Decorator that submits long-running computations to JobOrchestrator.

    Measures the wall-clock time of the wrapped function. If execution
    exceeds ``threshold_seconds``, the result is still returned (since the
    computation already completed), but a warning is logged. For truly
    predictable async behavior, callers should use ``submit_if_slow``
    (the procedural helper) which estimates duration *before* running.

    This decorator is best used for functions where the computation time
    is unpredictable and we want to record when it exceeds the threshold.

    Parameters
    ----------
    job_type : str
        The job type identifier for JobOrchestrator.
    threshold_seconds : float
        Duration threshold in seconds (default 5.0).
    queue_name : str
        Queue name for submitted jobs.
    source_key : str
        Source key for rate limiting.
    payload_builder : callable, optional
        Function that builds the job payload from the decorated function's
        arguments. If None, the kwargs are used directly.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed = time.perf_counter() - start

            if elapsed > threshold_seconds:
                logger.warning(
                    "Computation for %s exceeded threshold: %.2fs > %.2fs",
                    job_type,
                    elapsed,
                    threshold_seconds,
                )

            return result

        return wrapper

    return decorator


def submit_as_job(
    job_type: str,
    payload: dict,
    *,
    queue_name: str = "analysis",
    source_key: str = "api",
    priority: int = 100,
) -> dict:
    """Submit a computation to JobOrchestrator and return the job envelope.

    Use this when you *know* (or estimate) that a computation will exceed
    the timeout threshold and want to return a job_id immediately.

    Returns
    -------
    dict
        Job record with at minimum ``job_id`` and ``status`` fields.
    """
    from deps import get_job_orchestrator

    orchestrator = get_job_orchestrator()
    job = orchestrator.enqueue(
        job_type,
        payload=payload,
        queue_name=queue_name,
        source_key=source_key,
        priority=priority,
    )
    return {
        "job_id": job["job_id"],
        "status": "queued",
        "message": "Computation submitted to background queue",
    }


def check_and_submit_if_slow(
    computation_fn: Callable,
    *,
    job_type: str,
    payload: dict,
    threshold_seconds: float = 5.0,
    queue_name: str = "analysis",
    source_key: str = "api",
) -> dict:
    """Run a computation; if it exceeds the threshold, also enqueue for async.

    This is the primary procedural helper for the "async if slow" pattern.
    It always returns the computed result (since we already paid the cost),
    but attaches a ``_slow_computation`` flag when the threshold is exceeded.

    For endpoints that want to *predict* slowness and return a job_id
    immediately (without running the computation), use ``submit_as_job``
    directly with an estimated duration check.

    Returns
    -------
    dict
        The computation result, with ``_slow_computation: True`` added
        if the threshold was exceeded.
    """
    start = time.perf_counter()
    result = computation_fn()
    elapsed = time.perf_counter() - start

    if elapsed > threshold_seconds:
        logger.info(
            "Computation %s took %.2fs (threshold %.2fs) — flagging as slow",
            job_type,
            elapsed,
            threshold_seconds,
        )
        if isinstance(result, dict):
            result["_slow_computation"] = True
            result["_computation_time_seconds"] = round(elapsed, 3)

    return result


# ---------------------------------------------------------------------------
# attach_computation_time — metadata enrichment
# ---------------------------------------------------------------------------


def attach_computation_time(response: dict, start_time: float) -> dict:
    """Add computation_time_ms to the response metadata.

    Parameters
    ----------
    response : dict
        The API response dict. Must contain (or will get) a ``metadata`` key.
    start_time : float
        The start time from ``time.perf_counter()`` or ``time.time()``.

    Returns
    -------
    dict
        The response with ``metadata.computation_time_ms`` populated.
    """
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    if "metadata" not in response:
        response["metadata"] = {}
    response["metadata"]["computation_time_ms"] = elapsed_ms
    return response


def computation_timer() -> float:
    """Return a high-resolution start time for use with attach_computation_time.

    Usage::

        start = computation_timer()
        # ... do work ...
        response = attach_computation_time(response, start)
    """
    return time.perf_counter()
