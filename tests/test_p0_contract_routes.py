import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


class P0ContractRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app)

    def test_p0_dataset_contract_response_contains_required_metadata(self):
        response = self.client.get("/api/p0/datasets/load-actual?market=NEM&region=NSW1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["dataset_family"], "load_actual")
        self.assertEqual(payload["metadata"]["observation_kind"], "actual")
        self.assertIn("lineage", payload["metadata"])
        self.assertIn("grade", payload["metadata"])
        self.assertGreater(len(payload["points"]), 0)
        self.assertEqual(payload["metadata"]["grade"], "analytical-preview")

    def test_p0_load_actual_route_uses_source_sync_freshness(self):
        with mock.patch.object(
            server.db,
            "fetch_aemo_source_sync_state",
            return_value={
                "source_id": "aemo_nem_load_actual",
                "last_success_at": "2026-05-01T00:03:00Z",
                "last_attempt_at": "2026-05-01T00:04:00Z",
                "sync_status": "ok",
                "last_error": None,
                "detail_json": {"row_count": 48},
            },
        ):
            response = self.client.get("/api/p0/datasets/load-actual?market=NEM&region=NSW1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["freshness"]["last_updated_at"], "2026-05-01T00:03:00Z")

    def test_p0_load_forecast_route_exposes_forecast_contract(self):
        response = self.client.get("/api/p0/datasets/load-forecast?market=NEM&region=QLD1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "load_forecast")
        self.assertEqual(payload["metadata"]["dataset_family"], "load_forecast")
        self.assertEqual(payload["metadata"]["observation_kind"], "forecast")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_load_forecast_route_uses_source_sync_freshness(self):
        with mock.patch.object(
            server.db,
            "fetch_aemo_source_sync_state",
            return_value={
                "source_id": "aemo_nem_load_forecast",
                "last_success_at": "2026-05-01T00:05:00Z",
                "last_attempt_at": "2026-05-01T00:06:00Z",
                "sync_status": "ok",
                "last_error": None,
                "detail_json": {"row_count": 24},
            },
        ):
            response = self.client.get("/api/p0/datasets/load-forecast?market=NEM&region=QLD1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["freshness"]["last_updated_at"], "2026-05-01T00:05:00Z")

    def test_p0_wind_actual_route_returns_real_points(self):
        response = self.client.get("/api/p0/datasets/wind-actual?market=NEM&region=SA1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "wind_actual")
        self.assertGreater(len(payload["points"]), 0)
        self.assertIn("actual_proxy_from_dispatch_clearedmw", payload["metadata"]["warnings"])
        self.assertEqual(payload["metadata"]["lineage"]["measurement_basis"], "dispatch_clearedmw_proxy")

    def test_p0_wind_forecast_route_returns_real_points(self):
        response = self.client.get("/api/p0/datasets/wind-forecast?market=NEM&region=SA1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "wind_forecast")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_solar_actual_route_returns_real_points(self):
        response = self.client.get("/api/p0/datasets/solar-actual?market=NEM&region=QLD1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "solar_actual")
        self.assertGreater(len(payload["points"]), 0)
        self.assertIn("actual_proxy_from_dispatch_clearedmw", payload["metadata"]["warnings"])
        self.assertEqual(payload["metadata"]["lineage"]["measurement_basis"], "dispatch_clearedmw_proxy")

    def test_p0_solar_forecast_route_returns_real_points(self):
        response = self.client.get("/api/p0/datasets/solar-forecast?market=NEM&region=QLD1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "solar_forecast")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_rooftop_pv_route_exposes_distinct_family(self):
        response = self.client.get("/api/p0/datasets/rooftop-pv?market=NEM&region=SA1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "rooftop_pv")
        self.assertEqual(payload["metadata"]["dataset_family"], "rooftop_pv")
        self.assertEqual(payload["metadata"]["unit"], "MW")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_outage_route_exposes_event_contract(self):
        response = self.client.get("/api/p0/datasets/outage?market=NEM&region=NSW1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "outage")
        self.assertEqual(payload["metadata"]["observation_kind"], "event")

    def test_p0_outage_route_uses_event_sync_freshness(self):
        with mock.patch.object(
            server.db,
            "fetch_grid_event_sync_states",
            return_value=[
                {
                    "source": "nem_market_notice",
                    "last_success_at": "2026-05-01 00:11:00",
                    "cursor": None,
                    "last_backfill_at": None,
                    "sync_status": "ok",
                },
                {
                    "source": "bom_warnings",
                    "last_success_at": "2026-05-01 00:12:00",
                    "cursor": None,
                    "last_backfill_at": None,
                    "sync_status": "ok",
                },
            ],
        ):
            response = self.client.get("/api/p0/datasets/outage?market=NEM&region=NSW1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["freshness"]["last_updated_at"], "2026-05-01T00:12:00Z")

    def test_p0_interconnector_flow_route_returns_real_points(self):
        response = self.client.get("/api/p0/datasets/interconnector-flow?market=NEM&interconnector_id=NSW1-QLD1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "interconnector_flow")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_interconnector_flow_route_uses_source_sync_error_warning(self):
        with mock.patch.object(
            server.db,
            "fetch_aemo_source_sync_state",
            return_value={
                "source_id": "aemo_nem_interconnector_flow",
                "last_success_at": "2026-05-01T00:08:00Z",
                "last_attempt_at": "2026-05-01T00:09:00Z",
                "sync_status": "error",
                "last_error": "upstream unavailable",
                "detail_json": {"row_count": 0},
            },
        ):
            response = self.client.get("/api/p0/datasets/interconnector-flow?market=NEM&interconnector_id=NSW1-QLD1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["freshness"]["last_updated_at"], "2026-05-01T00:08:00Z")
        self.assertIn("source_error", payload["metadata"]["warnings"])

    def test_p0_reserve_requirement_route_exposes_state_contract(self):
        response = self.client.get("/api/p0/datasets/reserve-requirement?market=NEM&region=VIC1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "reserve_requirement")
        self.assertEqual(payload["metadata"]["observation_kind"], "state")
        self.assertIn("source_unavailable", payload["metadata"]["warnings"])

    def test_p0_settlement_route_exposes_settlement_contract(self):
        response = self.client.get("/api/p0/datasets/settlement?market=NEM&region=NSW1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "settlement")
        self.assertEqual(payload["metadata"]["observation_kind"], "settlement")
        self.assertEqual(payload["metadata"]["unit"], "AUD")
        self.assertGreater(len(payload["points"]), 0)
        self.assertEqual(payload["metadata"]["grade"], "analytical-preview")

    def test_p0_weather_route_exposes_actual_contract(self):
        response = self.client.get("/api/p0/datasets/weather?market=NEM&region=QLD1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "weather")
        self.assertEqual(payload["metadata"]["observation_kind"], "actual")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_weather_route_uses_source_sync_freshness_and_degraded_warning(self):
        with mock.patch.object(
            server.db,
            "fetch_aemo_source_sync_state",
            return_value={
                "source_id": "aemo_nem_weather",
                "last_success_at": "2026-05-01T00:10:00Z",
                "last_attempt_at": "2026-05-01T00:12:00Z",
                "sync_status": "degraded",
                "last_error": None,
                "detail_json": {"fallback_region_count": 2},
            },
        ):
            response = self.client.get("/api/p0/datasets/weather?market=NEM&region=QLD1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["freshness"]["last_updated_at"], "2026-05-01T00:10:00Z")
        self.assertIn("source_degraded", payload["metadata"]["warnings"])

    def test_p0_unit_availability_route_exposes_state_contract(self):
        response = self.client.get("/api/p0/datasets/unit-availability?market=NEM&region=VIC1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "unit_availability")
        self.assertEqual(payload["metadata"]["observation_kind"], "state")
        self.assertGreater(len(payload["points"]), 0)
        self.assertNotIn("region_filter_unmapped_for_public_duid_feed", payload["metadata"]["warnings"])

    def test_p0_unit_availability_route_uses_source_sync_freshness(self):
        with mock.patch.object(
            server.db,
            "fetch_aemo_source_sync_state",
            return_value={
                "source_id": "aemo_nem_unit_availability",
                "last_success_at": "2026-05-01T00:20:00Z",
                "last_attempt_at": "2026-05-01T00:21:00Z",
                "sync_status": "ok",
                "last_error": None,
                "detail_json": {"row_count": 10},
            },
        ):
            response = self.client.get("/api/p0/datasets/unit-availability?market=NEM&region=VIC1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["metadata"]["freshness"]["last_updated_at"], "2026-05-01T00:20:00Z")

    def test_p0_unit_availability_route_uses_composite_mapping_source_governance(self):
        def _fetch_source_state(source_id: str):
            if source_id == "aemo_nem_unit_availability":
                return {
                    "source_id": "aemo_nem_unit_availability",
                    "last_success_at": "2026-05-01T00:20:00Z",
                    "last_attempt_at": "2026-05-01T00:21:00Z",
                    "sync_status": "ok",
                    "last_error": None,
                    "detail_json": {"row_count": 10},
                }
            if source_id == "aemo_nem_du_detail_summary":
                return {
                    "source_id": "aemo_nem_du_detail_summary",
                    "last_success_at": None,
                    "last_attempt_at": "2026-05-01T00:19:00Z",
                    "sync_status": "error",
                    "last_error": "du_detail_summary archive unavailable",
                    "detail_json": {"row_count": 0},
                }
            return None

        with mock.patch.object(server.db, "fetch_aemo_source_sync_state", side_effect=_fetch_source_state):
            response = self.client.get("/api/p0/datasets/unit-availability?market=NEM&region=VIC1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("source_error", payload["metadata"]["warnings"])

    def test_p0_reserve_shortfall_route_returns_real_wem_points(self):
        response = self.client.get("/api/p0/datasets/reserve-shortfall?market=WEM&region=WEM")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "reserve_shortfall")
        self.assertEqual(payload["metadata"]["observation_kind"], "event")
        self.assertGreater(len(payload["points"]), 0)
        self.assertEqual(payload["metadata"]["lineage"]["source_id"], "aemo_wem_reserve_shortfall")

    def test_p0_reserve_shortfall_route_uses_source_sync_error_warning(self):
        with mock.patch.object(
            server.db,
            "fetch_aemo_source_sync_state",
            return_value={
                "source_id": "aemo_wem_reserve_shortfall",
                "last_success_at": None,
                "last_attempt_at": "2026-05-01T00:25:00Z",
                "sync_status": "error",
                "last_error": "wem_ess_market_price unavailable",
                "detail_json": {"row_count": 0},
            },
        ):
            response = self.client.get("/api/p0/datasets/reserve-shortfall?market=WEM&region=WEM")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("source_error", payload["metadata"]["warnings"])

    def test_p0_reserve_shortfall_route_marks_nem_scope_as_wem_only(self):
        response = self.client.get("/api/p0/datasets/reserve-shortfall?market=NEM&region=NSW1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("market_scope_wem_only", payload["metadata"]["warnings"])

    def test_p0_wem_reserve_requirement_route_returns_real_points(self):
        response = self.client.get("/api/p0/datasets/reserve-requirement?market=WEM&region=WEM")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(payload["points"]), 0)
        self.assertEqual(payload["metadata"]["grade"], "analytical-preview")

    def test_p0_constraint_route_returns_real_wem_points(self):
        response = self.client.get("/api/p0/datasets/constraint?market=WEM&region=WEM")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset_family"], "constraint")
        self.assertGreater(len(payload["points"]), 0)

    def test_p0_outage_route_returns_real_points_for_regions_with_outage_feed(self):
        response = self.client.get("/api/p0/datasets/outage?market=NEM&region=VIC1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(payload["points"]), 0)

    def test_existing_analysis_endpoints_keep_metadata_grade_alias(self):
        payload = server._attach_price_trend_metadata({"data": []}, region="NSW1")
        self.assertEqual(payload["metadata"]["grade"], payload["metadata"]["data_grade"])


if __name__ == "__main__":
    unittest.main()
