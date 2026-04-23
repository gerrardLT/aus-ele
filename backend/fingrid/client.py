import os
import time

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
        response = self.session.get(
            f"{self.base_url}/datasets/{dataset_id}/data",
            headers={"x-api-key": self.api_key},
            params={
                "startTime": start_time_utc,
                "endTime": end_time_utc,
                "format": "json",
                "pageSize": page_size,
                "locale": locale,
                "sortBy": "startTime",
                "sortOrder": "asc",
            },
            timeout=self.timeout_seconds,
        )
        self._last_request_monotonic = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else payload.get("data", [])
