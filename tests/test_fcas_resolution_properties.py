"""Property-based tests for FCAS data resolution fallback and compression.

Feature: platform-optimization, Property 8: 数据分辨率回退正确性
Feature: platform-optimization, Property 9: 数据压缩保留策略

Uses Hypothesis to verify:
- Property 8: Resolution fallback logic correctly falls back from 4s to 5min
  when data is unavailable, and metadata reflects actual resolution.
- Property 9: Compression retains 4s data within 90 days, downsamples to 1min
  beyond 90 days, with approximately 1/15 compression ratio.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from pipelines.fcas_4s_ingest import resolve_fcas_resolution, FCAS_4S_TABLE
from pipelines.fcas_compressor import FcasDataCompressor


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

nem_regions = st.sampled_from(["NSW1", "QLD1", "VIC1", "SA1", "TAS1"])
valid_years = st.integers(min_value=2020, max_value=2030)
resolution_requests = st.sampled_from(["auto", "4s", "5min"])
data_availability = st.booleans()


def make_4s_records_for_minute(region: str, minute_start: datetime, count: int) -> list[dict]:
    """Generate 4-second interval FCAS records within a single minute.

    Args:
        region: NEM region ID.
        minute_start: Start of the minute (second=0).
        count: Number of records (max 15 for 4s intervals in 60s).
    """
    records = []
    for i in range(count):
        ts = minute_start + timedelta(seconds=i * 4)
        records.append({
            "timestamp": ts.isoformat(),
            "region_id": region,
            "raise6sec_price": 10.0 + i * 0.5,
            "raise60sec_price": 20.0 + i * 0.3,
            "raise5min_price": 30.0,
            "raisereg_price": 5.0,
            "raise1sec_price": 15.0,
            "lower6sec_price": 8.0,
            "lower60sec_price": 12.0,
            "lower5min_price": 6.0,
            "lowerreg_price": 4.0,
            "lower1sec_price": 7.0,
            "total_demand_mw": 5000.0 + i * 10,
            "frequency_hz": 50.0,
        })
    return records


# ---------------------------------------------------------------------------
# Property 8: 数据分辨率回退正确性
# ---------------------------------------------------------------------------


class TestProperty8ResolutionFallback:
    """Property 8: 数据分辨率回退正确性

    For any FCAS analysis request, when 4-second data is unavailable,
    the system should fall back to 5-minute resolution, and the response
    metadata.interval_seconds should reflect the actual resolution used
    (not the requested resolution).

    **Validates: Requirements 8.3, 8.4**
    """

    @given(
        region=nem_regions,
        year=valid_years,
        requested_resolution=resolution_requests,
        has_4s_data=data_availability,
    )
    @settings(max_examples=200)
    def test_resolution_fallback_metadata_reflects_actual(
        self, region, year, requested_resolution, has_4s_data
    ):
        """Resolution metadata always reflects actual data used, not requested.

        Feature: platform-optimization, Property 8: 数据分辨率回退正确性
        **Validates: Requirements 8.3, 8.4**
        """
        # Mock the database to control data availability
        mock_db = MagicMock()

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.get_connection.return_value = mock_conn

        if has_4s_data:
            # Table exists and has data for this region/year
            mock_cursor.fetchone.side_effect = [(1,), (1,)]
        else:
            # Table exists but no data for this region/year
            mock_cursor.fetchone.side_effect = [(1,), None]

        result = resolve_fcas_resolution(
            mock_db,
            region=region,
            year=year,
            requested_resolution=requested_resolution,
        )

        # Core property assertions
        assert "resolution_seconds" in result
        assert "source" in result
        assert "fallback_used" in result

        if requested_resolution == "5min":
            # Explicit 5min request always returns 5min
            assert result["resolution_seconds"] == 300
            assert result["fallback_used"] is False
            assert result["source"] == f"trading_price_{year}"
        elif has_4s_data:
            # 4s data available -> use 4s resolution
            assert result["resolution_seconds"] == 4
            assert result["source"] == FCAS_4S_TABLE
            assert result["fallback_used"] is False
        else:
            # 4s data NOT available -> fallback to 5min
            assert result["resolution_seconds"] == 300
            assert result["source"] == f"trading_price_{year}"
            assert result["fallback_used"] is True

    @given(
        region=nem_regions,
        year=valid_years,
    )
    @settings(max_examples=200)
    def test_resolution_never_returns_invalid_seconds(self, region, year):
        """Resolution seconds is always either 4 or 300, never anything else.

        Feature: platform-optimization, Property 8: 数据分辨率回退正确性
        **Validates: Requirements 8.3, 8.4**
        """
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.get_connection.return_value = mock_conn

        # Simulate no data available (fallback case)
        mock_cursor.fetchone.side_effect = [(1,), None]

        for req_res in ["auto", "4s", "5min"]:
            mock_cursor.fetchone.side_effect = [(1,), None]

            result = resolve_fcas_resolution(
                mock_db,
                region=region,
                year=year,
                requested_resolution=req_res,
            )

            # Resolution must be one of the two valid values
            assert result["resolution_seconds"] in (4, 300), (
                f"Invalid resolution_seconds={result['resolution_seconds']} "
                f"for requested={req_res}"
            )

    @given(
        region=nem_regions,
        year=valid_years,
    )
    @settings(max_examples=200)
    def test_table_not_exists_triggers_fallback(self, region, year):
        """When the fcas_4s_data table doesn't exist, fallback is always used.

        Feature: platform-optimization, Property 8: 数据分辨率回退正确性
        **Validates: Requirements 8.3, 8.4**
        """
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.get_connection.return_value = mock_conn

        # Table does not exist
        mock_cursor.fetchone.return_value = None

        result = resolve_fcas_resolution(
            mock_db,
            region=region,
            year=year,
            requested_resolution="auto",
        )

        # Must fallback since table doesn't exist
        assert result["resolution_seconds"] == 300
        assert result["fallback_used"] is True
        assert result["source"] == f"trading_price_{year}"


# ---------------------------------------------------------------------------
# Property 9: 数据压缩保留策略
# ---------------------------------------------------------------------------


class TestProperty9CompressionRetention:
    """Property 9: 数据压缩保留策略

    For any 4-second FCAS dataset, after compression:
    (a) Data within 90 days retains 4-second resolution (unchanged).
    (b) Data older than 90 days is downsampled to 1-minute resolution.
    (c) The downsampled data point count is approximately 1/15 of original.

    **Validates: Requirements 8.5**
    """

    @given(
        region=nem_regions,
        num_minutes=st.integers(min_value=1, max_value=10),
        records_per_minute=st.integers(min_value=10, max_value=15),
    )
    @settings(max_examples=200)
    def test_compression_ratio_approximately_1_over_15(
        self, region, num_minutes, records_per_minute
    ):
        """Downsampled records per minute ≈ 1/15 of original 4s records.

        Feature: platform-optimization, Property 9: 数据压缩保留策略
        **Validates: Requirements 8.5**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = []
        for minute_idx in range(num_minutes):
            minute_start = base_time + timedelta(minutes=minute_idx)
            records.extend(
                make_4s_records_for_minute(region, minute_start, records_per_minute)
            )

        compressor = FcasDataCompressor()
        downsampled = compressor._downsample(records, compressor.TARGET_INTERVAL_SECONDS)

        # Each minute should compress to exactly 1 record (same region, same window)
        assert len(downsampled) == num_minutes

        # Compression ratio should be approximately 1/records_per_minute
        ratio = len(downsampled) / len(records)
        expected_ratio = 1.0 / records_per_minute
        assert ratio == pytest.approx(expected_ratio, rel=0.01), (
            f"Compression ratio {ratio} not close to expected {expected_ratio}"
        )

    @given(
        region=nem_regions,
        num_minutes=st.integers(min_value=1, max_value=10),
        records_per_minute=st.integers(min_value=10, max_value=15),
    )
    @settings(max_examples=200)
    def test_compression_preserves_region_grouping(
        self, region, num_minutes, records_per_minute
    ):
        """Compression groups by region — records from same region stay together.

        Feature: platform-optimization, Property 9: 数据压缩保留策略
        **Validates: Requirements 8.5**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = []
        for minute_idx in range(num_minutes):
            minute_start = base_time + timedelta(minutes=minute_idx)
            records.extend(
                make_4s_records_for_minute(region, minute_start, records_per_minute)
            )

        compressor = FcasDataCompressor()
        downsampled = compressor._downsample(records, compressor.TARGET_INTERVAL_SECONDS)

        # All downsampled records should have the same region as input
        for rec in downsampled:
            assert rec["region_id"] == region

    @given(
        region=nem_regions,
        num_minutes=st.integers(min_value=2, max_value=8),
        records_per_minute=st.integers(min_value=10, max_value=15),
    )
    @settings(max_examples=200)
    def test_recent_data_preserved_old_data_compressed(
        self, region, num_minutes, records_per_minute
    ):
        """90-day retention: recent data untouched, old data compressed.

        Feature: platform-optimization, Property 9: 数据压缩保留策略
        **Validates: Requirements 8.5**

        Simulates the full compress() workflow with a mock DB that has
        old (beyond 90 days) data. Verifies that old data is compressed
        to approximately 1/15 of original.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=FcasDataCompressor.RETENTION_DAYS)

        # Generate old records (beyond 90 days), aligned to minute boundaries
        old_base = cutoff - timedelta(hours=1)
        # Align to minute boundary
        old_base = old_base.replace(second=0, microsecond=0)

        old_records = []
        for minute_idx in range(num_minutes):
            minute_start = old_base + timedelta(minutes=minute_idx)
            old_records.extend(
                make_4s_records_for_minute(region, minute_start, records_per_minute)
            )

        # Track what gets replaced
        replaced_records = []

        class MockDB:
            def fetch_fcas_4s_before(self, cutoff_dt):
                return old_records

            def replace_fcas_records(self, before, new_records):
                replaced_records.extend(new_records)

        compressor = FcasDataCompressor()
        result = compressor.compress(MockDB())

        # Old data was compressed
        assert result["original_count"] == len(old_records)
        assert result["compressed_count"] == len(replaced_records)

        # Compressed count should be 1 record per minute
        expected_compressed = num_minutes
        assert result["compressed_count"] == expected_compressed

        # Compression ratio ≈ 1/records_per_minute
        expected_ratio = expected_compressed / len(old_records)
        assert result["compression_ratio"] == pytest.approx(expected_ratio, rel=0.01)

    @given(
        region=nem_regions,
        num_minutes=st.integers(min_value=1, max_value=5),
        records_per_minute=st.integers(min_value=10, max_value=15),
    )
    @settings(max_examples=200)
    def test_downsampled_values_are_averages(
        self, region, num_minutes, records_per_minute
    ):
        """Downsampled numeric values are averages of the original window records.

        Feature: platform-optimization, Property 9: 数据压缩保留策略
        **Validates: Requirements 8.5**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = []
        for minute_idx in range(num_minutes):
            minute_start = base_time + timedelta(minutes=minute_idx)
            records.extend(
                make_4s_records_for_minute(region, minute_start, records_per_minute)
            )

        compressor = FcasDataCompressor()
        downsampled = compressor._downsample(records, compressor.TARGET_INTERVAL_SECONDS)

        # Group original records by window
        from collections import defaultdict
        windows = defaultdict(list)
        for rec in records:
            window_start = compressor._compute_window_start(
                rec["timestamp"], compressor.TARGET_INTERVAL_SECONDS
            )
            windows[(rec["region_id"], window_start)].append(rec)

        for ds_rec in downsampled:
            key = (ds_rec["region_id"], ds_rec["timestamp"])
            assert key in windows, f"Downsampled record key {key} not found in windows"
            window_records = windows[key]

            # Verify raise6sec_price is the average of window records
            original_values = [
                r["raise6sec_price"] for r in window_records
                if r.get("raise6sec_price") is not None
            ]
            if original_values:
                expected_avg = sum(original_values) / len(original_values)
                assert ds_rec["raise6sec_price"] == pytest.approx(expected_avg, rel=1e-6), (
                    f"raise6sec_price mismatch: got {ds_rec['raise6sec_price']}, "
                    f"expected {expected_avg}"
                )

    @given(
        region=nem_regions,
        num_minutes=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_no_data_loss_for_recent_records(self, region, num_minutes):
        """Records within 90 days are never fetched for compression.

        Feature: platform-optimization, Property 9: 数据压缩保留策略
        **Validates: Requirements 8.5**

        The compressor only processes records older than RETENTION_DAYS.
        Recent records should remain untouched.
        """
        now = datetime.now(timezone.utc)

        fetch_called_with = []

        class MockDB:
            def fetch_fcas_4s_before(self, cutoff_dt):
                fetch_called_with.append(cutoff_dt)
                # Return empty — simulating no old data (all data is recent)
                return []

            def replace_fcas_records(self, before, new_records):
                pass

        compressor = FcasDataCompressor()
        result = compressor.compress(MockDB())

        # The cutoff should be 90 days ago
        assert len(fetch_called_with) == 1
        expected_cutoff = now - timedelta(days=90)
        actual_cutoff = fetch_called_with[0]
        # Cutoff should be approximately 90 days ago (within a few seconds)
        delta = abs((actual_cutoff - expected_cutoff).total_seconds())
        assert delta < 5, f"Cutoff delta too large: {delta}s"

        # No records compressed since DB returned empty (all recent)
        assert result["original_count"] == 0
        assert result["compressed_count"] == 0
