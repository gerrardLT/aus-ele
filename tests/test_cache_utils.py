"""Unit tests for cache_utils module.

Tests the standardized caching utilities, async job submission helpers,
and computation time attachment.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from cache_utils import (
    stable_cache_key,
    fetch_from_cache,
    store_in_cache,
    attach_computation_time,
    computation_timer,
    check_and_submit_if_slow,
    submit_as_job,
    cached_response,
)


class TestStableCacheKey:
    """Tests for stable_cache_key determinism."""

    def test_same_dict_produces_same_key(self):
        payload = {"year": 2024, "region": "NSW1", "month": "01"}
        assert stable_cache_key(payload) == stable_cache_key(payload)

    def test_key_order_independent(self):
        a = {"region": "NSW1", "year": 2024}
        b = {"year": 2024, "region": "NSW1"}
        assert stable_cache_key(a) == stable_cache_key(b)

    def test_different_values_produce_different_keys(self):
        a = {"year": 2024, "region": "NSW1"}
        b = {"year": 2024, "region": "QLD1"}
        assert stable_cache_key(a) != stable_cache_key(b)

    def test_returns_hex_string(self):
        key = stable_cache_key({"x": 1})
        assert len(key) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in key)

    def test_handles_none_values(self):
        payload = {"year": 2024, "month": None}
        key = stable_cache_key(payload)
        assert isinstance(key, str) and len(key) == 64


class TestAttachComputationTime:
    """Tests for attach_computation_time helper."""

    def test_adds_computation_time_ms_to_existing_metadata(self):
        start = time.perf_counter()
        time.sleep(0.01)  # ~10ms
        response = {"data": [1, 2, 3], "metadata": {"unit": "$/MWh"}}
        result = attach_computation_time(response, start)
        assert "computation_time_ms" in result["metadata"]
        assert result["metadata"]["computation_time_ms"] >= 5  # at least a few ms
        # Original metadata preserved
        assert result["metadata"]["unit"] == "$/MWh"

    def test_creates_metadata_if_missing(self):
        start = time.perf_counter()
        response = {"data": []}
        result = attach_computation_time(response, start)
        assert "metadata" in result
        assert "computation_time_ms" in result["metadata"]
        assert isinstance(result["metadata"]["computation_time_ms"], int)

    def test_computation_time_is_non_negative(self):
        start = time.perf_counter()
        response = {"metadata": {}}
        result = attach_computation_time(response, start)
        assert result["metadata"]["computation_time_ms"] >= 0


class TestComputationTimer:
    """Tests for computation_timer helper."""

    def test_returns_float(self):
        t = computation_timer()
        assert isinstance(t, float)

    def test_monotonically_increasing(self):
        t1 = computation_timer()
        t2 = computation_timer()
        assert t2 >= t1


class TestCheckAndSubmitIfSlow:
    """Tests for check_and_submit_if_slow procedural helper."""

    def test_fast_computation_returns_result_without_flag(self):
        def fast_fn():
            return {"result": 42}

        result = check_and_submit_if_slow(
            fast_fn,
            job_type="test_job",
            payload={"x": 1},
            threshold_seconds=10.0,
        )
        assert result == {"result": 42}
        assert "_slow_computation" not in result

    def test_slow_computation_flags_result(self):
        def slow_fn():
            time.sleep(0.05)
            return {"result": 99}

        result = check_and_submit_if_slow(
            slow_fn,
            job_type="test_job",
            payload={"x": 1},
            threshold_seconds=0.01,  # very low threshold
        )
        assert result["result"] == 99
        assert result["_slow_computation"] is True
        assert "_computation_time_seconds" in result


class TestCachedResponseDecorator:
    """Tests for the cached_response decorator."""

    def test_decorator_calls_function_when_no_cache_params(self):
        @cached_response("test_scope", ttl_seconds=60)
        def handler():
            return {"data": "fresh"}

        result = handler()
        assert result == {"data": "fresh"}

    def test_decorator_preserves_function_name(self):
        @cached_response("test_scope")
        def my_handler(*, cache_params=None):
            return {}

        assert my_handler.__name__ == "my_handler"
