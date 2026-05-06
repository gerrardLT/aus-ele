import unittest
from unittest import mock

import requests
import ssl

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

    @mock.patch("fingrid.client.time.sleep")
    @mock.patch("fingrid.client.requests.Session.get")
    def test_requests_path_retries_on_rate_limit(self, mock_get, mock_sleep):
        rate_limited = mock.Mock(status_code=429, headers={"Retry-After": "2"})
        ok_response = mock.Mock(status_code=200, headers={})
        ok_response.raise_for_status.return_value = None
        ok_response.json.return_value = [{"value": 12.5}]
        mock_get.side_effect = [rate_limited, ok_response]

        client = FingridClient(api_key="secret-key", request_interval_seconds=0, timeout_seconds=30)
        rows = client.fetch_dataset_window(
            "317",
            start_time_utc="2026-01-01T00:00:00Z",
            end_time_utc="2026-01-31T23:00:00Z",
        )

        self.assertEqual(rows[0]["value"], 12.5)
        mock_sleep.assert_called_with(2.0)

    @mock.patch("fingrid.client.time.sleep")
    @mock.patch.object(FingridClient, "_fetch_via_https_connection")
    @mock.patch.object(FingridClient, "_fetch_via_requests")
    def test_fetch_dataset_window_falls_back_when_requests_hits_ssl_error(
        self,
        mock_requests_fetch,
        mock_https_fetch,
        mock_sleep,
    ):
        mock_requests_fetch.side_effect = requests.exceptions.SSLError("handshake eof")
        mock_https_fetch.return_value = [
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-01T01:00:00Z",
                "value": 12.5,
            }
        ]

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
        mock_requests_fetch.assert_called_once()
        mock_https_fetch.assert_called_once()

    @mock.patch("fingrid.client.time.sleep")
    @mock.patch("fingrid.client.socket.create_connection")
    def test_https_fallback_retries_when_upstream_rate_limits(self, mock_create_connection, mock_sleep):
        class DummySocket:
            def __init__(self, chunks):
                self._chunks = list(chunks)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def sendall(self, payload):
                self.last_payload = payload

            def recv(self, _size):
                if self._chunks:
                    return self._chunks.pop(0)
                return b""

        rate_limit_response = (
            b"HTTP/1.1 429 Too Many Requests\r\n"
            b"Retry-After: 1\r\n"
            b"Content-Type: application/json\r\n\r\n"
            b'{ "statusCode": 429, "message": "Rate limit is exceeded. Try again in 1 seconds." }'
        )
        ok_response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n\r\n"
            b'{"data":[{"value":12.5}]}'
        )

        raw_socket_1 = mock.Mock()
        raw_socket_1.__enter__ = mock.Mock(return_value=raw_socket_1)
        raw_socket_1.__exit__ = mock.Mock(return_value=False)
        raw_socket_2 = mock.Mock()
        raw_socket_2.__enter__ = mock.Mock(return_value=raw_socket_2)
        raw_socket_2.__exit__ = mock.Mock(return_value=False)
        mock_create_connection.side_effect = [raw_socket_1, raw_socket_2]

        client = FingridClient(
            api_key="secret-key",
            base_url="https://data.fingrid.fi/api",
            request_interval_seconds=0,
            timeout_seconds=30,
        )
        wrapped_socket_1 = DummySocket([rate_limit_response])
        wrapped_socket_2 = DummySocket([ok_response])
        client_context = mock.Mock()
        client_context.wrap_socket.side_effect = [wrapped_socket_1, wrapped_socket_2]
        with mock.patch("fingrid.client.ssl.create_default_context", return_value=client_context):
            rows = client._fetch_via_https_connection(
                "317",
                params=client._request_params(
                    start_time_utc="2026-01-01T00:00:00Z",
                    end_time_utc="2026-01-31T23:00:00Z",
                    page_size=20000,
                    locale="en",
                ),
            )

        self.assertEqual(rows[0]["value"], 12.5)
        mock_sleep.assert_called_once_with(1.0)

    @mock.patch("fingrid.client.time.sleep")
    @mock.patch("fingrid.client.socket.create_connection")
    def test_https_fallback_retries_on_ssl_error(self, mock_create_connection, mock_sleep):
        class DummySocket:
            def __init__(self, chunks):
                self._chunks = list(chunks)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def sendall(self, payload):
                self.last_payload = payload

            def recv(self, _size):
                if self._chunks:
                    return self._chunks.pop(0)
                return b""

        raw_socket_1 = mock.Mock()
        raw_socket_1.__enter__ = mock.Mock(return_value=raw_socket_1)
        raw_socket_1.__exit__ = mock.Mock(return_value=False)
        raw_socket_2 = mock.Mock()
        raw_socket_2.__enter__ = mock.Mock(return_value=raw_socket_2)
        raw_socket_2.__exit__ = mock.Mock(return_value=False)
        mock_create_connection.side_effect = [raw_socket_1, raw_socket_2]

        client = FingridClient(api_key="secret-key", request_interval_seconds=0, timeout_seconds=30)
        ok_response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n\r\n"
            b'{"data":[{"value":12.5}]}'
        )
        client_context = mock.Mock()
        client_context.wrap_socket.side_effect = [ssl.SSLError("eof"), DummySocket([ok_response])]
        with mock.patch("fingrid.client.ssl.create_default_context", return_value=client_context):
            rows = client._fetch_via_https_connection(
                "317",
                params=client._request_params(
                    start_time_utc="2026-01-01T00:00:00Z",
                    end_time_utc="2026-01-31T23:00:00Z",
                    page_size=20000,
                    locale="en",
                ),
            )

        self.assertEqual(rows[0]["value"], 12.5)
        mock_sleep.assert_called_with(1.5)
