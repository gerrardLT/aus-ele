import contextlib
import contextlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock

import bess_backtest
from database import DatabaseManager
import server


FCAS_DEFAULTS = {
    "raise1sec_rrp": 1.0,
    "raise6sec_rrp": 2.0,
    "raise60sec_rrp": 3.0,
    "raise5min_rrp": 4.0,
    "raisereg_rrp": 5.0,
    "lower1sec_rrp": 1.5,
    "lower6sec_rrp": 2.5,
    "lower60sec_rrp": 3.5,
    "lower5min_rrp": 4.5,
    "lowerreg_rrp": 5.5,
}


def make_nem_record(timestamp: str, region: str, price: float, **overrides):
    record = {
        "settlement_date": timestamp,
        "region_id": region,
        "rrp_aud_mwh": price,
    }
    record.update(FCAS_DEFAULTS)
    record.update(overrides)
    return record


@contextlib.contextmanager
def patched_server_db(db_manager: DatabaseManager):
    original_db = server.db
    original_db_path = server.DB_PATH
    original_cache = server.response_cache
    server.db = db_manager
    server.DB_PATH = db_manager.db_path
    server.response_cache = FakeResponseCache()
    try:
        yield
    finally:
        server.db = original_db
        server.DB_PATH = original_db_path
        server.response_cache = original_cache


class FakeResponseCache:
    def __init__(self):
        self.store = {}

    def get_json(self, scope: str, cache_key: str):
        payload = self.store.get((scope, cache_key))
        return json.loads(json.dumps(payload)) if payload is not None else None

    def set_json(self, scope: str, cache_key: str, value, ttl_seconds: int):
        self.store[(scope, cache_key)] = json.loads(json.dumps(value))


@contextlib.contextmanager
def patched_server_response_cache(cache):
    original_cache = server.response_cache
    server.response_cache = cache
    try:
        yield
    finally:
        server.response_cache = original_cache


class ApiLogicFixTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def test_nem_fcas_analysis_includes_1sec_services(self):
        self.db.batch_insert([
            make_nem_record("2025-01-06 00:00:00", "NSW1", 90.0, raise1sec_rrp=12.0, lower1sec_rrp=8.0),
            make_nem_record("2025-01-06 00:05:00", "NSW1", 110.0, raise1sec_rrp=18.0, lower1sec_rrp=6.0),
        ])

        with patched_server_db(self.db):
            result = server.get_fcas_analysis(
                year=2025,
                region="NSW1",
                aggregation="daily",
                capacity_mw=50,
            )

        self.assertTrue(result["has_fcas_data"])
        keys = {item["key"] for item in result["service_breakdown"]}
        self.assertIn("raise1sec", keys)
        self.assertIn("lower1sec", keys)
        self.assertIn("raise1sec_rrp", result["data"][0])
        self.assertIn("lower1sec_rrp", result["data"][0])

    def test_peak_analysis_filters_follow_price_trend_month_precedence(self):
        self.db.batch_insert([
            make_nem_record("2025-01-10 00:00:00", "NSW1", 25.0),
            make_nem_record("2025-01-10 00:05:00", "NSW1", 35.0),
            make_nem_record("2025-04-10 00:00:00", "NSW1", 125.0),
            make_nem_record("2025-04-10 00:05:00", "NSW1", 135.0),
        ])

        with patched_server_db(self.db):
            trend = server.get_price_trend(
                year=2025,
                region="NSW1",
                month="04",
                quarter="Q1",
                day_type=None,
                limit=1500,
            )
            peak = server.get_peak_analysis(
                year=2025,
                region="NSW1",
                aggregation="daily",
                network_fee=0,
                month="04",
                quarter="Q1",
                day_type=None,
            )

        self.assertTrue(all(point["time"].startswith("2025-04-10") for point in trend["data"]))
        self.assertEqual([row["date"] for row in peak["data"]], ["2025-04-10"])

    def test_fcas_analysis_day_type_filter_matches_price_trend(self):
        self.db.batch_insert([
            make_nem_record("2025-01-04 00:00:00", "NSW1", 50.0, raise1sec_rrp=8.0),
            make_nem_record("2025-01-04 00:05:00", "NSW1", 55.0, raise1sec_rrp=9.0),
            make_nem_record("2025-01-06 00:00:00", "NSW1", 150.0, raise1sec_rrp=18.0),
            make_nem_record("2025-01-06 00:05:00", "NSW1", 155.0, raise1sec_rrp=19.0),
        ])

        with patched_server_db(self.db):
            trend = server.get_price_trend(
                year=2025,
                region="NSW1",
                month=None,
                quarter=None,
                day_type="WEEKEND",
                limit=1500,
            )
            fcas = server.get_fcas_analysis(
                year=2025,
                region="NSW1",
                aggregation="daily",
                capacity_mw=10,
                month=None,
                quarter=None,
                day_type="WEEKEND",
            )

        self.assertTrue(all(point["time"].startswith("2025-01-04") for point in trend["data"]))
        self.assertEqual([row["period"] for row in fcas["data"]], ["2025-01-04"])

    def test_investment_analysis_uses_effective_degradation_and_auto_fcas_for_nem(self):
        self.db.batch_insert([
            make_nem_record("2024-01-05 00:00:00", "NSW1", 90.0, raise1sec_rrp=10.0, lower1sec_rrp=10.0),
            make_nem_record("2024-01-05 00:05:00", "NSW1", 95.0, raise1sec_rrp=12.0, lower1sec_rrp=8.0),
            make_nem_record("2025-01-05 00:00:00", "NSW1", 100.0, raise1sec_rrp=20.0, lower1sec_rrp=15.0),
            make_nem_record("2025-01-05 00:05:00", "NSW1", 105.0, raise1sec_rrp=22.0, lower1sec_rrp=13.0),
        ])

        fake_backtest = {
            "total_revenue_aud": 1_000_000,
            "trading_days": 120,
            "revenue_per_mw_year": 10_000,
            "annual_discharge_mwh": 12_000,
            "backtest_mode": "optimized_hindsight",
            "revenue_scope": "physical_upper_bound",
        }

        with patched_server_db(self.db), mock.patch("bess_backtest.backtest_arbitrage", return_value=fake_backtest):
            low_deg = server.investment_analysis(server.InvestmentParams(
                region="NSW1",
                power_mw=100,
                duration_hours=4,
                degradation_rate=0.02,
                backtest_years=[2024, 2025],
                fcas_revenue_mode="auto",
                fcas_revenue_per_mw_year=0,
            ))
            high_deg = server.investment_analysis(server.InvestmentParams(
                region="NSW1",
                power_mw=100,
                duration_hours=4,
                degradation_rate=0.10,
                backtest_years=[2024, 2025],
                fcas_revenue_mode="auto",
                fcas_revenue_per_mw_year=0,
            ))

        self.assertEqual(low_deg["effective_degradation_rate"], 0.02)
        self.assertEqual(low_deg["fcas_baseline_source"], "historical_auto")
        self.assertIn("optimized_hindsight", low_deg["backtest_mode"])
        self.assertGreater(low_deg["baseline_revenue"]["fcas"], 0)
        self.assertLess(high_deg["cash_flows"][-1]["degradation_factor"], low_deg["cash_flows"][-1]["degradation_factor"])
        self.assertLess(high_deg["metrics"]["npv"], low_deg["metrics"]["npv"])

    def test_investment_analysis_falls_back_to_manual_fcas_for_wem(self):
        fake_backtest = {
            "total_revenue_aud": 900_000,
            "trading_days": 90,
            "revenue_per_mw_year": 9_000,
            "annual_discharge_mwh": 10_000,
            "backtest_mode": "optimized_hindsight",
            "revenue_scope": "physical_upper_bound",
        }

        with patched_server_db(self.db), mock.patch("bess_backtest.backtest_arbitrage", return_value=fake_backtest):
            result = server.investment_analysis(server.InvestmentParams(
                region="WEM",
                power_mw=50,
                duration_hours=4,
                degradation_rate=0.03,
                backtest_years=[2025],
                fcas_revenue_mode="auto",
                fcas_revenue_per_mw_year=12345,
            ))

        self.assertEqual(result["fcas_baseline_source"], "manual_input_wem_fallback")
        self.assertEqual(result["baseline_revenue"]["fcas"], 12345 * 50)
        self.assertTrue(any("WEM" in item for item in result["assumptions"]))

    def test_investment_analysis_caches_identical_request_response(self):
        fake_backtest = {
            "total_revenue_aud": 950_000,
            "trading_days": 90,
            "revenue_per_mw_year": 9_500,
            "annual_discharge_mwh": 10_500,
            "backtest_mode": "optimized_hindsight",
            "revenue_scope": "physical_upper_bound",
        }
        self.db.set_last_update_time("2026-04-16 09:00:00")
        params = server.InvestmentParams(
            region="NSW1",
            power_mw=100,
            duration_hours=4,
            degradation_rate=0.03,
            discount_rate=0.08,
            backtest_years=[2025],
            fcas_revenue_mode="manual",
            fcas_revenue_per_mw_year=20000,
        )

        with patched_server_db(self.db), mock.patch("bess_backtest.backtest_arbitrage", return_value=fake_backtest) as mock_backtest:
            first = server.investment_analysis(params)
            second = server.investment_analysis(params)

        self.assertEqual(mock_backtest.call_count, 1)
        self.assertEqual(first, second)

    def test_investment_analysis_reuses_backtest_and_fcas_cache_when_only_finance_changes(self):
        fake_backtest = {
            "total_revenue_aud": 1_100_000,
            "trading_days": 120,
            "revenue_per_mw_year": 11_000,
            "annual_discharge_mwh": 12_500,
            "backtest_mode": "optimized_hindsight",
            "revenue_scope": "physical_upper_bound",
        }
        self.db.set_last_update_time("2026-04-16 09:05:00")

        with patched_server_db(self.db), \
            mock.patch("bess_backtest.backtest_arbitrage", return_value=fake_backtest) as mock_backtest, \
            mock.patch("server._estimate_nem_fcas_baseline", return_value=(250_000.0, "historical_auto")) as mock_fcas:
            low_discount = server.investment_analysis(server.InvestmentParams(
                region="NSW1",
                power_mw=100,
                duration_hours=4,
                degradation_rate=0.03,
                discount_rate=0.08,
                backtest_years=[2024, 2025],
                fcas_revenue_mode="auto",
                fcas_revenue_per_mw_year=0,
            ))
            high_discount = server.investment_analysis(server.InvestmentParams(
                region="NSW1",
                power_mw=100,
                duration_hours=4,
                degradation_rate=0.03,
                discount_rate=0.12,
                backtest_years=[2024, 2025],
                fcas_revenue_mode="auto",
                fcas_revenue_per_mw_year=0,
            ))

        self.assertEqual(mock_backtest.call_count, 2)
        self.assertEqual(mock_fcas.call_count, 1)
        self.assertNotEqual(low_discount["metrics"]["npv"], high_discount["metrics"]["npv"])

    def test_investment_analysis_deduplicates_identical_inflight_requests(self):
        fake_backtest = {
            "total_revenue_aud": 1_000_000,
            "trading_days": 100,
            "revenue_per_mw_year": 10_000,
            "annual_discharge_mwh": 11_000,
            "backtest_mode": "optimized_hindsight",
            "revenue_scope": "physical_upper_bound",
        }
        self.db.set_last_update_time("2026-04-16 09:10:00")
        params = server.InvestmentParams(
            region="QLD1",
            power_mw=100,
            duration_hours=4,
            degradation_rate=0.03,
            discount_rate=0.08,
            backtest_years=[2025],
            fcas_revenue_mode="manual",
            fcas_revenue_per_mw_year=15000,
        )

        first_started = threading.Event()
        release_first = threading.Event()
        call_count = 0
        call_count_lock = threading.Lock()

        def slow_backtest(*args, **kwargs):
            nonlocal call_count
            with call_count_lock:
                call_count += 1
                current_call = call_count

            if current_call == 1:
                first_started.set()
                release_first.wait(timeout=1.0)

            time.sleep(0.05)
            return dict(fake_backtest)

        results = []
        errors = []

        def invoke():
            try:
                results.append(server.investment_analysis(params))
            except Exception as exc:  # pragma: no cover - diagnostic safety
                errors.append(exc)

        with patched_server_db(self.db), mock.patch("bess_backtest.backtest_arbitrage", side_effect=slow_backtest):
            thread1 = threading.Thread(target=invoke)
            thread1.start()
            self.assertTrue(first_started.wait(timeout=1.0))

            thread2 = threading.Thread(target=invoke)
            thread2.start()
            time.sleep(0.1)
            release_first.set()

            thread1.join(timeout=2.0)
            thread2.join(timeout=2.0)

        self.assertFalse(thread1.is_alive())
        self.assertFalse(thread2.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(call_count, 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])

    def test_investment_analysis_uses_redis_response_cache_when_local_cache_misses(self):
        fake_backtest = {
            "total_revenue_aud": 880_000,
            "trading_days": 95,
            "revenue_per_mw_year": 8_800,
            "annual_discharge_mwh": 9_900,
            "backtest_mode": "optimized_hindsight",
            "revenue_scope": "physical_upper_bound",
        }
        fake_cache = FakeResponseCache()
        self.db.set_last_update_time("2026-04-16 10:30:00")
        params = server.InvestmentParams(
            region="NSW1",
            power_mw=100,
            duration_hours=4,
            degradation_rate=0.03,
            discount_rate=0.08,
            backtest_years=[2025],
            fcas_revenue_mode="manual",
            fcas_revenue_per_mw_year=15000,
        )

        with patched_server_db(self.db), \
            patched_server_response_cache(fake_cache), \
            mock.patch.object(self.db, "fetch_analysis_cache", return_value=None), \
            mock.patch.object(self.db, "upsert_analysis_cache"), \
            mock.patch("bess_backtest.backtest_arbitrage", return_value=fake_backtest) as mock_backtest:
            first = server.investment_analysis(params)
            second = server.investment_analysis(params)

        self.assertEqual(mock_backtest.call_count, 1)
        self.assertEqual(first, second)

    def test_price_trend_uses_redis_response_cache(self):
        fake_cache = FakeResponseCache()
        self.db.set_last_update_time("2026-04-16 10:40:00")
        self.db.batch_insert([
            make_nem_record("2025-01-06 00:00:00", "NSW1", 90.0),
            make_nem_record("2025-01-06 00:05:00", "NSW1", 110.0),
        ])

        with patched_server_db(self.db), patched_server_response_cache(fake_cache):
            first = server.get_price_trend(year=2025, region="NSW1", month=None, quarter=None, day_type=None, limit=1500)
            with mock.patch.object(self.db, "get_last_update_time", return_value="2026-04-16 10:40:00"), \
                mock.patch.object(self.db, "get_connection", side_effect=RuntimeError("db should not be hit on redis cache hit")):
                second = server.get_price_trend(year=2025, region="NSW1", month=None, quarter=None, day_type=None, limit=1500)

        self.assertEqual(first, second)

    def test_peak_analysis_uses_redis_response_cache(self):
        fake_cache = FakeResponseCache()
        self.db.set_last_update_time("2026-04-16 10:45:00")
        self.db.batch_insert([
            make_nem_record("2025-01-06 00:00:00", "NSW1", 20.0),
            make_nem_record("2025-01-06 00:05:00", "NSW1", 30.0),
            make_nem_record("2025-01-06 00:10:00", "NSW1", 100.0),
            make_nem_record("2025-01-06 00:15:00", "NSW1", 110.0),
        ])

        with patched_server_db(self.db), patched_server_response_cache(fake_cache):
            first = server.get_peak_analysis(year=2025, region="NSW1", aggregation="daily", network_fee=0, month=None, quarter=None, day_type=None)
            with mock.patch.object(self.db, "get_last_update_time", return_value="2026-04-16 10:45:00"), \
                mock.patch.object(self.db, "get_connection", side_effect=RuntimeError("db should not be hit on redis cache hit")):
                second = server.get_peak_analysis(year=2025, region="NSW1", aggregation="daily", network_fee=0, month=None, quarter=None, day_type=None)

        self.assertEqual(first, second)

    def test_hourly_price_profile_uses_redis_response_cache(self):
        fake_cache = FakeResponseCache()
        self.db.set_last_update_time("2026-04-16 10:50:00")
        self.db.batch_insert([
            make_nem_record("2025-01-06 00:00:00", "NSW1", -10.0),
            make_nem_record("2025-01-06 00:05:00", "NSW1", 40.0),
        ])

        with patched_server_db(self.db), patched_server_response_cache(fake_cache):
            first = server.get_hourly_price_profile(year=2025, region="NSW1", month="01")
            with mock.patch.object(self.db, "get_last_update_time", return_value="2026-04-16 10:50:00"), \
                mock.patch.object(self.db, "get_connection", side_effect=RuntimeError("db should not be hit on redis cache hit")):
                second = server.get_hourly_price_profile(year=2025, region="NSW1", month="01")

        self.assertEqual(first, second)

    def test_fcas_analysis_uses_redis_response_cache(self):
        fake_cache = FakeResponseCache()
        self.db.set_last_update_time("2026-04-16 10:55:00")
        self.db.batch_insert([
            make_nem_record("2025-01-06 00:00:00", "NSW1", 90.0, raise1sec_rrp=12.0, lower1sec_rrp=8.0),
            make_nem_record("2025-01-06 00:05:00", "NSW1", 110.0, raise1sec_rrp=18.0, lower1sec_rrp=6.0),
        ])

        with patched_server_db(self.db), patched_server_response_cache(fake_cache):
            first = server.get_fcas_analysis(year=2025, region="NSW1", aggregation="daily", capacity_mw=50, month=None, quarter=None, day_type=None)
            with mock.patch.object(self.db, "get_last_update_time", return_value="2026-04-16 10:55:00"), \
                mock.patch.object(self.db, "get_connection", side_effect=RuntimeError("db should not be hit on redis cache hit")):
                second = server.get_fcas_analysis(year=2025, region="NSW1", aggregation="daily", capacity_mw=50, month=None, quarter=None, day_type=None)

        self.assertEqual(first, second)

    def test_wem_fcas_analysis_marks_single_day_preview_metadata(self):
        with self.db.get_connection() as conn:
            self.db.ensure_wem_ess_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.db.WEM_ESS_MARKET_TABLE} (
                    dispatch_interval,
                    energy_price,
                    regulation_raise_price,
                    regulation_lower_price,
                    contingency_raise_price,
                    contingency_lower_price,
                    rocof_price,
                    available_regulation_raise,
                    available_regulation_lower,
                    available_contingency_raise,
                    available_contingency_lower,
                    available_rocof,
                    in_service_regulation_raise,
                    in_service_regulation_lower,
                    in_service_contingency_raise,
                    in_service_contingency_lower,
                    in_service_rocof,
                    requirement_regulation_raise,
                    requirement_regulation_lower,
                    requirement_contingency_raise,
                    requirement_contingency_lower,
                    requirement_rocof,
                    shortfall_regulation_raise,
                    shortfall_regulation_lower,
                    shortfall_contingency_raise,
                    shortfall_contingency_lower,
                    shortfall_rocof,
                    dispatch_total_regulation_raise,
                    dispatch_total_regulation_lower,
                    dispatch_total_contingency_raise,
                    dispatch_total_contingency_lower,
                    dispatch_total_rocof,
                    capped_regulation_raise,
                    capped_regulation_lower,
                    capped_contingency_raise,
                    capped_contingency_lower,
                    capped_rocof
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "2026-04-13 08:00:00",
                    96.12,
                    15.0,
                    11.0,
                    6.0,
                    4.0,
                    3.0,
                    435.296,
                    437.024,
                    329.771,
                    331.636,
                    5966.0,
                    979.74,
                    979.74,
                    980.4,
                    1055.398,
                    12124.5,
                    110.0,
                    110.0,
                    258.268,
                    72.308,
                    12124.5,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    110.0,
                    110.0,
                    268.853,
                    72.308,
                    12124.5,
                    1,
                    0,
                    0,
                    0,
                    0,
                ),
            )
            conn.execute(
                f"""
                INSERT INTO {self.db.WEM_ESS_CONSTRAINT_TABLE} (
                    dispatch_interval,
                    binding_count,
                    near_binding_count,
                    binding_max_shadow_price,
                    near_binding_max_shadow_price,
                    max_formulation_shadow_price,
                    max_facility_shadow_price,
                    max_network_shadow_price,
                    max_generic_shadow_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-04-13 08:00:00", 1, 2, 96.12, 96.12, 96.12, 0.0, 0.0, 0.0),
            )
            conn.commit()

        with patched_server_db(self.db):
            result = server.get_fcas_analysis(
                year=2026,
                region="WEM",
                aggregation="daily",
                capacity_mw=100,
            )

        self.assertEqual(result["summary"]["preview_mode"], "single_day_preview")
        self.assertEqual(result["summary"]["coverage_days"], 1)
        self.assertFalse(result["summary"]["investment_grade"])


class BacktestConstraintTests(unittest.TestCase):
    def test_backtest_arbitrage_returns_to_mid_soc_and_respects_cycle_limit(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE trading_price_2025 (
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL
            )
            """
        )

        rows = []
        for hour in range(24):
            price = 20.0 if hour < 12 else 220.0
            rows.append((f"2025-01-01 {hour:02d}:00:00", "NSW1", price))
        conn.executemany(
            "INSERT INTO trading_price_2025 (settlement_date, region_id, rrp_aud_mwh) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()

        result = bess_backtest.backtest_arbitrage(conn, "NSW1", 2025, {
            "duration_hours": 1,
            "capacity_mwh": 100,
            "power_mw": 100,
        })
        conn.close()

        self.assertEqual(result["backtest_mode"], "optimized_hindsight")
        self.assertEqual(result["revenue_scope"], "physical_upper_bound")
        self.assertAlmostEqual(result["initial_soc_mwh"], result["terminal_soc_mwh"], places=2)
        self.assertLessEqual(result["annual_charge_mwh"], result["throughput_limit_mwh"] + 1e-6)


if __name__ == "__main__":
    unittest.main()
