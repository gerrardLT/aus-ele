import datetime as dt
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from nordpool_client import NordPoolClient


class NordPoolClientTests(unittest.TestCase):
    @mock.patch("nordpool_client.requests.Session.get")
    def test_fetch_day_ahead_area_prices_uses_bearer_token_and_expected_params(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"deliveryStart": "2026-04-28T00:00:00Z", "price": 42.5, "currency": "EUR", "unit": "EUR/MWh"},
                {"deliveryStart": "2026-04-28T01:00:00Z", "price": 51.0, "currency": "EUR", "unit": "EUR/MWh"},
            ]
        }
        mock_get.return_value = mock_response

        client = NordPoolClient(
            access_token="np-token",
            base_url="https://data-api.nordpoolgroup.com",
            timeout_seconds=30,
        )
        rows = client.fetch_day_ahead_area_prices(
            delivery_area="FI",
            delivery_date=dt.date(2026, 4, 28),
            currency="EUR",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["price"], 42.5)
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer np-token")
        self.assertEqual(kwargs["params"]["deliveryArea"], "FI")
        self.assertEqual(kwargs["params"]["currency"], "EUR")
        self.assertEqual(kwargs["params"]["date"], "2026-04-28")

    @mock.patch("nordpool_client.requests.Session.post")
    @mock.patch("nordpool_client.requests.Session.get")
    def test_client_credentials_flow_fetches_access_token_when_direct_token_missing(self, mock_get, mock_post):
        token_response = mock.Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"access_token": "issued-token"}
        mock_post.return_value = token_response

        data_response = mock.Mock()
        data_response.raise_for_status.return_value = None
        data_response.json.return_value = {"data": []}
        mock_get.return_value = data_response

        client = NordPoolClient(
            access_token=None,
            base_url="https://data-api.nordpoolgroup.com",
            token_url="https://identity.nordpoolgroup.com/connect/token",
            client_id="client-id",
            client_secret="client-secret",
            timeout_seconds=30,
        )
        client.fetch_day_ahead_area_prices(
            delivery_area="FI",
            delivery_date=dt.date(2026, 4, 28),
            currency="EUR",
        )

        _, post_kwargs = mock_post.call_args
        self.assertEqual(post_kwargs["data"]["grant_type"], "client_credentials")
        self.assertEqual(post_kwargs["data"]["client_id"], "client-id")
        self.assertEqual(post_kwargs["data"]["client_secret"], "client-secret")

    @mock.patch("nordpool_client.requests.Session.get")
    def test_fetch_intraday_trades_by_delivery_start_uses_official_v2_endpoint_and_params(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {
                    "deliveryStart": "2026-04-28T00:00:00Z",
                    "tradeTime": "2026-04-27T23:55:00Z",
                    "price": 48.5,
                    "volume": 12.5,
                    "currency": "EUR",
                    "unit": "EUR/MWh",
                    "areas": ["FI"],
                },
                {
                    "deliveryStart": "2026-04-28T01:00:00Z",
                    "tradeTime": "2026-04-28T00:35:00Z",
                    "price": 52.0,
                    "volume": 9.0,
                    "currency": "EUR",
                    "unit": "EUR/MWh",
                    "areas": ["FI"],
                },
            ]
        }
        mock_get.return_value = mock_response

        client = NordPoolClient(
            access_token="np-token",
            base_url="https://data-api.nordpoolgroup.com",
            timeout_seconds=30,
        )
        rows = client.fetch_intraday_trades_by_delivery_start(
            areas=["FI"],
            delivery_start_from=dt.datetime(2026, 4, 28, 0, 0, tzinfo=dt.timezone.utc),
            delivery_start_to=dt.datetime(2026, 4, 28, 2, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["price"], 48.5)
        self.assertEqual(rows[0]["volume_mwh"], 12.5)
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer np-token")
        self.assertTrue(str(kwargs["url"]).endswith("/api/v2/Intraday/Trades/ByDeliveryStart"))
        self.assertEqual(kwargs["params"]["areas"], "FI")
        self.assertEqual(kwargs["params"]["deliveryStartFrom"], "2026-04-28T00:00:00Z")
        self.assertEqual(kwargs["params"]["deliveryStartTo"], "2026-04-28T02:00:00Z")


if __name__ == "__main__":
    unittest.main()
