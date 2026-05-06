import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from connector_framework import get_connector_spec, list_connector_specs


class ConnectorFrameworkTests(unittest.TestCase):
    def test_registry_contains_nem_wem_and_fingrid_connectors(self):
        connector_ids = [spec.source_id for spec in list_connector_specs()]

        self.assertIn("aemo_nem_trading_price", connector_ids)
        self.assertIn("aemo_wem_ess_market", connector_ids)
        self.assertIn("fingrid_dataset_281", connector_ids)
        self.assertIn("fingrid_dataset_283", connector_ids)
        self.assertIn("fingrid_dataset_315", connector_ids)
        self.assertIn("fingrid_dataset_316", connector_ids)
        self.assertIn("fingrid_dataset_317", connector_ids)
        self.assertIn("fingrid_dataset_318", connector_ids)
        self.assertIn("fingrid_dataset_319", connector_ids)

    def test_connector_specs_expose_required_taskbook_fields(self):
        for source_id in (
            "aemo_nem_trading_price",
            "aemo_wem_ess_market",
            "fingrid_dataset_317",
        ):
            spec = get_connector_spec(source_id)

            self.assertTrue(spec.market)
            self.assertTrue(spec.run_modes)
            self.assertTrue(spec.backfill_policy)
            self.assertTrue(spec.rate_limit)
            self.assertTrue(spec.schema_mapping)
            self.assertTrue(spec.quality_checks)

    def test_fingrid_connector_uses_canonical_schema_mapping(self):
        spec = get_connector_spec("fingrid_dataset_317")

        self.assertEqual(spec.market, "FINGRID")
        self.assertEqual(spec.schema_mapping, "map_fingrid_timeseries_row")
        self.assertIn("incremental", spec.run_modes)
        self.assertIn("backfill", spec.run_modes)

    def test_connector_specs_include_dataset_family_and_observation_kind(self):
        spec = get_connector_spec("aemo_nem_operational_demand")

        self.assertEqual(spec.dataset_family, "load_actual")
        self.assertEqual(spec.observation_kind, "actual")
        self.assertEqual(spec.adapter, "build_aemo_load_actual_series")

    def test_aemo_fundamentals_connectors_are_registered_with_contract_fields(self):
        expectations = {
            "aemo_nem_load_forecast": ("load_forecast", "forecast", "build_aemo_load_forecast_series"),
            "aemo_nem_wind_forecast": ("wind_forecast", "forecast", "build_aemo_wind_forecast_series"),
            "aemo_nem_wind_actual": ("wind_actual", "actual", "build_aemo_wind_actual_series"),
            "aemo_nem_solar_forecast": ("solar_forecast", "forecast", "build_aemo_solar_forecast_series"),
            "aemo_nem_solar_actual": ("solar_actual", "actual", "build_aemo_solar_actual_series"),
            "aemo_nem_rooftop_pv": ("rooftop_pv", "actual", "build_aemo_rooftop_pv_series"),
            "aemo_nem_outage": ("outage", "event", "build_aemo_outage_series"),
            "aemo_nem_interconnector_flow": ("interconnector_flow", "actual", "build_aemo_interconnector_flow_series"),
            "aemo_nem_reserve_requirement": ("reserve_requirement", "state", "build_aemo_reserve_requirement_series"),
            "aemo_wem_reserve_shortfall": ("reserve_shortfall", "event", "build_aemo_reserve_shortfall_series"),
            "aemo_nem_weather": ("weather", "actual", "build_aemo_weather_series"),
            "aemo_nem_unit_availability": ("unit_availability", "state", "build_aemo_unit_availability_series"),
        }

        for source_id, (family, observation_kind, adapter) in expectations.items():
            spec = get_connector_spec(source_id)

            self.assertEqual(spec.market, "WEM" if source_id == "aemo_wem_reserve_shortfall" else "NEM")
            self.assertEqual(spec.dataset_family, family)
            self.assertEqual(spec.observation_kind, observation_kind)
            self.assertEqual(spec.adapter, adapter)


if __name__ == "__main__":
    unittest.main()
