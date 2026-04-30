import datetime as dt
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from nordpool_finland import fetch_finland_day_ahead_summary, fetch_finland_intraday_summary


class NordPoolFinlandTests(unittest.TestCase):
    def test_fetch_finland_day_ahead_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_day_ahead_area_prices.return_value = [
            {"timestamp_utc": "2026-04-28T00:00:00Z", "price": 42.5, "currency": "EUR", "unit": "EUR/MWh"},
            {"timestamp_utc": "2026-04-28T01:00:00Z", "price": 51.0, "currency": "EUR", "unit": "EUR/MWh"},
        ]

        payload = fetch_finland_day_ahead_summary(
            client=fake_client,
            delivery_date=dt.date(2026, 4, 28),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "nordpool_day_ahead_fi")
        self.assertEqual(payload["dataset"]["record_count"], 2)
        self.assertEqual(payload["summary"]["latest_price"], 51.0)
        self.assertEqual(payload["summary"]["average_price"], 46.75)

    def test_fetch_finland_intraday_summary_builds_live_dataset_summary(self):
        fake_client = mock.Mock()
        fake_client.fetch_intraday_trades_by_delivery_start.return_value = [
            {
                "timestamp_utc": "2026-04-28T00:00:00Z",
                "trade_time_utc": "2026-04-27T23:55:00Z",
                "price": 48.5,
                "volume_mwh": 12.5,
                "currency": "EUR",
                "unit": "EUR/MWh",
            },
            {
                "timestamp_utc": "2026-04-28T01:00:00Z",
                "trade_time_utc": "2026-04-28T00:35:00Z",
                "price": 52.0,
                "volume_mwh": 9.0,
                "currency": "EUR",
                "unit": "EUR/MWh",
            },
        ]

        payload = fetch_finland_intraday_summary(
            client=fake_client,
            delivery_date=dt.date(2026, 4, 28),
        )

        self.assertEqual(payload["dataset"]["dataset_id"], "nordpool_intraday_fi")
        self.assertEqual(payload["dataset"]["record_count"], 2)
        self.assertEqual(payload["summary"]["latest_price"], 52.0)
        self.assertEqual(payload["summary"]["average_price"], 50.25)
        self.assertEqual(payload["summary"]["total_volume_mwh"], 21.5)
