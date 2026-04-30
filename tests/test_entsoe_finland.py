import datetime as dt
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from entsoe_finland import (
    FINLAND_BIDDING_ZONE,
    FINLAND_NEIGHBOR_BIDDING_ZONES,
    fetch_finland_cross_border_flow_summary,
    fetch_finland_day_ahead_summary,
    fetch_finland_generation_forecast_summary,
    fetch_finland_generation_mix_summary,
    fetch_finland_total_load_summary,
)


class EntsoeFinlandTests(unittest.TestCase):
    def test_fetch_finland_day_ahead_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_day_ahead_prices.return_value = [
            {"timestamp_utc": "2026-04-28T00:00:00Z", "price": 42.5, "currency": "EUR", "unit": "MWH"},
            {"timestamp_utc": "2026-04-28T01:00:00Z", "price": 51.0, "currency": "EUR", "unit": "MWH"},
        ]

        payload = fetch_finland_day_ahead_summary(
            client=fake_client,
            now_utc=dt.datetime(2026, 4, 28, 12, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "entsoe_day_ahead_fi")
        self.assertEqual(payload["dataset"]["record_count"], 2)
        self.assertEqual(payload["dataset"]["coverage_start_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(payload["dataset"]["coverage_end_utc"], "2026-04-28T01:00:00Z")
        self.assertEqual(payload["summary"]["latest_price"], 51.0)
        self.assertEqual(payload["summary"]["average_price"], 46.75)

        fake_client.fetch_day_ahead_prices.assert_called_once()
        _, kwargs = fake_client.fetch_day_ahead_prices.call_args
        self.assertEqual(kwargs["in_domain"], FINLAND_BIDDING_ZONE)
        self.assertEqual(kwargs["out_domain"], FINLAND_BIDDING_ZONE)

    def test_fetch_finland_total_load_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_total_load.return_value = [
            {"timestamp_utc": "2026-04-28T00:00:00Z", "load_mw": 8200.0},
            {"timestamp_utc": "2026-04-28T01:00:00Z", "load_mw": 8350.0},
        ]

        payload = fetch_finland_total_load_summary(
            client=fake_client,
            now_utc=dt.datetime(2026, 4, 28, 12, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "entsoe_total_load_fi")
        self.assertEqual(payload["dataset"]["record_count"], 2)
        self.assertEqual(payload["summary"]["latest_load_mw"], 8350.0)
        self.assertEqual(payload["summary"]["average_load_mw"], 8275.0)

    def test_fetch_finland_generation_mix_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_aggregated_generation_per_type.return_value = [
            {"timestamp_utc": "2026-04-28T00:00:00Z", "quantity_mw": 4100.0, "psr_type": "B16"},
            {"timestamp_utc": "2026-04-28T01:00:00Z", "quantity_mw": 4300.0, "psr_type": "B16"},
            {"timestamp_utc": "2026-04-28T00:00:00Z", "quantity_mw": 1200.0, "psr_type": "B18"},
            {"timestamp_utc": "2026-04-28T01:00:00Z", "quantity_mw": 1250.0, "psr_type": "B18"},
        ]

        payload = fetch_finland_generation_mix_summary(
            client=fake_client,
            now_utc=dt.datetime(2026, 4, 28, 12, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "entsoe_generation_mix_fi")
        self.assertEqual(payload["dataset"]["record_count"], 4)
        self.assertEqual(payload["summary"]["latest_total_generation_mw"], 5550.0)
        self.assertEqual(payload["summary"]["production_type_count"], 2)
        self.assertEqual(payload["summary"]["top_production_type"], "B16")

        fake_client.fetch_aggregated_generation_per_type.assert_called_once()
        _, kwargs = fake_client.fetch_aggregated_generation_per_type.call_args
        self.assertEqual(kwargs["in_domain"], FINLAND_BIDDING_ZONE)

    def test_fetch_finland_cross_border_flow_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_physical_flows.side_effect = [
            [
                {
                    "timestamp_utc": "2026-04-28T00:00:00Z",
                    "flow_mw": 850.0,
                    "in_domain": FINLAND_BIDDING_ZONE,
                    "out_domain": FINLAND_NEIGHBOR_BIDDING_ZONES["SE1"],
                },
                {
                    "timestamp_utc": "2026-04-28T01:00:00Z",
                    "flow_mw": 910.0,
                    "in_domain": FINLAND_BIDDING_ZONE,
                    "out_domain": FINLAND_NEIGHBOR_BIDDING_ZONES["SE1"],
                },
            ],
            [
                {
                    "timestamp_utc": "2026-04-28T00:00:00Z",
                    "flow_mw": 1200.0,
                    "in_domain": FINLAND_BIDDING_ZONE,
                    "out_domain": FINLAND_NEIGHBOR_BIDDING_ZONES["EE"],
                },
                {
                    "timestamp_utc": "2026-04-28T01:00:00Z",
                    "flow_mw": 1180.0,
                    "in_domain": FINLAND_BIDDING_ZONE,
                    "out_domain": FINLAND_NEIGHBOR_BIDDING_ZONES["EE"],
                },
            ],
        ]

        payload = fetch_finland_cross_border_flow_summary(
            client=fake_client,
            now_utc=dt.datetime(2026, 4, 28, 12, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "entsoe_cross_border_flow_fi")
        self.assertEqual(payload["dataset"]["record_count"], 4)
        self.assertEqual(payload["summary"]["latest_total_flow_mw"], 2090.0)
        self.assertEqual(payload["summary"]["border_count"], 2)
        self.assertEqual(payload["summary"]["largest_border"], "EE")

        self.assertEqual(fake_client.fetch_physical_flows.call_count, 2)

    def test_fetch_finland_generation_forecast_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_generation_forecast.return_value = [
            {"timestamp_utc": "2026-04-28T00:00:00Z", "generation_forecast_mw": 7600.0},
            {"timestamp_utc": "2026-04-28T01:00:00Z", "generation_forecast_mw": 7800.0},
        ]

        payload = fetch_finland_generation_forecast_summary(
            client=fake_client,
            now_utc=dt.datetime(2026, 4, 28, 12, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "entsoe_generation_forecast_fi")
        self.assertEqual(payload["dataset"]["record_count"], 2)
        self.assertEqual(payload["summary"]["latest_generation_forecast_mw"], 7800.0)
        self.assertEqual(payload["summary"]["average_generation_forecast_mw"], 7700.0)
