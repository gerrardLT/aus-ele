import contextlib
import json
import os
import tempfile
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server


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


def seed_recent_nem_history(db: DatabaseManager, region: str):
    rows = [
        {"settlement_date": "2026-04-14 22:00:00", "region_id": region, "rrp_aud_mwh": 35.0, "raise1sec_rrp": 8.0},
        {"settlement_date": "2026-04-14 22:05:00", "region_id": region, "rrp_aud_mwh": 45.0, "raise1sec_rrp": 9.0},
        {"settlement_date": "2026-04-14 22:10:00", "region_id": region, "rrp_aud_mwh": 55.0, "raise1sec_rrp": 10.0},
        {"settlement_date": "2026-04-14 22:15:00", "region_id": region, "rrp_aud_mwh": 65.0, "raise1sec_rrp": 11.0},
    ]
    db.batch_insert(rows)


def seed_event_state(
    db: DatabaseManager,
    *,
    region: str,
    state_type: str,
    severity: str,
    market: str = "NEM",
):
    db.replace_grid_event_states(market, [
        {
            "state_id": f"{market.lower()}-{region.lower()}-{state_type}",
            "market": market,
            "region": region,
            "state_type": state_type,
            "start_time": "2026-04-15 10:00:00",
            "end_time": "2026-04-15 18:00:00",
            "severity": severity,
            "confidence": 0.9,
            "headline": f"{region} {state_type}",
            "impact_domains": ["grid_forecast"],
            "evidence_event_ids": [1],
            "evidence_summary_json": [{"source": "test"}],
        }
    ])


def seed_wem_slim_history(db: DatabaseManager):
    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        conn.execute(
            f"""
            INSERT INTO {db.WEM_ESS_MARKET_TABLE} (
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
                "2026-04-14 08:00:00",
                220.0,
                15.0,
                11.0,
                6.0,
                4.0,
                3.0,
                435.0,
                437.0,
                330.0,
                332.0,
                5966.0,
                980.0,
                980.0,
                981.0,
                1055.0,
                12124.5,
                110.0,
                110.0,
                258.0,
                72.0,
                12124.5,
                0.0,
                0.0,
                4.0,
                0.0,
                0.0,
                110.0,
                110.0,
                269.0,
                72.0,
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
            INSERT INTO {db.WEM_ESS_CONSTRAINT_TABLE} (
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
            ("2026-04-14 08:00:00", 3, 4, 320.0, 180.0, 150.0, 80.0, 320.0, 40.0),
        )
        conn.commit()


class GridForecastStorageTests(unittest.TestCase):
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

    def test_snapshot_round_trip(self):
        payload = {
            "metadata": {
                "market": "NEM",
                "region": "NSW1",
                "horizon": "24h",
                "coverage_quality": "full",
            },
            "summary": {"grid_stress_score": 78},
            "windows": [],
            "drivers": [],
        }

        self.db.upsert_grid_forecast_snapshot(
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of_bucket="2026-04-15 09:00:00",
            issued_at="2026-04-15 09:02:00",
            expires_at="2026-04-15 10:00:00",
            coverage_quality="full",
            response_payload=payload,
        )

        row = self.db.fetch_grid_forecast_snapshot(
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of_bucket="2026-04-15 09:00:00",
        )

        self.assertEqual(row["coverage_quality"], "full")
        self.assertEqual(row["response"]["summary"]["grid_stress_score"], 78)


class GridForecastEngineTests(unittest.TestCase):
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

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_24h_forecast_uses_predispatch_and_event_signals(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": -35.0, "demand_mw": 8900.0},
            {"time": "2026-04-15 18:00:00", "price": 420.0, "demand_mw": 12900.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_event_state(self.db, region="NSW1", state_type="reserve_tightness", severity="high")

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertEqual(result["metadata"]["forecast_mode"], "hybrid_signal_calibrated")
        self.assertEqual(result["metadata"]["coverage_quality"], "full")
        self.assertGreaterEqual(result["summary"]["price_spike_risk_score"], 70)
        self.assertGreaterEqual(result["summary"]["negative_price_risk_score"], 40)
        self.assertIn("reserve_tightness", result["summary"]["driver_tags"])
        self.assertEqual(result["coverage"]["source_status"]["nem_predispatch"], "ok")
        self.assertEqual(result["coverage"]["forward_points"], 2)
        self.assertEqual(result["market_context"]["forward_price_max_aud_mwh"], 420.0)
        self.assertEqual(result["market_context"]["forward_demand_peak_mw"], 12900.0)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_long_horizon_switches_to_regime_outlook(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": -25.0, "demand_mw": 9100.0},
            {"time": "2026-04-15 18:00:00", "price": 280.0, "demand_mw": 12600.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_event_state(self.db, region="NSW1", state_type="network_stress", severity="medium")

        day_ahead = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )
        weekly = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="7d",
            as_of="2026-04-15 09:07:00",
        )
        monthly = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="30d",
            as_of="2026-04-15 09:07:00",
        )

        self.assertEqual(day_ahead["metadata"]["forecast_mode"], "hybrid_signal_calibrated")
        self.assertEqual(weekly["metadata"]["forecast_mode"], "daily_regime_outlook")
        self.assertEqual(monthly["metadata"]["forecast_mode"], "structural_regime_outlook")
        self.assertEqual(weekly["coverage"]["forward_points"], 0)
        self.assertEqual(monthly["coverage"]["forward_points"], 0)
        self.assertEqual(weekly["coverage"]["source_status"]["nem_predispatch"], "stale")
        self.assertEqual(monthly["coverage"]["source_status"]["nem_predispatch"], "stale")
        self.assertTrue(all(window["window_type"] == "core_risk_window" for window in weekly["windows"]))
        self.assertEqual(len(monthly["windows"]), 1)
        self.assertEqual(monthly["windows"][0]["window_type"], "core_risk_window")

    def test_wem_forecast_returns_core_only_and_not_investment_grade(self):
        import grid_forecast

        seed_wem_slim_history(self.db)
        seed_event_state(self.db, region="WEM", state_type="network_stress", severity="medium", market="WEM")

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="WEM",
            region="WEM",
            horizon="7d",
            as_of="2026-04-15 09:07:00",
        )

        self.assertEqual(result["metadata"]["coverage_quality"], "core_only")
        self.assertFalse(result["metadata"]["investment_grade"])
        self.assertIn("confidence_constrained", result["metadata"]["warnings"])
        self.assertEqual(result["coverage"]["source_status"]["wem_ess_slim"], "ok")
        self.assertEqual(result["coverage"]["source_status"]["event_state"], "ok")
        self.assertEqual(result["market_context"]["binding_shadow_max"], 320.0)
        self.assertEqual(result["market_context"]["constraint_pressure_index"], 34.0)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_cache_hit_skips_upstream_fetch(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": 120.0, "demand_mw": 9500.0}
        ]
        seed_recent_nem_history(self.db, region="NSW1")

        grid_forecast.get_grid_forecast_response(self.db, "NEM", "NSW1", "24h", "2026-04-15 09:07:00")
        grid_forecast.get_grid_forecast_response(self.db, "NEM", "NSW1", "24h", "2026-04-15 09:20:00")

        self.assertEqual(mock_p5.call_count, 1)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_legacy_cached_snapshot_is_rebuilt_when_new_metadata_is_missing(self, mock_p5):
        import grid_forecast

        seed_recent_nem_history(self.db, region="NSW1")
        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": 180.0, "demand_mw": 9500.0}
        ]
        self.db.upsert_grid_forecast_snapshot(
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of_bucket="2026-04-15 09:00:00",
            issued_at="2026-04-15 09:02:00",
            expires_at="2026-04-15 10:00:00",
            coverage_quality="full",
            response_payload={
                "metadata": {
                    "market": "NEM",
                    "region": "NSW1",
                    "horizon": "24h",
                    "coverage_quality": "full",
                },
                "summary": {"grid_stress_score": 51},
                "windows": [],
                "drivers": [],
            },
        )

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertIn("coverage", result)
        self.assertIn("market_context", result)
        self.assertEqual(result["coverage"]["source_status"]["nem_predispatch"], "ok")
        self.assertEqual(mock_p5.call_count, 1)


class GridForecastRouteTests(unittest.TestCase):
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

    def test_grid_forecast_route_delegates_to_engine(self):
        fake = {
            "metadata": {"coverage_quality": "full", "forecast_mode": "hybrid_signal_calibrated"},
            "summary": {"grid_stress_score": 81},
            "windows": [],
            "drivers": [],
        }
        with patched_server_db(self.db), mock.patch("grid_forecast.get_grid_forecast_response", return_value=fake):
            result = server.get_grid_forecast(market="NEM", region="NSW1", horizon="24h", as_of=None)
        self.assertEqual(result["summary"]["grid_stress_score"], 81)

    def test_grid_forecast_route_uses_redis_response_cache(self):
        fake = {
            "metadata": {"coverage_quality": "full", "forecast_mode": "hybrid_signal_calibrated"},
            "summary": {"grid_stress_score": 81},
            "windows": [],
            "drivers": [],
        }
        fake_cache = FakeResponseCache()
        self.db.set_last_update_time("2026-04-16 10:20:00")

        with patched_server_db(self.db), patched_server_response_cache(fake_cache), \
            mock.patch("server._grid_forecast_data_version", return_value="grid-forecast-version"), \
            mock.patch("grid_forecast.get_grid_forecast_response", return_value=fake) as mock_route:
            first = server.get_grid_forecast(market="NEM", region="NSW1", horizon="24h", as_of="2026-04-16 10:21:00")
            second = server.get_grid_forecast(market="NEM", region="NSW1", horizon="24h", as_of="2026-04-16 10:25:00")

        self.assertEqual(mock_route.call_count, 1)
        self.assertEqual(first, second)

    def test_grid_forecast_coverage_route_delegates_to_engine(self):
        fake = {
            "coverage_quality": "core_only",
            "sources_used": ["event_state", "wem_ess_slim"],
            "source_status": {"wem_ess_slim": "ok"},
        }
        with patched_server_db(self.db), mock.patch("grid_forecast.get_grid_forecast_coverage", return_value=fake):
            result = server.get_grid_forecast_coverage(market="WEM", region="WEM", horizon="7d", as_of=None)
        self.assertEqual(result["coverage_quality"], "core_only")
        self.assertEqual(result["source_status"]["wem_ess_slim"], "ok")


if __name__ == "__main__":
    unittest.main()
