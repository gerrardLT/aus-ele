"""Tests for backvalidation API endpoints.

验证反推验证 API 端点的集成测试：
1. 有效区域返回 200 + 预期字段
2. 无效区域返回 422
3. 摘要端点返回 4 个区域
4. 偏差计算公式验证
5. 摘要结果按 |deviation_percent| 降序排列

Requirements: 3.3
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()


class TestBackvalidationRoutes:
    """Test backvalidation API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        # Mock the ForwardPriceEngine to avoid needing real data files
        with patch(
            "routes.narrative_routes._get_forward_price_engine"
        ) as mock_engine_fn:
            mock_engine = MagicMock()
            mock_engine._calibration = {
                "status": "calibrated",
                "confidence_interval": {"p10": 80, "p50": 120, "p90": 160},
            }

            # Mock calculate_price_distribution to return predictable values
            mock_dist = MagicMock()
            mock_dist.mean_spread = 120.0
            mock_engine.calculate_price_distribution.return_value = mock_dist
            mock_engine._get_cumulative_bess_capacity.return_value = 1000.0

            mock_engine_fn.return_value = mock_engine

            from fastapi.testclient import TestClient
            from app import app

            client = TestClient(app)
            yield client

    def test_backvalidation_region_valid(self, client):
        """Valid region returns 200 with expected fields."""
        response = client.get("/api/v1/narrative/backvalidation/NSW1")
        assert response.status_code == 200
        data = response.json()
        assert "region" in data
        assert "model_revenue" in data
        assert "benchmark_revenue" in data
        assert "deviation_percent" in data
        assert "status" in data
        assert data["region"] == "NSW1"

    def test_backvalidation_region_invalid_422(self, client):
        """Invalid region returns 422."""
        response = client.get("/api/v1/narrative/backvalidation/INVALID")
        assert response.status_code == 422

    def test_backvalidation_summary_returns_all_regions(self, client):
        """Summary endpoint returns results for all 4 NEM regions."""
        response = client.get("/api/v1/narrative/backvalidation/summary")
        assert response.status_code == 200
        data = response.json()
        assert "regions" in data
        assert len(data["regions"]) == 4
        assert "within_range_count" in data
        assert "out_of_range_count" in data
        assert data["within_range_count"] + data["out_of_range_count"] <= 4

    def test_backvalidation_deviation_calculation(self, client):
        """Verify revenue formula: spread × 365 × 4 × 0.65 × 0.87."""
        response = client.get("/api/v1/narrative/backvalidation/NSW1")
        data = response.json()
        # With mean_spread=120, revenue should be 120 * 365 * 4 * 0.65 * 0.87
        expected_revenue = 120.0 * 365 * 4 * 0.65 * 0.87
        assert abs(data["model_revenue"] - expected_revenue) < 1.0

    def test_backvalidation_summary_sorted_by_deviation(self, client):
        """Summary results should be sorted by |deviation_percent| descending."""
        response = client.get("/api/v1/narrative/backvalidation/summary")
        data = response.json()
        deviations = [
            abs(r["deviation_percent"])
            for r in data["regions"]
            if r["deviation_percent"] is not None
        ]
        assert deviations == sorted(deviations, reverse=True)
