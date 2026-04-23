import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fingrid.client import FingridClient


class FingridClientTests(unittest.TestCase):
    @mock.patch("fingrid.client.time.sleep")
    @mock.patch("fingrid.client.requests.Session.get")
    def test_fetch_dataset_window_uses_dataset_endpoint_and_headers(self, mock_get, mock_sleep):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-01T01:00:00Z",
                "value": 12.5,
            }
        ]
        mock_get.return_value = mock_response

        client = FingridClient(
            api_key="secret-key",
            base_url="https://data.fingrid.fi/api",
            request_interval_seconds=6.5,
            timeout_seconds=30,
        )
        rows = client.fetch_dataset_window(
            "317",
            start_time_utc="2026-01-01T00:00:00Z",
            end_time_utc="2026-01-31T23:00:00Z",
        )

        self.assertEqual(rows[0]["value"], 12.5)
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://data.fingrid.fi/api/datasets/317/data")
        self.assertEqual(kwargs["headers"]["x-api-key"], "secret-key")
        self.assertEqual(kwargs["params"]["format"], "json")
        self.assertEqual(kwargs["params"]["sortBy"], "startTime")
        self.assertEqual(kwargs["params"]["sortOrder"], "asc")
        self.assertEqual(kwargs["params"]["pageSize"], 20000)
