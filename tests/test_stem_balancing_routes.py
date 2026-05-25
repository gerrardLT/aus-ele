"""Unit tests for the WEM STEM/Balancing spread analysis endpoint.

Tests the GET /api/v1/wem/stem-balancing endpoint including:
- Spread statistics calculation
- Hourly pattern computation
- Theoretical revenue with BESS constraints
- Unconstrained revenue calculation
- Constraint impact percentage
- Data unavailability handling
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scrapers"))

from database import DatabaseManager


def _create_test_app(db: DatabaseManager) -> TestClient:
    """Create a FastAPI test app with the WEM modules router."""
    app = FastAPI()
    with patch("deps.get_db", return_value=db):
        from routes.wem_modules_routes import router
        app.include_router(router)
        return TestClient(app)


def _seed_stem_prices(db: DatabaseManager, year: int, prices: list[tuple[str, float]]):
    """Seed STEM (Reference Trading Price) data into trading_price_{year} table."""
    with db.get_connection() as conn:
        table_name = f"trading_price_{year}"
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL,
                UNIQUE(settlement_date, region_id)
            )
        """)
        for ts, price in prices:
            conn.execute(
                f"INSERT OR REPLACE INTO {table_name} (settlement_date, region_id, rrp_aud_mwh) VALUES (?, 'WEM', ?)",
                (ts, price),
            )
        conn.commit()


def _seed_balancing_prices(db: DatabaseManager, prices: list[tuple[str, float]]):
    """Seed Balancing (ESS dispatch) energy prices into wem_ess_market_price table."""
    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        for ts, price in prices:
            conn.execute(
                f"INSERT OR REPLACE INTO {db.WEM_ESS_MARKET_TABLE} (dispatch_interval, energy_price) VALUES (?, ?)",
                (ts, price),
            )
        conn.commit()


class TestStemBalancingEndpoint(unittest.TestCase):
    """Tests for GET /api/v1/wem/stem-balancing."""

    def setUp(self):
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = DatabaseManager(self.tmp_path)

    def tearDown(self):
        if os.path.exists(self.tmp_path):
            os.remove(self.tmp_path)

    def test_returns_zeros_when_no_data_available(self):
        """When no STEM or Balancing data exists, returns zero-filled response."""
        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["date_range"], {"start": "2024-01-01", "end": "2024-01-31"})
        self.assertEqual(data["spread_stats"]["mean"], 0.0)
        self.assertEqual(data["theoretical_revenue"], 0.0)
        self.assertEqual(data["unconstrained_revenue"], 0.0)
        self.assertEqual(data["constraint_impact_pct"], 0.0)

    def test_returns_zeros_when_only_stem_data_available(self):
        """When only STEM data exists (no Balancing), returns zero-filled response."""
        _seed_stem_prices(self.db, 2024, [
            ("2024-01-01 08:00:00", 50.0),
            ("2024-01-01 08:30:00", 55.0),
        ])

        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["theoretical_revenue"], 0.0)

    def test_computes_spread_stats_correctly(self):
        """With aligned STEM and Balancing data, computes correct spread statistics."""
        # STEM prices at 30-min intervals
        stem_prices = [
            ("2024-01-01 08:00:00", 50.0),
            ("2024-01-01 08:30:00", 60.0),
            ("2024-01-01 09:00:00", 55.0),
            ("2024-01-01 09:30:00", 45.0),
        ]
        _seed_stem_prices(self.db, 2024, stem_prices)

        # Balancing prices at 5-min intervals (6 per 30-min bucket)
        balancing_prices = []
        # 08:00 bucket: avg = 70 (spread = 70 - 50 = 20)
        for m in range(0, 30, 5):
            balancing_prices.append((f"2024-01-01 08:{m:02d}:00", 70.0))
        # 08:30 bucket: avg = 50 (spread = 50 - 60 = -10)
        for m in range(30, 60, 5):
            balancing_prices.append((f"2024-01-01 08:{m:02d}:00", 50.0))
        # 09:00 bucket: avg = 65 (spread = 65 - 55 = 10)
        for m in range(0, 30, 5):
            balancing_prices.append((f"2024-01-01 09:{m:02d}:00", 65.0))
        # 09:30 bucket: avg = 40 (spread = 40 - 45 = -5)
        for m in range(30, 60, 5):
            balancing_prices.append((f"2024-01-01 09:{m:02d}:00", 40.0))

        _seed_balancing_prices(self.db, balancing_prices)

        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={"start_date": "2024-01-01", "end_date": "2024-01-01"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Spreads: [20, -10, 10, -5]
        # Mean = (20 - 10 + 10 - 5) / 4 = 3.75
        self.assertAlmostEqual(data["spread_stats"]["mean"], 3.75, places=1)
        # Std should be > 0
        self.assertGreater(data["spread_stats"]["std"], 0)

    def test_computes_hourly_pattern(self):
        """Hourly pattern groups spreads by hour of day."""
        stem_prices = [
            ("2024-01-01 08:00:00", 50.0),
            ("2024-01-01 08:30:00", 50.0),
            ("2024-01-01 14:00:00", 80.0),
        ]
        _seed_stem_prices(self.db, 2024, stem_prices)

        balancing_prices = []
        # 08:00 bucket: avg = 60 (spread = 10)
        for m in range(0, 30, 5):
            balancing_prices.append((f"2024-01-01 08:{m:02d}:00", 60.0))
        # 08:30 bucket: avg = 70 (spread = 20)
        for m in range(30, 60, 5):
            balancing_prices.append((f"2024-01-01 08:{m:02d}:00", 70.0))
        # 14:00 bucket: avg = 100 (spread = 20)
        for m in range(0, 30, 5):
            balancing_prices.append((f"2024-01-01 14:{m:02d}:00", 100.0))

        _seed_balancing_prices(self.db, balancing_prices)

        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={"start_date": "2024-01-01", "end_date": "2024-01-01"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should have 24 hourly entries
        self.assertEqual(len(data["hourly_pattern"]), 24)

        # Hour 8 should have avg_spread = (10 + 20) / 2 = 15, count = 2
        hour_8 = next(h for h in data["hourly_pattern"] if h["hour"] == 8)
        self.assertAlmostEqual(hour_8["avg_spread"], 15.0, places=1)
        self.assertEqual(hour_8["count"], 2)

        # Hour 14 should have avg_spread = 20, count = 1
        hour_14 = next(h for h in data["hourly_pattern"] if h["hour"] == 14)
        self.assertAlmostEqual(hour_14["avg_spread"], 20.0, places=1)
        self.assertEqual(hour_14["count"], 1)

    def test_theoretical_revenue_constrained_by_bess_capacity(self):
        """Theoretical revenue is limited by BESS energy capacity per day."""
        # Create a day with many positive spreads to test capacity constraint
        stem_prices = []
        balancing_prices = []

        # 48 intervals per day (30-min each)
        for i in range(48):
            hour = i // 2
            minute = (i % 2) * 30
            ts = f"2024-01-01 {hour:02d}:{minute:02d}:00"
            stem_prices.append((ts, 50.0))

            # Balancing always higher by $20 (positive spread)
            for m_offset in range(0, 30, 5):
                bal_ts = f"2024-01-01 {hour:02d}:{minute + m_offset:02d}:00"
                balancing_prices.append((bal_ts, 70.0))

        _seed_stem_prices(self.db, 2024, stem_prices)
        _seed_balancing_prices(self.db, balancing_prices)

        # BESS: 100 MW, 2h duration -> can only discharge for 4 intervals (4 * 0.5h = 2h)
        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-01",
                    "power_mw": 100,
                    "duration_hours": 2,
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Theoretical should be less than unconstrained (capacity limits apply)
        self.assertGreater(data["unconstrained_revenue"], 0)
        self.assertGreater(data["theoretical_revenue"], 0)
        self.assertLess(data["theoretical_revenue"], data["unconstrained_revenue"])
        self.assertGreater(data["constraint_impact_pct"], 0)

    def test_invalid_date_format_returns_422(self):
        """Invalid date format returns 422 error."""
        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={"start_date": "not-a-date", "end_date": "2024-01-31"},
            )

        self.assertEqual(response.status_code, 422)

    def test_end_date_before_start_date_returns_422(self):
        """end_date before start_date returns 422 error."""
        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={"start_date": "2024-06-01", "end_date": "2024-01-01"},
            )

        self.assertEqual(response.status_code, 422)

    def test_constraint_impact_pct_calculation(self):
        """constraint_impact_pct = (unconstrained - theoretical) / unconstrained * 100."""
        # Create scenario where constraint matters
        stem_prices = []
        balancing_prices = []

        # 48 intervals with positive spreads
        for i in range(48):
            hour = i // 2
            minute = (i % 2) * 30
            ts = f"2024-01-01 {hour:02d}:{minute:02d}:00"
            stem_prices.append((ts, 40.0))
            for m_offset in range(0, 30, 5):
                bal_ts = f"2024-01-01 {hour:02d}:{minute + m_offset:02d}:00"
                balancing_prices.append((bal_ts, 80.0))

        _seed_stem_prices(self.db, 2024, stem_prices)
        _seed_balancing_prices(self.db, balancing_prices)

        # Small BESS: 100 MW, 1h -> only 2 intervals per day
        with patch("deps.get_db", return_value=self.db), \
             patch("routes.wem_modules_routes.get_db", return_value=self.db):
            client = _create_test_app(self.db)
            response = client.get(
                "/api/v1/wem/stem-balancing",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-01",
                    "power_mw": 100,
                    "duration_hours": 1,
                },
            )

        data = response.json()
        unconstrained = data["unconstrained_revenue"]
        theoretical = data["theoretical_revenue"]

        if unconstrained > 0:
            expected_pct = (unconstrained - theoretical) / unconstrained * 100
            self.assertAlmostEqual(data["constraint_impact_pct"], expected_pct, places=1)


if __name__ == "__main__":
    unittest.main()
