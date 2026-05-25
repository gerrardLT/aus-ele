"""Unit tests for FcasDataCompressor.

Tests the downsample logic, window computation, and compression workflow.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import datetime, timezone, timedelta

import pytest

from pipelines.fcas_compressor import FcasDataCompressor, _NUMERIC_COLUMNS


class TestFcasDataCompressorDownsample:
    """Tests for FcasDataCompressor._downsample() method."""

    def setup_method(self):
        self.compressor = FcasDataCompressor()

    def test_empty_records_returns_empty(self):
        result = self.compressor._downsample([], 60)
        assert result == []

    def test_single_record_returns_single(self):
        record = {
            "timestamp": "2024-01-01T00:00:04+00:00",
            "region_id": "NSW1",
            "raise6sec_price": 10.0,
            "raise60sec_price": 20.0,
            "raise5min_price": 30.0,
            "raisereg_price": 5.0,
            "raise1sec_price": 15.0,
            "lower6sec_price": 8.0,
            "lower60sec_price": 12.0,
            "lower5min_price": 6.0,
            "lowerreg_price": 4.0,
            "lower1sec_price": 7.0,
            "total_demand_mw": 5000.0,
            "frequency_hz": 50.01,
        }
        result = self.compressor._downsample([record], 60)
        assert len(result) == 1
        assert result[0]["region_id"] == "NSW1"
        assert result[0]["raise6sec_price"] == 10.0
        assert result[0]["total_demand_mw"] == 5000.0

    def test_multiple_records_same_window_averaged(self):
        """Records within the same 1-minute window should be averaged."""
        records = [
            {
                "timestamp": "2024-01-01T00:00:04+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 10.0,
                "raise60sec_price": 20.0,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": 5000.0,
                "frequency_hz": 50.0,
            },
            {
                "timestamp": "2024-01-01T00:00:08+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 20.0,
                "raise60sec_price": 30.0,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": 6000.0,
                "frequency_hz": 50.02,
            },
            {
                "timestamp": "2024-01-01T00:00:12+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 30.0,
                "raise60sec_price": 40.0,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": 7000.0,
                "frequency_hz": 49.98,
            },
        ]
        result = self.compressor._downsample(records, 60)
        assert len(result) == 1
        assert result[0]["region_id"] == "NSW1"
        # Average of 10, 20, 30
        assert result[0]["raise6sec_price"] == pytest.approx(20.0)
        # Average of 20, 30, 40
        assert result[0]["raise60sec_price"] == pytest.approx(30.0)
        # Average of 5000, 6000, 7000
        assert result[0]["total_demand_mw"] == pytest.approx(6000.0)
        # Average of 50.0, 50.02, 49.98
        assert result[0]["frequency_hz"] == pytest.approx(50.0, abs=0.01)

    def test_different_windows_produce_separate_records(self):
        """Records in different 1-minute windows should not be merged."""
        records = [
            {
                "timestamp": "2024-01-01T00:00:04+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 10.0,
                "raise60sec_price": None,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": None,
                "frequency_hz": None,
            },
            {
                "timestamp": "2024-01-01T00:01:04+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 20.0,
                "raise60sec_price": None,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": None,
                "frequency_hz": None,
            },
        ]
        result = self.compressor._downsample(records, 60)
        assert len(result) == 2

    def test_different_regions_produce_separate_records(self):
        """Records from different regions in the same window should not be merged."""
        records = [
            {
                "timestamp": "2024-01-01T00:00:04+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 10.0,
                "raise60sec_price": None,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": None,
                "frequency_hz": None,
            },
            {
                "timestamp": "2024-01-01T00:00:08+00:00",
                "region_id": "QLD1",
                "raise6sec_price": 20.0,
                "raise60sec_price": None,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": None,
                "frequency_hz": None,
            },
        ]
        result = self.compressor._downsample(records, 60)
        assert len(result) == 2
        regions = {r["region_id"] for r in result}
        assert regions == {"NSW1", "QLD1"}

    def test_none_values_excluded_from_average(self):
        """None values should be excluded from averaging, not treated as 0."""
        records = [
            {
                "timestamp": "2024-01-01T00:00:04+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 10.0,
                "raise60sec_price": None,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": None,
                "frequency_hz": None,
            },
            {
                "timestamp": "2024-01-01T00:00:08+00:00",
                "region_id": "NSW1",
                "raise6sec_price": 30.0,
                "raise60sec_price": None,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": None,
                "frequency_hz": None,
            },
        ]
        result = self.compressor._downsample(records, 60)
        assert len(result) == 1
        # Average of 10 and 30 (not 10, None, 30)
        assert result[0]["raise6sec_price"] == pytest.approx(20.0)
        # All None -> None
        assert result[0]["raise60sec_price"] is None

    def test_compression_ratio_approximately_1_over_15(self):
        """15 records per minute (4s intervals) should compress to 1 record."""
        # 15 records at 4-second intervals within one minute
        records = []
        for i in range(15):
            seconds = i * 4
            records.append({
                "timestamp": f"2024-01-01T00:00:{seconds:02d}+00:00",
                "region_id": "SA1",
                "raise6sec_price": float(i),
                "raise60sec_price": float(i * 2),
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": 5000.0 + i,
                "frequency_hz": 50.0,
            })
        result = self.compressor._downsample(records, 60)
        assert len(result) == 1
        # Compression ratio: 1/15
        assert len(result) / len(records) == pytest.approx(1 / 15)


class TestFcasDataCompressorCompress:
    """Tests for FcasDataCompressor.compress() integration with mock DB."""

    def test_compress_no_old_records(self):
        """When no old records exist, compress returns zeros."""

        class MockDB:
            def fetch_fcas_4s_before(self, cutoff):
                return []

            def replace_fcas_records(self, before, new_records):
                return 0

        compressor = FcasDataCompressor()
        result = compressor.compress(MockDB())
        assert result["original_count"] == 0
        assert result["compressed_count"] == 0
        assert result["compression_ratio"] == 0.0

    def test_compress_with_old_records(self):
        """Compress should downsample and replace old records."""
        old_records = []
        for i in range(15):
            old_records.append({
                "timestamp": "2024-01-01T00:00:{:02d}+00:00".format(i * 4),
                "region_id": "VIC1",
                "raise6sec_price": 10.0,
                "raise60sec_price": 20.0,
                "raise5min_price": None,
                "raisereg_price": None,
                "raise1sec_price": None,
                "lower6sec_price": None,
                "lower60sec_price": None,
                "lower5min_price": None,
                "lowerreg_price": None,
                "lower1sec_price": None,
                "total_demand_mw": 4000.0,
                "frequency_hz": 50.0,
            })

        replaced_records = []

        class MockDB:
            def fetch_fcas_4s_before(self, cutoff):
                return old_records

            def replace_fcas_records(self, before, new_records):
                replaced_records.extend(new_records)
                return len(new_records)

        compressor = FcasDataCompressor()
        result = compressor.compress(MockDB())

        assert result["original_count"] == 15
        assert result["compressed_count"] == 1
        assert result["compression_ratio"] == pytest.approx(1 / 15)
        assert len(replaced_records) == 1
        assert replaced_records[0]["region_id"] == "VIC1"
        assert replaced_records[0]["raise6sec_price"] == pytest.approx(10.0)


class TestWindowComputation:
    """Tests for _compute_window_start."""

    def setup_method(self):
        self.compressor = FcasDataCompressor()

    def test_window_start_at_minute_boundary(self):
        result = self.compressor._compute_window_start("2024-01-01T00:00:00+00:00", 60)
        assert "00:00:00" in result

    def test_window_start_mid_minute(self):
        result = self.compressor._compute_window_start("2024-01-01T00:00:32+00:00", 60)
        assert "00:00:00" in result

    def test_window_start_end_of_minute(self):
        result = self.compressor._compute_window_start("2024-01-01T00:00:56+00:00", 60)
        assert "00:00:00" in result

    def test_window_start_second_minute(self):
        result = self.compressor._compute_window_start("2024-01-01T00:01:04+00:00", 60)
        assert "00:01:00" in result
