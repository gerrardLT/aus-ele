import unittest
from unittest import mock
from types import SimpleNamespace

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from result_metadata import build_result_metadata
import server


class ResultMetadataTests(unittest.TestCase):
    def test_build_result_metadata_returns_required_fields(self):
        payload = build_result_metadata(
            market="NEM",
            region_or_zone="NSW1",
            timezone="Australia/Sydney",
            currency="AUD",
            unit="AUD/MWh",
            interval_minutes=5,
            data_grade="analytical",
            data_quality_score=0.94,
            coverage={"expected_intervals": 288, "actual_intervals": 288, "coverage_ratio": 1.0},
            freshness={"lag_minutes": 15, "last_updated_at": "2026-04-27T00:15:00Z"},
            source_name="AEMO",
            source_version="2026-04-27",
            methodology_version="price_trend_v1",
            warnings=[],
        )

        self.assertEqual(payload["market"], "NEM")
        self.assertEqual(payload["region_or_zone"], "NSW1")
        self.assertEqual(payload["currency"], "AUD")
        self.assertEqual(payload["unit"], "AUD/MWh")
        self.assertEqual(payload["data_grade"], "analytical")
        self.assertIn("coverage", payload)
        self.assertIn("freshness", payload)
        self.assertIn("methodology_version", payload)

    def test_build_result_metadata_uses_empty_defaults_for_none_fields(self):
        payload = build_result_metadata(
            market="NEM",
            region_or_zone="QLD1",
            timezone="Australia/Brisbane",
            currency="AUD",
            unit="AUD/MWh",
            interval_minutes=5,
            data_grade="analytical",
            data_quality_score=None,
            coverage=None,
            freshness=None,
            source_name="AEMO",
            source_version="2026-04-27",
            methodology_version="price_trend_v1",
            warnings=None,
        )

        self.assertEqual(payload["coverage"], {})
        self.assertEqual(payload["freshness"], {})
        self.assertEqual(payload["warnings"], [])

    def test_build_result_metadata_snapshots_mutable_inputs(self):
        coverage = {"expected_intervals": 288}
        freshness = {"lag_minutes": 15}
        warnings = ["stale_source"]

        payload = build_result_metadata(
            market="NEM",
            region_or_zone="VIC1",
            timezone="Australia/Melbourne",
            currency="AUD",
            unit="AUD/MWh",
            interval_minutes=5,
            data_grade="analytical",
            data_quality_score=0.9,
            coverage=coverage,
            freshness=freshness,
            source_name="AEMO",
            source_version="2026-04-27",
            methodology_version="price_trend_v1",
            warnings=warnings,
        )

        coverage["expected_intervals"] = 1
        freshness["lag_minutes"] = 999
        warnings.append("late_update")

        self.assertEqual(payload["coverage"], {"expected_intervals": 288})
        self.assertEqual(payload["freshness"], {"lag_minutes": 15})
        self.assertEqual(payload["warnings"], ["stale_source"])


class ApiMetadataIntegrationTests(unittest.TestCase):
    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._store_response_cache", side_effect=lambda scope, payload, response_payload, ttl_seconds: response_payload)
    @mock.patch("server._fetch_response_cache", return_value=None)
    def test_price_trend_response_contains_metadata(self, mock_cache_get, mock_cache_store, mock_updated_at):
        with mock.patch("server.db.get_connection") as mock_get_connection:
            mock_conn = mock.MagicMock()
            mock_cursor = mock.MagicMock()
            mock_get_connection.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [
                (1,),
                (1,),
                (55.0, 55.0, 55.0, 0, None, None, 55.0, 55.0, 0, 0),
            ]
            mock_cursor.fetchall.side_effect = [
                [("2026-04-01 00:00:00", 55.0)],
                [],
            ]

            payload = server.get_price_trend(year=2026, region="NSW1", limit=1500)

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical")
        self.assertEqual(payload["metadata"]["currency"], "AUD")
        self.assertEqual(payload["metadata"]["timezone"], "Australia/Sydney")
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["source_version"], "2026-04-27 00:10:00")
        self.assertEqual(
            payload["metadata"]["freshness"]["last_updated_at"],
            "2026-04-27 00:10:00",
        )

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._fetch_response_cache")
    def test_price_trend_cache_hit_attaches_metadata_contract(self, mock_cache_get, mock_updated_at):
        mock_cache_get.return_value = {
            "region": "QLD1",
            "year": 2026,
            "month": None,
            "total_points": 1,
            "returned_points": 1,
            "stats": {"min": 55.0, "max": 55.0, "avg": 55.0},
            "advanced_stats": {
                "neg_ratio": 0,
                "neg_avg": 0,
                "neg_min": 0,
                "pos_avg": 55.0,
                "pos_max": 55.0,
                "days_below_100": 0,
                "days_above_300": 0,
            },
            "hourly_distribution": [],
            "data": [{"datetime": "2026-04-01 00:00:00", "price": 55.0}],
        }

        payload = server.get_price_trend(year=2026, region="QLD1", limit=1500)

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["timezone"], "Australia/Brisbane")
        self.assertEqual(payload["metadata"]["region_or_zone"], "QLD1")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["source_version"], "2026-04-27 00:10:00")
        self.assertEqual(
            payload["metadata"]["freshness"]["last_updated_at"],
            "2026-04-27 00:10:00",
        )

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._store_response_cache", side_effect=lambda scope, payload, response_payload, ttl_seconds: response_payload)
    @mock.patch("server._fetch_response_cache", return_value=None)
    def test_hourly_price_profile_response_contains_metadata(self, mock_cache_get, mock_cache_store, mock_updated_at):
        with mock.patch("server.db.get_connection") as mock_get_connection:
            mock_conn = mock.MagicMock()
            mock_cursor = mock.MagicMock()
            mock_get_connection.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [
                (1,),
            ]
            mock_cursor.fetchall.return_value = [
                (0, 55.0, 45.0, 65.0, 12, 0, None),
            ]

            payload = server.get_hourly_price_profile(year=2026, region="NSW1", month="04")

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["market"], "NEM")
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["metadata"]["currency"], "AUD")
        self.assertEqual(payload["metadata"]["unit"], "AUD/MWh")
        self.assertEqual(payload["metadata"]["timezone"], "Australia/Sydney")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["source_version"], "2026-04-27 00:10:00")
        self.assertEqual(
            payload["metadata"]["freshness"]["last_updated_at"],
            "2026-04-27 00:10:00",
        )

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._fetch_response_cache")
    def test_hourly_price_profile_cache_hit_attaches_metadata_contract(self, mock_cache_get, mock_updated_at):
        mock_cache_get.return_value = {
            "region": "QLD1",
            "year": 2026,
            "month": "04",
            "hourly": [{
                "hour": 0,
                "avg_price": 55.0,
                "min_price": 45.0,
                "max_price": 65.0,
                "count": 12,
                "neg_pct": 0,
                "neg_avg": None,
            }],
        }

        payload = server.get_hourly_price_profile(year=2026, region="QLD1", month="04")

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["market"], "NEM")
        self.assertEqual(payload["metadata"]["region_or_zone"], "QLD1")
        self.assertEqual(payload["metadata"]["timezone"], "Australia/Brisbane")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["methodology_version"], "hourly_price_profile_v1")
        self.assertEqual(
            payload["metadata"]["freshness"]["last_updated_at"],
            "2026-04-27 00:10:00",
        )

    def test_fingrid_status_contains_data_grade(self):
        with mock.patch("server.fingrid_service.get_dataset_status_payload") as mock_status:
            mock_status.return_value = {"status": {"dataset_id": "317"}}

            payload = server.get_fingrid_dataset_status("317")

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical-preview")
        self.assertEqual(payload["metadata"]["timezone"], "Europe/Helsinki")
        self.assertEqual(payload["metadata"]["region_or_zone"], "317")
        self.assertIsNone(payload["metadata"]["interval_minutes"])
        self.assertEqual(payload["metadata"]["source_version"], "fcrn_hourly_market_price")
        self.assertNotIn("last_updated_at", payload["metadata"]["freshness"])

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._fetch_response_cache")
    def test_event_overlays_cache_hit_attaches_standard_metadata_contract(self, mock_cache_get, mock_updated_at):
        mock_cache_get.return_value = {
            "metadata": {
                "market": "NEM",
                "region": "NSW1",
                "coverage_quality": "full",
                "sources_used": ["nem_market_notice"],
                "time_granularity": "interval",
                "no_verified_event_explanation": False,
                "filters": {"year": 2026, "month": "04", "quarter": None, "day_type": None},
            },
            "states": [{"state_id": "evt-1"}],
            "daily_rollup": [],
            "events": [],
        }

        payload = server.get_event_overlays(
            year=2026,
            region="NSW1",
            market="NEM",
            month="04",
            quarter=None,
            day_type=None,
        )

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["market"], "NEM")
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["metadata"]["timezone"], "Australia/Sydney")
        self.assertEqual(payload["metadata"]["currency"], "AUD")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["coverage_quality"], "full")
        self.assertEqual(payload["metadata"]["time_granularity"], "interval")
        self.assertEqual(
            payload["metadata"]["freshness"]["last_updated_at"],
            "2026-04-27 00:10:00",
        )

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._fetch_response_cache")
    def test_grid_forecast_cache_hit_attaches_standard_metadata_contract(self, mock_cache_get, mock_updated_at):
        mock_cache_get.return_value = {
            "metadata": {
                "market": "NEM",
                "region": "NSW1",
                "horizon": "24h",
                "forecast_mode": "hybrid_signal_calibrated",
                "coverage_quality": "full",
                "issued_at": "2026-04-27 00:00:00",
                "as_of": "2026-04-27 00:00:00",
                "confidence_band": "medium",
                "sources_used": ["recent_market_history", "nem_predispatch"],
                "investment_grade": False,
                "warnings": [],
            },
            "summary": {"grid_stress_score": 81},
            "coverage": {"source_status": {"nem_predispatch": "ok"}},
            "market_context": {},
            "windows": [],
            "drivers": [],
        }

        payload = server.get_grid_forecast(market="NEM", region="NSW1", horizon="24h", as_of=None)

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["market"], "NEM")
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["metadata"]["timezone"], "Australia/Sydney")
        self.assertEqual(payload["metadata"]["currency"], "AUD")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["forecast_mode"], "hybrid_signal_calibrated")
        self.assertEqual(payload["metadata"]["coverage_quality"], "full")
        self.assertEqual(
            payload["metadata"]["freshness"]["last_updated_at"],
            "2026-04-27 00:10:00",
        )

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    def test_investment_analysis_response_contains_metadata(self, mock_updated_at):
        fake_metrics = SimpleNamespace(
            total_capex=100.0,
            model_dump=lambda: {
            "npv": 1.0,
            "irr": 0.1,
            "roi_pct": 10.0,
            "payback_years": 5,
            "total_capex": 100.0,
            "debt_capacity": 0.0,
            "levered_irr": None,
            "dscr_avg": 0.0,
            },
        )
        fake_result = SimpleNamespace(metrics=fake_metrics, cash_flows=[])

        params = server.InvestmentParams(region="NSW1", power_mw=100, duration_hours=4, backtest_years=[2025])
        response = server._build_investment_response(
            params=params,
            base_result=fake_result,
            scenarios=[],
            mc_result=None,
            baseline_arbitrage=1000.0,
            arbitrage_baseline_source="observed_net_revenue",
            baseline_fcas=200.0,
            fcas_baseline_source="manual_input",
            backtest_summary={
                "backtest_mode": "optimized_hindsight",
                "revenue_scope": "trajectory_gross_energy",
                "avg_annual_arbitrage_raw": 1000.0,
                "avg_annual_arbitrage_net": 900.0,
                "avg_annual_cycles": 12.5,
                "backtest_reference": {
                    "methodology_version": "bess_backtest_v1",
                    "inputs": [{"market": "NEM", "region": "NSW1", "year": 2025}],
                    "drivers": [{"methodology_version": "bess_backtest_v1"}],
                },
            },
        )

        self.assertIn("metadata", response)
        self.assertEqual(response["metadata"]["market"], "NEM")
        self.assertEqual(response["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(response["metadata"]["currency"], "AUD")
        self.assertEqual(response["metadata"]["unit"], "AUD/year")
        self.assertEqual(response["metadata"]["timezone"], "Australia/Sydney")
        self.assertIsNone(response["metadata"]["interval_minutes"])
