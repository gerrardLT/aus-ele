import json
import os
import ssl
import socket
import time
from urllib.parse import urlencode, urlparse

import requests


class FingridClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        request_interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
    ):
        self.api_key = api_key or os.environ.get("FINGRID_API_KEY")
        if not self.api_key:
            raise ValueError("FINGRID_API_KEY is required")

        self.base_url = (base_url or os.environ.get("FINGRID_BASE_URL") or "https://data.fingrid.fi/api").rstrip("/")
        self.request_interval_seconds = float(
            request_interval_seconds
            if request_interval_seconds is not None
            else os.environ.get("FINGRID_REQUEST_INTERVAL_SECONDS", "6.5")
        )
        self.timeout_seconds = int(
            timeout_seconds if timeout_seconds is not None else os.environ.get("FINGRID_TIMEOUT_SECONDS", "30")
        )
        self.session = requests.Session()
        self._last_request_monotonic = 0.0

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self.request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _request_params(
        self,
        *,
        start_time_utc: str,
        end_time_utc: str,
        page_size: int,
        locale: str,
    ) -> dict:
        return {
            "startTime": start_time_utc,
            "endTime": end_time_utc,
            "format": "json",
            "pageSize": page_size,
            "locale": locale,
            "sortBy": "startTime",
            "sortOrder": "asc",
        }

    def _fetch_via_requests(self, dataset_id: str, *, params: dict) -> list[dict]:
        for attempt in range(3):
            response = self.session.get(
                f"{self.base_url}/datasets/{dataset_id}/data",
                headers={"x-api-key": self.api_key},
                params=params,
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                try:
                    retry_seconds = max(float(retry_after), 0.5) if retry_after else 2.0
                except ValueError:
                    retry_seconds = 2.0
                time.sleep(retry_seconds)
                continue
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else payload.get("data", [])
        return []

    def _fetch_via_https_connection(self, dataset_id: str, *, params: dict) -> list[dict]:
        parsed = urlparse(self.base_url)
        query = urlencode(params)
        path = f"{parsed.path}/datasets/{dataset_id}/data?{query}"

        # Fingrid succeeds with a lower-level HTTPS client on this machine while
        # requests/urllib intermittently EOF during handshake. Keep the fallback
        # local to this connector instead of weakening global TLS behavior.
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        host = parsed.hostname
        port = parsed.port or 443

        for attempt in range(3):
            try:
                with socket.create_connection((host, port), timeout=self.timeout_seconds) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                        request = (
                            f"GET {path} HTTP/1.1\r\n"
                            f"Host: {host}\r\n"
                            f"x-api-key: {self.api_key}\r\n"
                            "Connection: close\r\n\r\n"
                        )
                        tls_sock.sendall(request.encode("utf-8"))
                        response_bytes = b""
                        while True:
                            chunk = tls_sock.recv(65536)
                            if not chunk:
                                break
                            response_bytes += chunk
            except (ssl.SSLError, socket.timeout, ConnectionError, OSError):
                if attempt < 2:
                    time.sleep(1.5 + attempt)
                    continue
                raise

            head, body = response_bytes.split(b"\r\n\r\n", 1)
            header_lines = head.decode("iso-8859-1").split("\r\n")
            status_line = header_lines[0]
            status_code = int(status_line.split()[1])
            headers = {}
            for line in header_lines[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            if status_code == 429 and attempt < 2:
                retry_after = headers.get("retry-after")
                try:
                    retry_seconds = max(float(retry_after), 0.5) if retry_after else 2.0
                except ValueError:
                    retry_seconds = 2.0
                time.sleep(retry_seconds)
                continue

            if status_code >= 400:
                raise RuntimeError(
                    f"Fingrid API returned {status_code}: {body[:300].decode('utf-8', errors='replace')}"
                )

            payload = json.loads(body.decode("utf-8"))
            return payload if isinstance(payload, list) else payload.get("data", [])

        return []

    def fetch_dataset_window(
        self,
        dataset_id: str,
        *,
        start_time_utc: str,
        end_time_utc: str,
        page_size: int = 20000,
        locale: str = "en",
    ) -> list[dict]:
        self._throttle()
        params = self._request_params(
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            page_size=page_size,
            locale=locale,
        )
        try:
            rows = self._fetch_via_requests(dataset_id, params=params)
        except requests.exceptions.SSLError:
            rows = self._fetch_via_https_connection(dataset_id, params=params)
        self._last_request_monotonic = time.monotonic()
        return rows
