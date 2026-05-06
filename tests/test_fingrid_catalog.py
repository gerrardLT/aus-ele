import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fingrid.catalog import get_dataset_config, list_dataset_configs
from fingrid.schemas import normalize_fingrid_row


class FingridCatalogTests(unittest.TestCase):
    def test_dataset_317_metadata_is_complete(self):
        dataset = get_dataset_config("317")
        self.assertEqual(dataset["dataset_code"], "fcrn_hourly_market_price")
        self.assertEqual(dataset["unit"], "EUR/MW")
        self.assertEqual(dataset["metadata_json"]["product"], "FCR-N")

    def test_hourly_fcr_market_dataset_set_is_available(self):
        dataset_ids = [item["dataset_id"] for item in list_dataset_configs()]
        self.assertEqual(dataset_ids, ["281", "283", "288", "290", "315", "316", "317", "318", "319", "321"])

    def test_dataset_319_metadata_is_available_for_finland_imbalance_context(self):
        dataset = get_dataset_config("319")
        self.assertEqual(dataset["dataset_code"], "imbalance_price")
        self.assertEqual(dataset["unit"], "EUR/MWh")
        self.assertEqual(dataset["metadata_json"]["product"], "Imbalance")

    def test_normalize_fingrid_row_accepts_start_time_shape(self):
        dataset = get_dataset_config("317")
        row = normalize_fingrid_row(
            dataset,
            {
                "startTime": "2026-04-01T00:00:00Z",
                "endTime": "2026-04-01T01:00:00Z",
                "value": 12.5,
            },
            ingested_at="2026-04-01T02:00:00Z",
        )
        self.assertEqual(row["dataset_id"], "317")
        self.assertEqual(row["series_key"], "fcrn_hourly_market_price")
        self.assertEqual(row["timestamp_utc"], "2026-04-01T00:00:00Z")
        self.assertEqual(row["value"], 12.5)


if __name__ == "__main__":
    unittest.main()
