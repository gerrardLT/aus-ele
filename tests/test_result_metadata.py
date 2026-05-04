import unittest
from unittest import mock
from types import SimpleNamespace

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from result_metadata import build_result_metadata
import server


class ResultMetadataTests(unittest.TestCase):
    def test_build_result_metadata_supports_grade_lineage_and_contract_fields(self):
        payload = build_result_metadata(
            market="NEM",
            region_or_zone="NSW1",
            timezone="Australia/Sydney",
            currency="AUD",
            unit="MW",
            interval_minutes=30,
            data_grade="preview",
            data_quality_score=0.87,
            coverage={"coverage_ratio": 0.92},
            freshness={"last_updated_at": "2026-04-30T00:00:00Z"},
            source_name="AEMO",
            source_version="p0_test_v1",
            methodology_version="p0_contract_v1",
            warnings=["source_partial"],
            dataset_family="load_forecast",
            observation_kind="forecast",
            lineage={"source_id": "aemo_operational_demand"},
            grade="preview",
        )

        self.assertEqual(payload["dataset_family"], "load_forecast")
        self.assertEqual(payload["observation_kind"], "forecast")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_operational_demand")
        self.assertEqual(payload["grade"], "preview")

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
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._store_response_cache", side_effect=lambda scope, payload, response_payload, ttl_seconds: response_payload)
    @mock.patch("server._fetch_response_cache", return_value=None)
    def test_price_trend_response_contains_metadata(self, mock_cache_get, mock_cache_store, mock_regime_layer, mock_updated_at):
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "scarcity", "score": 66.0, "confidence": 0.75},
            "active_regimes": [{"regime": "scarcity", "score": 66.0, "confidence": 0.75}],
            "regime_score_map": {"scarcity": 66.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
        }
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
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "scarcity")
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_price_trend_cache_hit_attaches_metadata_contract(self, mock_cache_get, mock_regime_layer, mock_updated_at):
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
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "oversupply", "score": 72.0, "confidence": 0.79},
            "active_regimes": [{"regime": "oversupply", "score": 72.0, "confidence": 0.79}],
            "regime_score_map": {"oversupply": 72.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
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
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "oversupply")
        self.assertEqual(payload["regime_compact"]["primary_regime"]["regime"], "oversupply")
        self.assertEqual(payload["regime_compact"]["availability_status"], "available")
        mock_regime_layer.assert_called_once_with(market="NEM", region="QLD1")

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_price_trend_cache_hit_preserves_response_when_regime_unavailable(self, mock_cache_get, mock_regime_layer, mock_updated_at):
        mock_cache_get.return_value = {
            "region": "NSW1",
            "year": 2026,
            "month": None,
            "total_points": 1,
            "returned_points": 1,
            "stats": {"min": 42.0, "max": 42.0, "avg": 42.0},
            "advanced_stats": {
                "neg_ratio": 0,
                "neg_avg": 0,
                "neg_min": 0,
                "pos_avg": 42.0,
                "pos_max": 42.0,
                "days_below_100": 1,
                "days_above_300": 0,
            },
            "hourly_distribution": [],
            "data": [{"datetime": "2026-04-01 00:00:00", "price": 42.0}],
        }
        mock_regime_layer.return_value = server._build_unavailable_regime_layer_payload(market="NEM", region="NSW1")

        payload = server.get_price_trend(year=2026, region="NSW1", limit=1500)

        self.assertEqual(payload["stats"]["avg"], 42.0)
        self.assertEqual(payload["regime_compact"]["availability_status"], "unavailable")
        self.assertIsNone(payload["regime_compact"]["primary_regime"])
        self.assertIn("regime_layer_unavailable", payload["regime_compact"]["warnings"])
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

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
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_hourly_price_profile_cache_hit_attaches_metadata_contract(self, mock_cache_get, mock_regime_layer, mock_updated_at):
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
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "oversupply", "score": 59.0, "confidence": 0.68},
            "active_regimes": [{"regime": "oversupply", "score": 59.0, "confidence": 0.68}],
            "regime_score_map": {"oversupply": 59.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
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
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "oversupply")
        mock_regime_layer.assert_called_once_with(market="NEM", region="QLD1")

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_peak_analysis_cache_hit_attaches_regime_layer(self, mock_cache_get, mock_regime_layer, mock_updated_at):
        mock_cache_get.return_value = {
            "region": "NSW1",
            "year": 2026,
            "aggregation": "daily",
            "network_fee": 12.0,
            "data": [{"date": "2026-04-01", "spread_2h": 110.0}],
            "summary": {"best_spread_2h": 110.0},
        }
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "scarcity", "score": 64.0, "confidence": 0.73},
            "active_regimes": [{"regime": "scarcity", "score": 64.0, "confidence": 0.73}],
            "regime_score_map": {"scarcity": 64.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
        }

        payload = server.get_peak_analysis(year=2026, region="NSW1", aggregation="daily", network_fee=12.0)

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "scarcity")
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

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
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_event_overlays_cache_hit_attaches_standard_metadata_contract(self, mock_cache_get, mock_regime_layer, mock_updated_at):
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
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "oversupply", "score": 77.0, "confidence": 0.82},
            "active_regimes": [{"regime": "oversupply", "score": 77.0, "confidence": 0.82}],
            "regime_score_map": {"oversupply": 77.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
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
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "oversupply")
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_grid_forecast_cache_hit_attaches_standard_metadata_contract(self, mock_cache_get, mock_regime_layer, mock_updated_at):
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
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "scarcity", "score": 68.0, "confidence": 0.71},
            "active_regimes": [{"regime": "scarcity", "score": 68.0, "confidence": 0.71}],
            "regime_score_map": {"scarcity": 68.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
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
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "scarcity")
        self.assertEqual(payload["baseline_forecast"]["regime_context"]["primary_regime"], "scarcity")
        self.assertEqual(payload["baseline_forecast"]["regime_context"]["availability_status"], "available")
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._build_regime_layer_payload")
    @mock.patch("server._fetch_response_cache")
    def test_fcas_analysis_cache_hit_attaches_regime_layer(self, mock_cache_get, mock_regime_layer, mock_updated_at):
        mock_cache_get.return_value = {
            "region": "NSW1",
            "year": 2026,
            "has_fcas_data": True,
            "aggregation": "daily",
            "summary": {"total_avg_fcas_price": 21.4},
            "hourly": [],
            "service_breakdown": [],
            "data": [],
        }
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "reserve_stress", "score": 71.0, "confidence": 0.77},
            "active_regimes": [{"regime": "reserve_stress", "score": 71.0, "confidence": 0.77}],
            "regime_score_map": {"reserve_stress": 71.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
        }

        payload = server.get_fcas_analysis(year=2026, region="NSW1", aggregation="daily", capacity_mw=100)

        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["metadata"]["interval_minutes"], 5)
        self.assertEqual(payload["regime_layer"]["primary_regime"]["regime"], "reserve_stress")
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server.get_grid_forecast")
    def test_p2_forecast_layer_response_contains_metadata_contract(self, mock_get_grid_forecast, mock_updated_at):
        mock_get_grid_forecast.return_value = {
            "metadata": {"horizon": "24h"},
            "coverage": {"mode": "full", "forward_points": 2},
            "market_context": {"forward_price_max_aud_mwh": 420.0},
            "drivers": [],
            "baseline_forecast": {
                "availability_status": "available",
                "warnings": [],
                "evaluation": {
                    "backtest_status": "evaluated",
                    "calibration_status": "baseline_only",
                    "calibration": {"status": "baseline_only", "sample_count": 2},
                },
            },
            "regime_compact": {"availability_status": "available"},
        }

        payload = server.get_p2_forecast_layer(market="NEM", region="NSW1", horizon="24h", as_of=None)

        self.assertEqual(payload["metadata"]["dataset_family"], "forecast_layer")
        self.assertEqual(payload["metadata"]["observation_kind"], "forecast")
        self.assertEqual(payload["metadata"]["grade"], "analytical-preview")
        self.assertEqual(payload["metadata"]["region_or_zone"], "NSW1")
        self.assertEqual(payload["baseline_forecast"]["evaluation"]["calibration"]["status"], "baseline_only")

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
            p3_decision=None,
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

    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    @mock.patch("server._build_regime_layer_payload")
    def test_investment_analysis_response_attaches_regime_contracts(self, mock_regime_layer, mock_updated_at):
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
        mock_regime_layer.return_value = {
            "primary_regime": {"regime": "scarcity", "score": 74.0, "confidence": 0.79},
            "active_regimes": [{"regime": "scarcity", "score": 74.0, "confidence": 0.79}],
            "regime_score_map": {"scarcity": 74.0},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
        }

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
            p3_decision=None,
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

        self.assertEqual(response["regime_layer"]["primary_regime"]["regime"], "scarcity")
        self.assertEqual(response["regime_compact"]["primary_regime"]["regime"], "scarcity")
        self.assertEqual(response["regime_compact"]["availability_status"], "available")
        mock_regime_layer.assert_called_once_with(market="NEM", region="NSW1")

    def test_investment_analysis_response_includes_p3_decision_summary_when_available(self):
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
            p3_decision={
                "decision_summary": {"recommended_strategy": "forecast_driven_dispatch"},
                "strategy_bundle": {
                    "forecast_driven_dispatch": {"net_revenue": 1250.0},
                    "stochastic_dispatch": {"scenario_spread": 140.0},
                },
                "revenue_attribution": {
                    "timing_alpha": 80.0,
                    "regime_capture_alpha": 40.0,
                    "fcas_stack_proxy": 30.0,
                    "net_revenue_after_decision_adjustments": 1250.0,
                },
            },
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

        self.assertIn("p3_decision", response)
        self.assertEqual(response["p3_decision"]["decision_summary"]["recommended_strategy"], "forecast_driven_dispatch")
        self.assertEqual(response["decision_adjusted_revenue"]["net_revenue"], 1250.0)
        self.assertEqual(response["decision_adjusted_revenue"]["scenario_spread"], 140.0)
        self.assertIn("decision_adjusted_metrics", response)
        self.assertGreater(response["decision_adjusted_metrics"]["npv"], response["base_metrics"]["npv"])
        self.assertGreater(response["decision_adjusted_metrics"]["roi_pct"], response["base_metrics"]["roi_pct"])
        self.assertNotIn("decision_adjusted_cash_flows", response)

    def test_investment_analysis_response_includes_decision_adjusted_scenarios_when_available(self):
        base_metrics = SimpleNamespace(
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
        adjusted_metrics = SimpleNamespace(
            model_dump=lambda: {
                "npv": 2.0,
                "irr": 0.12,
                "roi_pct": 12.0,
                "payback_years": 4,
                "total_capex": 100.0,
                "debt_capacity": 0.0,
                "levered_irr": None,
                "dscr_avg": 0.0,
            },
        )
        adjusted_cash_flows = [
            SimpleNamespace(
                model_dump=lambda: {
                    "year": 1,
                    "revenue_arbitrage": 100.0,
                    "revenue_fcas": 20.0,
                    "revenue_capacity": 0.0,
                    "total_revenue": 120.0,
                    "opex": 10.0,
                    "augmentation_capex": 0.0,
                    "net_cash_flow": 110.0,
                    "debt_service": 0.0,
                    "levered_cash_flow": 110.0,
                    "cumulative_cash_flow": -90.0,
                    "state_of_health": 0.99,
                    "annual_cycles": 150.0,
                },
            ),
        ]
        fake_base_result = SimpleNamespace(metrics=base_metrics, cash_flows=[])
        decision_adjusted_base = SimpleNamespace(
            scenario_name="Base",
            metrics=adjusted_metrics,
            cash_flows=adjusted_cash_flows,
            model_dump=lambda: {
                "scenario_name": "Base",
                "metrics": adjusted_metrics.model_dump(),
                "cash_flows": [row.model_dump() for row in adjusted_cash_flows],
            },
        )
        decision_adjusted_bull = SimpleNamespace(
            scenario_name="Bull",
            metrics=SimpleNamespace(
                model_dump=lambda: {
                    "npv": 3.0,
                    "irr": 0.15,
                    "roi_pct": 15.0,
                    "payback_years": 4,
                    "total_capex": 100.0,
                    "debt_capacity": 0.0,
                    "levered_irr": None,
                    "dscr_avg": 0.0,
                },
            ),
            cash_flows=[],
            model_dump=lambda: {
                "scenario_name": "Bull",
                "metrics": {
                    "npv": 3.0,
                    "irr": 0.15,
                    "roi_pct": 15.0,
                    "payback_years": 4,
                    "total_capex": 100.0,
                    "debt_capacity": 0.0,
                    "levered_irr": None,
                    "dscr_avg": 0.0,
                },
                "cash_flows": [],
            },
        )
        params = server.InvestmentParams(region="NSW1", power_mw=100, duration_hours=4, backtest_years=[2025])

        response = server._build_investment_response(
            params=params,
            base_result=fake_base_result,
            scenarios=[],
            mc_result=None,
            baseline_arbitrage=1000.0,
            arbitrage_baseline_source="observed_net_revenue",
            baseline_fcas=200.0,
            fcas_baseline_source="manual_input",
            p3_decision={
                "decision_summary": {"recommended_strategy": "forecast_driven_dispatch"},
                "strategy_bundle": {
                    "forecast_driven_dispatch": {"net_revenue": 1250.0},
                    "stochastic_dispatch": {"scenario_spread": 140.0},
                },
                "revenue_attribution": {
                    "timing_alpha": 80.0,
                    "regime_capture_alpha": 40.0,
                    "fcas_stack_proxy": 30.0,
                    "net_revenue_after_decision_adjustments": 1250.0,
                },
            },
            decision_adjusted_result=decision_adjusted_base,
            decision_adjusted_scenarios=[decision_adjusted_base, decision_adjusted_bull],
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

        self.assertIn("decision_adjusted_scenarios", response)
        self.assertEqual(len(response["decision_adjusted_scenarios"]), 2)
        self.assertEqual(response["decision_adjusted_scenarios"][0]["scenario_name"], "Base")
        self.assertEqual(response["decision_adjusted_scenarios"][1]["scenario_name"], "Bull")
        self.assertIn("decision_adjusted_cash_flows", response)
        self.assertEqual(response["decision_adjusted_cash_flows"][0]["total_revenue"], 120.0)

    def test_investment_analysis_response_includes_decision_adjusted_monte_carlo_when_available(self):
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
            mc_result=SimpleNamespace(
                model_dump=lambda: {
                    "npv_p10": -1.0,
                    "npv_p50": 1.0,
                    "npv_p90": 3.0,
                    "irr_p10": 0.03,
                    "irr_p50": 0.1,
                    "irr_p90": 0.18,
                },
            ),
            baseline_arbitrage=1000.0,
            arbitrage_baseline_source="observed_net_revenue",
            baseline_fcas=200.0,
            fcas_baseline_source="manual_input",
            p3_decision={"decision_summary": {"recommended_strategy": "forecast_driven_dispatch"}},
            decision_adjusted_monte_carlo=SimpleNamespace(
                model_dump=lambda: {
                    "npv_p10": 0.5,
                    "npv_p50": 2.2,
                    "npv_p90": 4.8,
                    "irr_p10": 0.05,
                    "irr_p50": 0.12,
                    "irr_p90": 0.21,
                },
            ),
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

        self.assertIn("decision_adjusted_monte_carlo", response)
        self.assertEqual(response["decision_adjusted_monte_carlo"]["npv_p50"], 2.2)
