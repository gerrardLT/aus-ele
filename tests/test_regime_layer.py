import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


def _half_hour_rows(values):
    rows = []
    for idx, value in enumerate(values):
        hour = idx // 2
        minute = 30 if idx % 2 else 0
        start = f"2026-05-01T{hour:02d}:{minute:02d}:00Z"
        end_hour = hour + (1 if minute == 30 else 0)
        end_minute = 0 if minute == 30 else 30
        end = f"2026-05-01T{end_hour:02d}:{end_minute:02d}:00Z"
        rows.append({"interval_start": start, "interval_end": end, "value": value})
    return rows


class RegimeLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app)

    @patch("server._fetch_recent_grid_state_rows", return_value=[])
    @patch("server._fetch_latest_nem_region_prices", return_value={"NSW1": 210.0, "QLD1": -25.0, "VIC1": 80.0, "SA1": -60.0, "TAS1": 45.0})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=_half_hour_rows([400.0, 420.0, 410.0, 430.0]))
    @patch("server._fetch_dispatch_region_metric_rows")
    @patch("server._fetch_operational_demand_actual_rows", return_value=_half_hour_rows([900.0, 880.0, 860.0, 840.0]))
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([-120.0, -80.0, -40.0, -20.0]))
    def test_build_regime_layer_summary_identifies_negative_price_oversupply(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_states,
    ):
        def dispatch_side_effect(region, metric, limit=96):
            if metric == "ss_wind_clearedmw":
                return _half_hour_rows([180.0, 190.0, 200.0, 195.0])
            if metric == "ss_solar_clearedmw":
                return _half_hour_rows([260.0, 250.0, 240.0, 245.0])
            return []

        mock_dispatch_metric.side_effect = dispatch_side_effect

        payload = server._build_regime_layer_payload(market="NEM", region="SA1")

        self.assertEqual(payload["primary_regime"]["regime"], "negative_price")
        self.assertGreaterEqual(payload["regime_score_map"]["negative_price"], 70)
        self.assertGreaterEqual(payload["regime_score_map"]["oversupply"], 60)
        active_regimes = {item["regime"] for item in payload["active_regimes"]}
        self.assertIn("negative_price", active_regimes)
        self.assertIn("oversupply", active_regimes)
        self.assertEqual(payload["active_regimes"][0]["regime"], payload["primary_regime"]["regime"])
        scores = [item["score"] for item in payload["active_regimes"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(payload["compact"]["top_drivers"][0]["driver_type"], "renewables_balance")

    @patch("server._fetch_recent_grid_state_rows", return_value=[{"state_type": "reserve_tightness", "severity": "high", "confidence": 0.9, "headline": "Reserve notice active"}])
    @patch("server._fetch_latest_nem_region_prices", return_value={})
    @patch("server._fetch_wem_constraint_rows", return_value=[{"binding_flag": True, "shadow_price": 1800.0}])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[{"value": 120.0, "reserve_service": "ROCOF", "severity": "market_shortfall"}])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=[])
    @patch("server._fetch_dispatch_region_metric_rows", return_value=[])
    @patch("server._fetch_operational_demand_actual_rows", return_value=[])
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([320.0, 340.0, 360.0, 380.0]))
    def test_build_regime_layer_summary_identifies_reserve_stress_for_wem(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_states,
    ):
        payload = server._build_regime_layer_payload(market="WEM", region="WEM")

        self.assertEqual(payload["primary_regime"]["regime"], "reserve_stress")
        self.assertGreaterEqual(payload["regime_score_map"]["reserve_stress"], 70)
        self.assertIn("reserve_stress", {item["regime"] for item in payload["active_regimes"]})
        self.assertTrue(any("Reserve notice active" in driver["headline"] for driver in payload["drivers"]))

    @patch("server._fetch_recent_grid_state_rows", return_value=[])
    @patch("server._fetch_region_interconnector_flow_rows", return_value=[])
    @patch("server._fetch_latest_nem_region_prices", return_value={"NSW1": 360.0, "QLD1": 355.0, "VIC1": 340.0, "SA1": 345.0, "TAS1": 338.0})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=_half_hour_rows([80.0, 70.0, 60.0, 55.0]))
    @patch("server._fetch_dispatch_region_metric_rows")
    @patch("server._fetch_operational_demand_actual_rows", return_value=_half_hour_rows([900.0, 920.0, 980.0, 1150.0]))
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([320.0, 340.0, 360.0, 380.0]))
    def test_build_regime_layer_identifies_nem_scarcity_from_spike_and_load_tightness(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_interconnector_rows,
        mock_states,
    ):
        def dispatch_side_effect(region, metric, limit=96):
            if metric == "ss_wind_clearedmw":
                return _half_hour_rows([110.0, 105.0, 95.0, 90.0])
            if metric == "ss_solar_clearedmw":
                return _half_hour_rows([40.0, 35.0, 25.0, 20.0])
            return []

        mock_dispatch_metric.side_effect = dispatch_side_effect

        payload = server._build_regime_layer_payload(market="NEM", region="NSW1")

        self.assertEqual(payload["primary_regime"]["regime"], "scarcity")
        self.assertGreaterEqual(payload["regime_score_map"]["scarcity"], 55)
        self.assertIn("scarcity", {item["regime"] for item in payload["active_regimes"]})
        self.assertTrue(any(driver["driver_type"] == "load_tightness" for driver in payload["drivers"]))

    @patch("server._fetch_recent_grid_state_rows", return_value=[
        {"state_type": "reserve_tightness", "severity": "high", "confidence": 0.9, "headline": "Reserve margin tight"},
        {"state_type": "network_stress", "severity": "high", "confidence": 0.95, "headline": "Network outage cluster"},
    ])
    @patch("server._fetch_region_interconnector_flow_rows", return_value=_half_hour_rows([620.0, 610.0, 640.0, 635.0]))
    @patch("server._fetch_latest_nem_region_prices", return_value={"NSW1": 145.0, "QLD1": 138.0, "VIC1": 141.0, "SA1": 140.0, "TAS1": 139.0})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=_half_hour_rows([90.0, 85.0, 80.0, 78.0]))
    @patch("server._fetch_dispatch_region_metric_rows")
    @patch("server._fetch_operational_demand_actual_rows", return_value=_half_hour_rows([1000.0, 1080.0, 1170.0, 1290.0]))
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([125.0, 130.0, 135.0, 140.0]))
    def test_build_regime_layer_identifies_scarcity_from_load_reserve_and_network_even_without_spike_prices(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_interconnector_rows,
        mock_states,
    ):
        def dispatch_side_effect(region, metric, limit=96):
            if metric == "ss_wind_clearedmw":
                return _half_hour_rows([120.0, 115.0, 105.0, 95.0])
            if metric == "ss_solar_clearedmw":
                return _half_hour_rows([55.0, 45.0, 35.0, 28.0])
            return []

        mock_dispatch_metric.side_effect = dispatch_side_effect

        payload = server._build_regime_layer_payload(market="NEM", region="NSW1")

        self.assertEqual(payload["primary_regime"]["regime"], "scarcity")
        self.assertGreaterEqual(payload["regime_score_map"]["scarcity"], 55)
        self.assertLess(payload["regime_score_map"]["negative_price"], 30)
        self.assertTrue(any(driver["driver_type"] == "load_tightness" for driver in payload["drivers"]))
        self.assertTrue(any(driver["driver_type"] == "reserve_tightness" for driver in payload["drivers"]))
        self.assertTrue(any(driver["driver_type"] == "network_stress" for driver in payload["drivers"]))

    @patch("server._fetch_recent_grid_state_rows", return_value=[{"state_type": "network_stress", "severity": "high", "confidence": 0.95, "headline": "Constraint cluster active"}])
    @patch("server._fetch_region_interconnector_flow_rows", return_value=_half_hour_rows([120.0, 130.0, 110.0, 115.0]))
    @patch("server._fetch_latest_nem_region_prices", return_value={"NSW1": 145.0, "QLD1": 140.0, "VIC1": 142.0, "SA1": 139.0, "TAS1": 141.0})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=_half_hour_rows([140.0, 145.0, 142.0, 141.0]))
    @patch("server._fetch_dispatch_region_metric_rows", return_value=_half_hour_rows([180.0, 175.0, 170.0, 168.0]))
    @patch("server._fetch_operational_demand_actual_rows", return_value=_half_hour_rows([860.0, 850.0, 845.0, 840.0]))
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([130.0, 135.0, 140.0, 145.0]))
    def test_build_regime_layer_identifies_congestion_from_network_stress(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_interconnector_rows,
        mock_states,
    ):
        payload = server._build_regime_layer_payload(market="NEM", region="NSW1")

        self.assertEqual(payload["primary_regime"]["regime"], "congestion")
        self.assertGreaterEqual(payload["regime_score_map"]["congestion"], 55)
        self.assertIn("congestion", {item["regime"] for item in payload["active_regimes"]})
        self.assertTrue(any(driver["driver_type"] == "network_stress" for driver in payload["drivers"]))

    @patch("server._fetch_recent_grid_state_rows", return_value=[])
    @patch("server._fetch_region_interconnector_flow_rows", return_value=[
        {"value": 780.0, "from_region": "NSW1", "to_region": "QLD1"},
        {"value": 810.0, "from_region": "NSW1", "to_region": "QLD1"},
        {"value": 795.0, "from_region": "NSW1", "to_region": "QLD1"},
    ])
    @patch("server._fetch_latest_nem_region_prices", return_value={"NSW1": 350.0, "QLD1": 40.0, "VIC1": 55.0, "SA1": 65.0, "TAS1": 50.0})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=[])
    @patch("server._fetch_dispatch_region_metric_rows", return_value=[])
    @patch("server._fetch_operational_demand_actual_rows", return_value=_half_hour_rows([920.0, 910.0, 905.0, 900.0]))
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([330.0, 340.0, 350.0, 360.0]))
    def test_build_regime_layer_uses_interconnector_flow_for_transmission_separation(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_interconnector_rows,
        mock_states,
    ):
        payload = server._build_regime_layer_payload(market="NEM", region="NSW1")

        self.assertGreaterEqual(payload["regime_score_map"]["transmission_separation"], 55)
        self.assertIn("transmission_separation", {item["regime"] for item in payload["active_regimes"]})
        self.assertTrue(any(driver["driver_type"] == "interconnector_flow" for driver in payload["drivers"]))

    @patch("server._build_regime_layer_payload")
    def test_regime_layer_route_exposes_payload(self, mock_builder):
        mock_builder.return_value = {
            "market": "NEM",
            "region": "NSW1",
            "active_regimes": [],
            "primary_regime": {"regime": "scarcity", "score": 61.2, "confidence": 0.73},
            "regime_score_map": {"scarcity": 61.2},
            "drivers": [],
            "transition_hints": [],
            "metadata": {"dataset_family": "regime_layer"},
        }

        response = self.client.get("/api/p1/regime-layer?market=NEM&region=NSW1")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["primary_regime"]["regime"], "scarcity")
        self.assertEqual(payload["metadata"]["dataset_family"], "regime_layer")
        self.assertEqual(payload["compact"]["primary_regime"]["regime"], "scarcity")
        self.assertIn("availability_status", payload["compact"])

    @patch("server._fetch_recent_grid_state_rows", return_value=[])
    @patch("server._fetch_region_interconnector_flow_rows", return_value=[])
    @patch("server._fetch_latest_nem_region_prices", return_value={})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_rooftop_pv_actual_rows", return_value=[])
    @patch("server._fetch_dispatch_region_metric_rows", return_value=[])
    @patch("server._fetch_operational_demand_actual_rows", return_value=[])
    @patch("server._fetch_settlement_rows", return_value=[])
    def test_build_regime_layer_returns_unavailable_when_inputs_missing(
        self,
        mock_settlement,
        mock_load,
        mock_dispatch_metric,
        mock_rooftop,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_interconnector_rows,
        mock_states,
    ):
        payload = server._build_regime_layer_payload(market="NEM", region="NSW1")

        self.assertIsNone(payload["primary_regime"])
        self.assertEqual(payload["active_regimes"], [])
        self.assertEqual(payload["regime_score_map"], {})
        self.assertIn("regime_layer_unavailable", payload["metadata"]["warnings"])
        self.assertEqual(payload["compact"]["availability_status"], "unavailable")
        self.assertIsNone(payload["compact"]["primary_regime"])

    @patch("server._fetch_recent_grid_state_rows", return_value=[])
    @patch("server._fetch_latest_nem_region_prices", return_value={})
    @patch("server._fetch_wem_constraint_rows", return_value=[])
    @patch("server._fetch_wem_reserve_shortfall_snapshot_rows", return_value=[])
    @patch("server._fetch_settlement_rows", return_value=_half_hour_rows([320.0, 340.0, 360.0, 380.0]))
    def test_build_regime_layer_degrades_when_optional_nem_fundamentals_are_missing(
        self,
        mock_settlement,
        mock_shortfall,
        mock_constraint,
        mock_latest_prices,
        mock_states,
    ):
        payload = server._build_regime_layer_payload(market="NEM", region="NSW1")

        self.assertIsNotNone(payload["primary_regime"])
        self.assertEqual(payload["compact"]["availability_status"], "available")
        self.assertNotIn("regime_layer_unavailable", payload["metadata"]["warnings"])

    def test_build_compact_regime_contract_deduplicates_top_drivers_and_transition_hints(self):
        compact = server._build_compact_regime_contract(
            {
                "primary_regime": {"regime": "scarcity", "score": 74.0, "confidence": 0.81},
                "active_regimes": [
                    {"regime": "scarcity", "score": 74.0, "confidence": 0.81},
                    {"regime": "reserve_stress", "score": 68.0, "confidence": 0.76},
                ],
                "regime_score_map": {"scarcity": 74.0, "reserve_stress": 68.0},
                "drivers": [
                    {"headline": "Reserve margin is tight", "driver_type": "reserve_tightness"},
                    {"headline": "Reserve margin is tight", "driver_type": "reserve_tightness"},
                    {"headline": "Spike interval ratio 12.5%", "driver_type": "price_shape"},
                    {"headline": "Regional spread signal 55.0", "driver_type": "regional_price_spread"},
                ],
                "transition_hints": [
                    "Reserve stress can escalate into broader scarcity if shortfalls persist.",
                    "Reserve stress can escalate into broader scarcity if shortfalls persist.",
                    "Regional spread and network constraints are moving together.",
                ],
                "metadata": {"warnings": []},
            }
        )

        self.assertEqual(
            compact["top_drivers"],
            [
                {"headline": "Reserve margin is tight", "driver_type": "reserve_tightness"},
                {"headline": "Regional spread signal 55.0", "driver_type": "regional_price_spread"},
                {"headline": "Spike interval ratio 12.5%", "driver_type": "price_shape"},
            ],
        )
        self.assertEqual(
            compact["transition_hints"],
            [
                "Reserve stress can escalate into broader scarcity if shortfalls persist.",
                "Regional spread and network constraints are moving together.",
            ],
        )

    def test_build_compact_regime_contract_prioritizes_fundamental_drivers_over_price_shape(self):
        compact = server._build_compact_regime_contract(
            {
                "primary_regime": {"regime": "negative_price", "score": 72.0, "confidence": 0.77},
                "active_regimes": [
                    {"regime": "negative_price", "score": 72.0, "confidence": 0.77},
                    {"regime": "oversupply", "score": 66.0, "confidence": 0.71},
                ],
                "regime_score_map": {"negative_price": 72.0, "oversupply": 66.0},
                "drivers": [
                    {"headline": "Latest price -85.0 AUD/MWh", "driver_type": "price_level"},
                    {"headline": "Negative-price interval ratio 42.00%", "driver_type": "price_shape"},
                    {"headline": "Renewable/load ratio 1.18", "driver_type": "renewables_balance"},
                    {"headline": "Reserve support signal 68.0", "driver_type": "reserve_tightness"},
                ],
                "transition_hints": [],
                "metadata": {"warnings": []},
            }
        )

        self.assertEqual(
            [item["driver_type"] for item in compact["top_drivers"]],
            ["reserve_tightness", "renewables_balance", "price_level"],
        )


if __name__ == "__main__":
    unittest.main()
