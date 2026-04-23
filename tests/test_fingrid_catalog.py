import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fingrid.catalog import get_dataset_config, list_dataset_configs
from fingrid.schemas import normalize_fingrid_row


class FingridCatalogTests(unittest.TestCase):
    def test_dataset_317_metadata_is_complete(self):
        dataset = get_dataset_config("317")

        self.assertEqual(dataset["dataset_id"], "317")
        self.assertEqual(dataset["unit"], "EUR/MW")
        self.assertEqual(dataset["timezone"], "Europe/Helsinki")
        self.assertEqual(dataset["value_kind"], "reserve_capacity_price")
        self.assertIn("month", dataset["supported_aggregations"])
        self.assertEqual(list_dataset_configs()[0]["dataset_id"], "317")

    def test_normalize_fingrid_row_accepts_start_time_shape(self):
        dataset = get_dataset_config("317")
        row = normalize_fingrid_row(
            dataset,
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-01T01:00:00Z",
                "value": 42.5,
                "updatedAt": "2026-01-01T00:05:00Z",
                "quality": "confirmed",
            },
            ingested_at="2026-04-23T00:00:00Z",
        )

        self.assertEqual(row["dataset_id"], "317")
        self.assertEqual(row["series_key"], "fcrn_hourly_market_price")
        self.assertEqual(row["timestamp_utc"], "2026-01-01T00:00:00Z")
        self.assertTrue(row["timestamp_local"].startswith("2026-01-01T02:00:00"))
        self.assertEqual(row["extra_json"]["end_time"], "2026-01-01T01:00:00Z")
