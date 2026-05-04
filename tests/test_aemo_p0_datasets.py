import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from aemo_p0_datasets import (
    build_aemo_constraint_series,
    build_aemo_interconnector_flow_series,
    build_aemo_load_actual_series,
    build_aemo_load_forecast_series,
    build_aemo_outage_series,
    build_aemo_rooftop_pv_series,
    build_aemo_reserve_requirement_series,
    build_aemo_reserve_shortfall_series,
    build_aemo_settlement_series,
    build_aemo_solar_actual_series,
    build_aemo_solar_forecast_series,
    build_aemo_unit_availability_series,
    build_aemo_weather_series,
    build_aemo_wind_actual_series,
    build_aemo_wind_forecast_series,
)


class AemoP0DatasetTests(unittest.TestCase):
    def test_aemo_load_actual_series_builds_canonical_contract(self):
        payload = build_aemo_load_actual_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 8450.0,
                }
            ],
            region="NSW1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "load_actual")
        self.assertEqual(payload["observation_kind"], "actual")
        self.assertEqual(payload["region_or_zone"], "NSW1")
        self.assertEqual(payload["unit"], "MW")

    def test_build_aemo_constraint_series_marks_input_layer_not_regime(self):
        payload = build_aemo_constraint_series(
            rows=[
                {
                    "constraint_id": "N::TEST",
                    "binding_flag": True,
                    "shadow_price": 1450.0,
                    "effective_start": "2026-04-30T00:00:00Z",
                    "effective_end": "2026-04-30T00:05:00Z",
                }
            ],
            region="NSW1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "constraint")
        self.assertEqual(payload["observation_kind"], "state")
        self.assertNotIn("regime", payload)

    def test_build_aemo_settlement_series_includes_lineage_and_quality(self):
        payload = build_aemo_settlement_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 120.5,
                    "component": "energy",
                    "finality": "prelim",
                }
            ],
            region="NSW1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "settlement")
        self.assertEqual(payload["observation_kind"], "settlement")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_settlement")
        self.assertEqual(payload["quality"]["finality"], "prelim")
        self.assertEqual(payload["quality"]["component"], "energy")

    def test_build_aemo_settlement_series_exposes_counterparty_and_run_dimensions(self):
        payload = build_aemo_settlement_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 18.2,
                    "component": "fcas_raise_6sec",
                    "finality": "final",
                    "settlement_run": "weekend_rerun",
                    "counterparty_type": "market_operator",
                }
            ],
            region="QLD1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["quality"]["settlement_run"], "weekend_rerun")
        self.assertEqual(payload["quality"]["counterparty_type"], "market_operator")
        self.assertEqual(payload["points"][0]["component"], "fcas_raise_6sec")
        self.assertEqual(payload["points"][0]["counterparty_type"], "market_operator")

    def test_build_aemo_load_forecast_series_builds_forecast_contract(self):
        payload = build_aemo_load_forecast_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 8610.0,
                    "run_at": "2026-04-29T23:30:00Z",
                }
            ],
            region="QLD1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "load_forecast")
        self.assertEqual(payload["observation_kind"], "forecast")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_nem_load_forecast")
        self.assertEqual(payload["quality"]["forecast_run_at"], "2026-04-29T23:30:00Z")

    def test_build_aemo_wind_forecast_series_uses_counterpart_series(self):
        payload = build_aemo_wind_forecast_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 1240.0,
                    "run_at": "2026-04-29T23:30:00Z",
                }
            ],
            region="SA1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "wind_forecast")
        self.assertEqual(payload["counterpart_series_id"], "wind_actual:SA1")

    def test_build_aemo_wind_actual_series_marks_actual_generation(self):
        payload = build_aemo_wind_actual_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 1188.0,
                }
            ],
            region="SA1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "wind_actual")
        self.assertEqual(payload["observation_kind"], "actual")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_nem_wind_actual")
        self.assertEqual(payload["lineage"]["measurement_basis"], "dispatch_clearedmw_proxy")

    def test_build_aemo_solar_forecast_series_uses_mw_unit(self):
        payload = build_aemo_solar_forecast_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 930.0,
                    "run_at": "2026-04-29T23:30:00Z",
                }
            ],
            region="VIC1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "solar_forecast")
        self.assertEqual(payload["unit"], "MW")

    def test_build_aemo_solar_actual_series_uses_actual_observation_kind(self):
        payload = build_aemo_solar_actual_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 884.0,
                }
            ],
            region="VIC1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "solar_actual")
        self.assertEqual(payload["observation_kind"], "actual")
        self.assertEqual(payload["lineage"]["measurement_basis"], "dispatch_clearedmw_proxy")

    def test_build_aemo_rooftop_pv_series_keeps_distinct_family(self):
        payload = build_aemo_rooftop_pv_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 522.0,
                }
            ],
            region="QLD1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "rooftop_pv")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_nem_rooftop_pv")

    def test_build_aemo_outage_series_marks_event_contract(self):
        payload = build_aemo_outage_series(
            rows=[
                {
                    "unit_id": "BAYSWTR1",
                    "event_start": "2026-04-30T00:00:00Z",
                    "event_end": "2026-04-30T06:00:00Z",
                    "available_capacity_mw": 0.0,
                    "outage_capacity_mw": 660.0,
                    "outage_type": "planned",
                }
            ],
            region="NSW1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "outage")
        self.assertEqual(payload["observation_kind"], "event")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_nem_outage")

    def test_build_aemo_interconnector_flow_series_uses_interconnector_scope(self):
        payload = build_aemo_interconnector_flow_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 540.0,
                    "interconnector_id": "NSW1-QLD1",
                    "from_region": "NSW1",
                    "to_region": "QLD1",
                }
            ],
            interconnector_id="NSW1-QLD1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "interconnector_flow")
        self.assertEqual(payload["region_or_zone"], "NSW1-QLD1")
        self.assertEqual(payload["unit"], "MW")

    def test_build_aemo_reserve_requirement_series_marks_state_contract(self):
        payload = build_aemo_reserve_requirement_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 850.0,
                    "reserve_service": "RAISE6SEC",
                }
            ],
            region="VIC1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "reserve_requirement")
        self.assertEqual(payload["observation_kind"], "state")

    def test_build_aemo_reserve_shortfall_series_marks_event_contract(self):
        payload = build_aemo_reserve_shortfall_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "value": 120.0,
                    "reserve_service": "RAISE6SEC",
                    "severity": "market_notice",
                }
            ],
            region="SA1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "reserve_shortfall")
        self.assertEqual(payload["observation_kind"], "event")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_wem_reserve_shortfall")

    def test_build_aemo_weather_series_preserves_metric_points(self):
        payload = build_aemo_weather_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "temperature_c": 21.5,
                    "wind_speed_mps": 7.2,
                    "cloud_cover_pct": 38.0,
                }
            ],
            region="QLD1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "weather")
        self.assertEqual(payload["observation_kind"], "actual")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_nem_weather")

    def test_build_aemo_unit_availability_series_marks_state_contract(self):
        payload = build_aemo_unit_availability_series(
            rows=[
                {
                    "interval_start": "2026-04-30T00:00:00Z",
                    "interval_end": "2026-04-30T00:30:00Z",
                    "unit_id": "ER02",
                    "available_capacity_mw": 430.0,
                    "max_capacity_mw": 460.0,
                }
            ],
            region="VIC1",
            ingested_at="2026-04-30T01:00:00Z",
        )

        self.assertEqual(payload["dataset_family"], "unit_availability")
        self.assertEqual(payload["observation_kind"], "state")


if __name__ == "__main__":
    unittest.main()
