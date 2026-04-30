import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from connector_framework import get_connector_spec, list_connector_specs


class ConnectorFrameworkTests(unittest.TestCase):
    def test_registry_contains_nem_wem_and_fingrid_connectors(self):
        connector_ids = [spec.source_id for spec in list_connector_specs()]

        self.assertIn("aemo_nem_trading_price", connector_ids)
        self.assertIn("aemo_wem_ess_market", connector_ids)
        self.assertIn("fingrid_dataset_317", connector_ids)

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


if __name__ == "__main__":
    unittest.main()
