import contextlib
import datetime as dt
import json
import os
import tempfile
import unittest
from unittest import mock
import warnings

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server


@contextlib.contextmanager
def patched_server_db(db_manager: DatabaseManager):
    """把 server 的库/缓存切到测试实例。

    刻意不再碰 ``server.DB_PATH``：那是 SQLite 时代的模块全局，PG 迁移后已删除，
    而 ``DatabaseManager`` 在 PG 下也忽略传入的 db_path（所有实例连同一个库）。
    """
    original_db = server.db
    original_cache = server.response_cache
    server.db = db_manager
    server.response_cache = FakeResponseCache()
    try:
        yield
    finally:
        server.db = original_db
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


def seed_forward_nem_actuals(db: DatabaseManager, region: str):
    rows = [
        {"settlement_date": "2026-04-15 12:00:00", "region_id": region, "rrp_aud_mwh": -20.0, "raise1sec_rrp": 6.0},
        {"settlement_date": "2026-04-15 18:00:00", "region_id": region, "rrp_aud_mwh": 390.0, "raise1sec_rrp": 14.0},
    ]
    db.batch_insert(rows)


def seed_forward_nem_long_actuals(db: DatabaseManager, region: str):
    rows = [
        {"settlement_date": "2026-04-16 12:00:00", "region_id": region, "rrp_aud_mwh": -15.0, "raise1sec_rrp": 7.0},
        {"settlement_date": "2026-04-18 18:00:00", "region_id": region, "rrp_aud_mwh": 310.0, "raise1sec_rrp": 13.0},
        {"settlement_date": "2026-05-05 18:00:00", "region_id": region, "rrp_aud_mwh": 265.0, "raise1sec_rrp": 9.0},
    ]
    db.batch_insert(rows)


def seed_operational_demand_actuals(db: DatabaseManager, region: str, values: list[float]):
    with db.get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operational_demand_actual_hh (
                region_id TEXT NOT NULL,
                interval_datetime TEXT NOT NULL,
                operational_demand REAL,
                operational_demand_adjustment REAL,
                wdr_estimate REAL,
                lastchanged TEXT,
                source_file TEXT NOT NULL,
                PRIMARY KEY (region_id, interval_datetime)
            )
            """
        )
        base = dt.datetime(2026, 4, 14, 20, 0, 0)
        for index, value in enumerate(values):
            interval_dt = base + dt.timedelta(minutes=30 * index)
            conn.execute(
                """
                INSERT INTO operational_demand_actual_hh (
                    region_id,
                    interval_datetime,
                    operational_demand,
                    operational_demand_adjustment,
                    wdr_estimate,
                    lastchanged,
                    source_file
                ) VALUES (?, ?, ?, 0, 0, ?, ?)
                """,
                (
                    region,
                    interval_dt.strftime("%Y/%m/%d %H:%M:%S"),
                    value,
                    interval_dt.strftime("%Y/%m/%d %H:%M:%S"),
                    "test-operational-demand.csv",
                ),
            )
        conn.commit()


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


def seed_event_states(
    db: DatabaseManager,
    *,
    region: str,
    states: list[dict],
    market: str = "NEM",
):
    payload = []
    for idx, state in enumerate(states, start=1):
        state_type = state["state_type"]
        severity = state["severity"]
        payload.append(
            {
                "state_id": f"{market.lower()}-{region.lower()}-{state_type}-{idx}",
                "market": market,
                "region": region,
                "state_type": state_type,
                "start_time": state.get("start_time", "2026-04-15 10:00:00"),
                "end_time": state.get("end_time", "2026-04-15 18:00:00"),
                "severity": severity,
                "confidence": state.get("confidence", 0.9),
                "headline": state.get("headline", f"{region} {state_type}"),
                "impact_domains": state.get("impact_domains", ["grid_forecast"]),
                "evidence_event_ids": state.get("evidence_event_ids", [idx]),
                "evidence_summary_json": state.get("evidence_summary_json", [{"source": "test"}]),
            }
        )
    db.replace_grid_event_states(market, payload)


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


def seed_wem_forward_actuals(db: DatabaseManager):
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
                "2026-04-15 12:00:00",
                280.0,
                14.0, 10.0, 7.0, 5.0, 4.0,
                435.0, 437.0, 330.0, 332.0, 5966.0,
                980.0, 980.0, 981.0, 1055.0, 12124.5,
                110.0, 110.0, 258.0, 72.0, 12124.5,
                0.0, 0.0, 3.0, 0.0, 0.0,
                110.0, 110.0, 269.0, 72.0, 12124.5,
                1, 0, 0, 0, 0,
            ),
        )
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
                "2026-04-16 06:00:00",
                340.0,
                18.0, 11.0, 8.0, 5.0, 4.0,
                435.0, 437.0, 330.0, 332.0, 5966.0,
                980.0, 980.0, 981.0, 1055.0, 12124.5,
                110.0, 110.0, 258.0, 72.0, 12124.5,
                0.0, 0.0, 2.0, 0.0, 0.0,
                110.0, 110.0, 269.0, 72.0, 12124.5,
                1, 0, 0, 0, 0,
            ),
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

    def test_parse_as_of_uses_naive_utc_fallback_without_deprecation_warning(self):
        import grid_forecast

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            parsed = grid_forecast.parse_as_of(None)
        expected_utc_now = dt.datetime.now(dt.UTC).replace(tzinfo=None)

        deprecations = [
            warning for warning in captured
            if issubclass(warning.category, DeprecationWarning)
        ]
        self.assertEqual(deprecations, [])
        self.assertIsNone(parsed.tzinfo)
        self.assertLess(abs((expected_utc_now - parsed).total_seconds()), 5)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_24h_forecast_uses_predispatch_and_event_signals(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": -35.0, "demand_mw": 8900.0},
            {"time": "2026-04-15 18:00:00", "price": 420.0, "demand_mw": 12900.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_forward_nem_actuals(self.db, region="NSW1")
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
        self.assertEqual(result["baseline_forecast"]["availability_status"], "available")
        self.assertEqual(result["baseline_forecast"]["forecast_class"], "baseline_point_forecast")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_status"], "evaluated")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["calibration_status"], "baseline_only")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["calibration"]["status"], "baseline_only")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["calibration"]["sample_count"], 2)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["diagnostics"]["status"], "available")
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["diagnostics"]["error_grade"],
            {"high_error", "moderate_error", "low_error"},
        )
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["diagnostics"]["primary_gap_domain"],
            {"coverage", "probability", "bias", "balanced"},
        )
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["calibration"]["coverage_gap_80"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["calibration"]["coverage_gap_90"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["calibration"]["mean_error_aud_mwh"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["calibration"]["spike_probability_gap"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["calibration"]["negative_price_probability_gap"], float)
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["calibration"]["bias_direction"],
            {"underforecast", "overforecast", "neutral"},
        )
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["calibration"]["coverage_assessment_80"],
            {"under_covered", "well_calibrated", "over_covered"},
        )
        self.assertEqual(result["baseline_forecast"]["forecast_horizon_summary"]["horizon"], "24h")
        self.assertEqual(result["baseline_forecast"]["forecast_horizon_summary"]["forward_points"], 2)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["policy"], "walk_forward_required")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["walk_forward_mode"], "rolling_origin")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["sample_points_evaluated"], 2)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["window_count"], 2)
        self.assertEqual(len(result["baseline_forecast"]["evaluation"]["backtest_window"]["samples"]), 2)
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["backtest_window"]["samples"][0]["observed_price_state"],
            {"negative_price", "normal_price", "elevated_price", "price_spike"},
        )
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["actuals_dataset_family"], "settlement")
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["metrics"]["mae_aud_mwh"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["metrics"]["rmse_aud_mwh"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["metrics"]["pinball_loss_p50"], float)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["metrics"]["brier_score_spike"], float)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["regime_error_attribution"]["status"], "attributed")
        self.assertGreaterEqual(len(result["baseline_forecast"]["evaluation"]["regime_error_attribution"]["regime_buckets"]), 1)
        self.assertIn("reserve_tightness", result["baseline_forecast"]["regime_context"]["driver_tags"])
        self.assertGreaterEqual(result["baseline_forecast"]["probabilities"]["price_spike"], 0.7)
        self.assertGreaterEqual(result["baseline_forecast"]["probabilities"]["negative_price"], 0.4)
        self.assertGreaterEqual(result["baseline_forecast"]["probabilities"]["negative_price_duration_intervals"], 1)
        self.assertGreaterEqual(result["baseline_forecast"]["probabilities"]["negative_price_duration_hours"], 0.0)
        self.assertEqual(result["baseline_forecast"]["probabilities"]["duration_method"], "window_probability_scan_v1")
        self.assertEqual(result["baseline_forecast"]["quantile_scaffold"]["method"], "heuristic_regime_quantiles_v1")
        self.assertLess(
            result["baseline_forecast"]["quantile_scaffold"]["p10_price_aud_mwh"],
            result["baseline_forecast"]["quantile_scaffold"]["p50_price_aud_mwh"],
        )
        self.assertLess(
            result["baseline_forecast"]["quantile_scaffold"]["p50_price_aud_mwh"],
            result["baseline_forecast"]["quantile_scaffold"]["p90_price_aud_mwh"],
        )
        self.assertIn(
            "negative_price",
            {
                bucket["regime"]
                for bucket in result["baseline_forecast"]["evaluation"]["regime_error_attribution"]["regime_buckets"]
            },
        )
        self.assertIn(
            "price_spike",
            {
                bucket["regime"]
                for bucket in result["baseline_forecast"]["evaluation"]["regime_error_attribution"]["regime_buckets"]
            },
        )

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_24h_forecast_prioritizes_supply_network_reserve_pressure_over_recent_price_shape(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": 135.0, "demand_mw": 12100.0},
            {"time": "2026-04-15 18:00:00", "price": 185.0, "demand_mw": 13450.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_forward_nem_actuals(self.db, region="NSW1")
        seed_event_states(
            self.db,
            region="NSW1",
            states=[
                {"state_type": "supply_shock", "severity": "high", "headline": "Major coal outage"},
                {"state_type": "network_stress", "severity": "high", "headline": "Interconnector constraint cluster"},
                {"state_type": "reserve_tightness", "severity": "medium", "headline": "Reserve margin tightening"},
            ],
        )

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertGreaterEqual(result["summary"]["grid_stress_score"], 65)
        self.assertGreaterEqual(result["summary"]["price_spike_risk_score"], 55)
        self.assertGreaterEqual(result["summary"]["reserve_tightness_risk_score"], 55)
        self.assertIn("supply_shock", result["summary"]["driver_tags"])
        self.assertIn("network_stress", result["summary"]["driver_tags"])
        self.assertIn("reserve_tightness", result["summary"]["driver_tags"])
        self.assertGreaterEqual(result["market_context"]["major_generation_outage_score"], 70)
        self.assertGreaterEqual(result["market_context"]["major_network_outage_score"], 70)
        self.assertGreaterEqual(result["market_context"]["reserve_pressure_score"], 45)
        self.assertGreaterEqual(result["market_context"]["weather_load_stress_score"], 60)
        self.assertGreaterEqual(result["market_context"]["demand_level_vs_normal"], 0)
        self.assertLess(result["market_context"]["recent_price_max_aud_mwh"], 100.0)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_24h_forecast_keeps_negative_price_risk_low_without_negative_signals(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": 118.0, "demand_mw": 11800.0},
            {"time": "2026-04-15 18:00:00", "price": 142.0, "demand_mw": 12150.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertLess(result["summary"]["negative_price_risk_score"], 15)
        self.assertLess(result["summary"]["charge_window_score"], 20)
        self.assertGreaterEqual(result["market_context"]["demand_level_vs_normal"], 0)
        self.assertLess(result["market_context"]["demand_level_vs_normal"], 10)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_24h_forecast_does_not_treat_low_confidence_events_as_full_strength_pressure(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": 128.0, "demand_mw": 11800.0},
            {"time": "2026-04-15 18:00:00", "price": 148.0, "demand_mw": 12050.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_event_states(
            self.db,
            region="NSW1",
            states=[
                {
                    "state_type": "supply_shock",
                    "severity": "high",
                    "confidence": 0.1,
                    "headline": "Unverified unit outage chatter",
                }
            ],
        )

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertLess(result["market_context"]["major_generation_outage_score"], 25)
        self.assertLess(result["summary"]["grid_stress_score"], 45)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_24h_forecast_does_not_let_multiple_low_confidence_events_stack_into_high_pressure(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": 126.0, "demand_mw": 11820.0},
            {"time": "2026-04-15 18:00:00", "price": 146.0, "demand_mw": 12020.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_event_states(
            self.db,
            region="NSW1",
            states=[
                {
                    "state_type": "supply_shock",
                    "severity": "high",
                    "confidence": 0.1,
                    "headline": "Rumored outage A",
                },
                {
                    "state_type": "supply_shock",
                    "severity": "high",
                    "confidence": 0.1,
                    "headline": "Rumored outage B",
                },
                {
                    "state_type": "supply_shock",
                    "severity": "high",
                    "confidence": 0.1,
                    "headline": "Rumored outage C",
                },
            ],
        )

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertLess(result["market_context"]["major_generation_outage_score"], 20)
        self.assertLess(result["summary"]["grid_stress_score"], 40)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_long_horizon_switches_to_regime_outlook(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": -25.0, "demand_mw": 9100.0},
            {"time": "2026-04-15 18:00:00", "price": 280.0, "demand_mw": 12600.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_forward_nem_long_actuals(self.db, region="NSW1")
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
        self.assertEqual(weekly["baseline_forecast"]["forecast_horizon_summary"]["horizon"], "7d")
        self.assertEqual(weekly["baseline_forecast"]["forecast_horizon_summary"]["forward_points"], 0)
        self.assertEqual(monthly["baseline_forecast"]["forecast_horizon_summary"]["horizon"], "30d")
        self.assertEqual(monthly["baseline_forecast"]["evaluation"]["backtest_window"]["target_metric"], "price_aud_mwh")
        self.assertEqual(weekly["baseline_forecast"]["evaluation"]["backtest_window"]["walk_forward_mode"], "rolling_origin")
        self.assertGreaterEqual(weekly["baseline_forecast"]["evaluation"]["backtest_window"]["sample_points_evaluated"], 1)
        self.assertEqual(weekly["baseline_forecast"]["evaluation"]["backtest_status"], "evaluated")
        self.assertEqual(monthly["baseline_forecast"]["evaluation"]["backtest_status"], "evaluated")
        self.assertEqual(weekly["baseline_forecast"]["evaluation"]["calibration"]["status"], "baseline_only")
        self.assertEqual(weekly["baseline_forecast"]["evaluation"]["diagnostics"]["status"], "available")
        self.assertGreaterEqual(monthly["baseline_forecast"]["evaluation"]["calibration"]["sample_count"], 1)
        self.assertIn(
            weekly["baseline_forecast"]["evaluation"]["calibration"]["summary_grade"],
            {"poor", "mixed", "good"},
        )
        self.assertIn(
            monthly["baseline_forecast"]["evaluation"]["calibration"]["summary_grade"],
            {"poor", "mixed", "good"},
        )
        self.assertIsInstance(weekly["baseline_forecast"]["evaluation"]["metrics"]["coverage_80"], float)
        self.assertIsNotNone(monthly["baseline_forecast"]["evaluation"]["regime_error_attribution"]["primary_regime"])
        self.assertEqual(weekly["baseline_forecast"]["quantile_scaffold"]["method"], "heuristic_regime_quantiles_v1")
        self.assertEqual(monthly["baseline_forecast"]["quantile_scaffold"]["method"], "heuristic_regime_quantiles_v1")
        self.assertGreater(
            monthly["baseline_forecast"]["quantile_scaffold"]["band_width_aud_mwh"],
            weekly["baseline_forecast"]["quantile_scaffold"]["band_width_aud_mwh"],
        )
        self.assertIn("interconnector_stress_score", weekly["market_context"])
        self.assertIn("dominant_supply_availability_delta", monthly["market_context"])
        self.assertIn("maintenance_concentration_score", monthly["market_context"])
        self.assertIn("structural_load_growth_score", monthly["market_context"])

    @mock.patch("grid_forecast.fetch_nem_predispatch_window", return_value=[])
    def test_nem_long_horizon_keeps_regime_outlook_under_outage_and_network_pressure_without_price_extremes(self, mock_p5):
        import grid_forecast

        seed_recent_nem_history(self.db, region="NSW1")
        seed_forward_nem_long_actuals(self.db, region="NSW1")
        seed_event_states(
            self.db,
            region="NSW1",
            states=[
                {"state_type": "supply_shock", "severity": "high", "headline": "Generator maintenance cluster"},
                {"state_type": "network_stress", "severity": "medium", "headline": "Transmission outage risk"},
                {"state_type": "reserve_tightness", "severity": "medium", "headline": "Reserve outlook tightening"},
                {"state_type": "demand_weather_shock", "severity": "medium", "headline": "Industrial demand uplift"},
            ],
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

        self.assertGreaterEqual(weekly["summary"]["grid_stress_score"], 55)
        self.assertGreaterEqual(monthly["summary"]["grid_stress_score"], 55)
        self.assertIn("supply_shock", weekly["summary"]["driver_tags"])
        self.assertIn("network_stress", weekly["summary"]["driver_tags"])
        self.assertIn("reserve_tightness", weekly["summary"]["driver_tags"])
        self.assertGreaterEqual(weekly["market_context"]["major_generation_outage_score"], 70)
        self.assertGreaterEqual(weekly["market_context"]["interconnector_stress_score"], 45)
        self.assertGreaterEqual(monthly["market_context"]["maintenance_concentration_score"], 60)
        self.assertGreaterEqual(monthly["market_context"]["structural_load_growth_score"], 40)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window", return_value=[])
    def test_nem_long_horizon_keeps_negative_price_risk_low_without_negative_price_signals(self, mock_p5):
        import grid_forecast

        seed_recent_nem_history(self.db, region="NSW1")

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

        self.assertLess(weekly["summary"]["negative_price_risk_score"], 5)
        self.assertLess(monthly["summary"]["negative_price_risk_score"], 5)
        self.assertLess(weekly["summary"]["charge_window_score"], 8)
        self.assertLess(monthly["summary"]["charge_window_score"], 8)

    @mock.patch("grid_forecast.fetch_nem_predispatch_window", return_value=[])
    def test_nem_long_horizon_uses_recent_load_baseline_for_demand_level_vs_normal(self, mock_p5):
        import grid_forecast

        seed_recent_nem_history(self.db, region="NSW1")
        seed_operational_demand_actuals(self.db, region="NSW1", values=[9800.0, 9900.0, 10050.0, 12850.0])

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

        self.assertGreater(weekly["market_context"]["demand_level_vs_normal"], 20)
        self.assertLess(weekly["market_context"]["demand_level_vs_normal"], 35)
        self.assertAlmostEqual(
            weekly["market_context"]["demand_level_vs_normal"],
            monthly["market_context"]["demand_level_vs_normal"],
            delta=0.1,
        )

    def test_wem_forecast_returns_core_only_and_not_investment_grade(self):
        import grid_forecast

        seed_wem_slim_history(self.db)
        seed_wem_forward_actuals(self.db)
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
        self.assertEqual(result["baseline_forecast"]["availability_status"], "available")
        self.assertEqual(result["baseline_forecast"]["coverage_mode"], "core_only")
        self.assertEqual(result["baseline_forecast"]["forecast_horizon_summary"]["horizon"], "7d")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_status"], "evaluated")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["calibration"]["status"], "baseline_only")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["diagnostics"]["status"], "available")
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["calibration"]["spike_probability_assessment"],
            {"understated", "well_calibrated", "overstated"},
        )
        self.assertIn(
            result["baseline_forecast"]["evaluation"]["calibration"]["summary_grade"],
            {"poor", "mixed", "good"},
        )
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["policy"], "walk_forward_required")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["walk_forward_mode"], "rolling_origin")
        self.assertGreaterEqual(result["baseline_forecast"]["evaluation"]["backtest_window"]["sample_points_evaluated"], 1)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["regime_error_attribution"]["status"], "attributed")
        self.assertIn("wem_constraint_tightness", result["baseline_forecast"]["regime_context"]["driver_tags"])
        self.assertIn("core_only_coverage", result["baseline_forecast"]["warnings"])
        self.assertEqual(result["baseline_forecast"]["quantile_scaffold"]["method"], "heuristic_regime_quantiles_v1")
        self.assertEqual(result["baseline_forecast"]["probabilities"]["duration_method"], "window_probability_scan_v1")
        self.assertIn(
            "price_spike",
            {
                bucket["regime"]
                for bucket in result["baseline_forecast"]["evaluation"]["regime_error_attribution"]["regime_buckets"]
            },
        )
        self.assertGreaterEqual(result["market_context"]["reserve_pressure_score"], 20)
        self.assertGreaterEqual(result["market_context"]["interconnector_stress_score"], 0)
        self.assertIn("wem_shortfall_signal", result["summary"]["driver_tags"])

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_nem_forecast_handles_missing_trading_price_tables_without_500(self, mock_p5):
        import grid_forecast

        mock_p5.return_value = []

        result = grid_forecast.get_grid_forecast_response(
            self.db,
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of="2026-04-15 09:07:00",
        )

        self.assertEqual(result["metadata"]["coverage_quality"], "partial")
        self.assertEqual(result["coverage"]["source_status"]["recent_market_history"], "missing")
        self.assertEqual(result["coverage"]["source_status"]["nem_predispatch"], "missing")
        self.assertEqual(result["coverage"]["recent_history_points"], 0)

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
        self.assertIn("baseline_forecast", result)
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

    def test_p2_forecast_layer_route_returns_stable_contract(self):
        fake_forecast = {
            "metadata": {"market": "NEM", "region": "NSW1", "horizon": "24h", "forecast_mode": "hybrid_signal_calibrated"},
            "coverage": {"mode": "full", "forward_points": 2, "event_count": 1},
            "market_context": {"forward_price_min_aud_mwh": -20.0, "forward_price_max_aud_mwh": 390.0},
            "summary": {"grid_stress_score": 81, "driver_tags": ["scarcity"]},
            "windows": [],
            "drivers": [],
            "baseline_forecast": {
                "availability_status": "available",
                "forecast_class": "baseline_point_forecast",
                "forecast_horizon_summary": {"horizon": "24h", "forward_points": 2},
                "evaluation": {"backtest_status": "evaluated", "metrics": {"mae_aud_mwh": 25.5}},
                "regime_context": {"primary_regime": "scarcity", "availability_status": "available", "driver_tags": ["scarcity"]},
                "probabilities": {"price_spike": 0.7, "negative_price": 0.4},
            },
            "regime_layer": {"primary_regime": {"regime": "scarcity"}},
            "regime_compact": {"availability_status": "available", "primary_regime": {"regime": "scarcity"}},
        }
        with patched_server_db(self.db), mock.patch("server.get_grid_forecast", return_value=fake_forecast):
            result = server.get_p2_forecast_layer(market="NEM", region="NSW1", horizon="24h", as_of=None)

        self.assertEqual(result["market"], "NEM")
        self.assertEqual(result["region"], "NSW1")
        self.assertEqual(result["horizon"], "24h")
        self.assertEqual(result["summary"]["grid_stress_score"], 81)
        self.assertEqual(result["windows"], [])
        self.assertEqual(result["market_context"]["forward_price_max_aud_mwh"], 390.0)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_status"], "evaluated")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["calibration"]["status"], "baseline_only")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["diagnostics"]["status"], "available")
        self.assertEqual(result["baseline_forecast"]["probabilities"]["duration_method"], "window_probability_scan_v1")
        self.assertEqual(result["baseline_forecast"]["regime_context"]["primary_regime"], "scarcity")
        self.assertEqual(result["regime_compact"]["primary_regime"]["regime"], "scarcity")
        self.assertEqual(result["metadata"]["dataset_family"], "forecast_layer")
        self.assertEqual(result["coverage_mode"], "full")
        self.assertEqual(result["regulatory_scope"], "NEM")
        self.assertEqual(result["result_type"], "opportunity_outlook")
        self.assertEqual(
            result["market_design_context"],
            "NEM forward opportunity outlook grounded in official price windows, regime persistence, and event overlays.",
        )
        self.assertEqual(
            result["value_stream_coverage"],
            ["energy_arbitrage", "negative_price_windows", "reserve_proxy"],
        )
        self.assertIn("governance", result)
        self.assertEqual(result["governance"]["forecast_value_attribution"]["status"], "proxy_available")
        self.assertEqual(result["governance"]["forecast_value_attribution"]["method"], "backtest_error_proxy_v1")
        self.assertIn("overall_information_value_index", result["governance"]["forecast_value_attribution"])
        self.assertEqual(result["governance"]["disclaimer"]["investment_grade"], False)
        self.assertIn("freshness", result["governance"])
        self.assertIn("drift", result["governance"])

    @mock.patch("grid_forecast.fetch_nem_predispatch_window")
    def test_p2_forecast_layer_route_exposes_evaluated_baseline_for_nem_24h(self, mock_p5):
        mock_p5.return_value = [
            {"time": "2026-04-15 12:00:00", "price": -35.0, "demand_mw": 8900.0},
            {"time": "2026-04-15 18:00:00", "price": 420.0, "demand_mw": 12900.0},
        ]
        seed_recent_nem_history(self.db, region="NSW1")
        seed_forward_nem_actuals(self.db, region="NSW1")
        seed_event_state(self.db, region="NSW1", state_type="reserve_tightness", severity="high")

        with patched_server_db(self.db):
            result = server.get_p2_forecast_layer(market="NEM", region="NSW1", horizon="24h", as_of="2026-04-15 09:07:00")

        self.assertEqual(result["metadata"]["dataset_family"], "forecast_layer")
        self.assertIn("summary", result)
        self.assertIn("windows", result)
        self.assertEqual(result["baseline_forecast"]["evaluation"]["backtest_status"], "evaluated")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["calibration"]["status"], "baseline_only")
        self.assertEqual(result["baseline_forecast"]["evaluation"]["diagnostics"]["status"], "available")
        self.assertGreaterEqual(result["baseline_forecast"]["probabilities"]["negative_price_duration_intervals"], 1)
        self.assertIsInstance(result["baseline_forecast"]["evaluation"]["metrics"]["mae_aud_mwh"], float)
        self.assertIn(result["regime_compact"]["availability_status"], {"available", "unavailable"})
        self.assertIn(result["governance"]["drift"]["status"], {"monitor", "elevated"})
        self.assertEqual(result["governance"]["forecast_value_attribution"]["status"], "proxy_available")
        self.assertGreaterEqual(result["governance"]["forecast_value_attribution"]["overall_information_value_index"], 0.0)
        self.assertEqual(result["governance"]["disclaimer"]["usage_scope"], "research_and_operational_support_only")
        self.assertEqual(result["result_type"], "opportunity_outlook")

    @mock.patch("server._fetch_recent_grid_state_rows", return_value=[])
    @mock.patch("server._fetch_latest_nem_region_prices", return_value={})
    @mock.patch("grid_forecast.fetch_nem_predispatch_window", return_value=[])
    def test_p2_forecast_layer_keeps_regime_compact_available_when_optional_p1_tables_are_missing(
        self,
        mock_p5,
        mock_latest_prices,
        mock_states,
    ):
        seed_recent_nem_history(self.db, region="NSW1")

        with patched_server_db(self.db):
            result = server.get_p2_forecast_layer(market="NEM", region="NSW1", horizon="7d", as_of="2026-04-15 09:07:00")

        self.assertEqual(result["regime_compact"]["availability_status"], "available")
        self.assertEqual(result["baseline_forecast"]["regime_context"]["availability_status"], "available")
        self.assertEqual(result["metadata"]["result_type"], "opportunity_outlook")


if __name__ == "__main__":
    unittest.main()
