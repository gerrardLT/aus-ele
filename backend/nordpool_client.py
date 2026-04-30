from __future__ import annotations

import datetime as dt
import os

import requests


class NordPoolClient:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        base_url: str | None = None,
        token_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.access_token = access_token or os.environ.get("NORDPOOL_ACCESS_TOKEN") or os.environ.get("NORDPOOL_API_KEY")
        self.base_url = (base_url or os.environ.get("NORDPOOL_API_BASE_URL") or "https://data-api.nordpoolgroup.com").rstrip("/")
        self.token_url = token_url or os.environ.get("NORDPOOL_TOKEN_URL")
        self.client_id = client_id or os.environ.get("NORDPOOL_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("NORDPOOL_CLIENT_SECRET")
        self.timeout_seconds = int(timeout_seconds if timeout_seconds is not None else os.environ.get("NORDPOOL_TIMEOUT_SECONDS", "30"))
        self.session = requests.Session()

    def _resolve_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        if not (self.token_url and self.client_id and self.client_secret):
            raise ValueError("Nord Pool credentials are required")

        response = self.session.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ValueError("Nord Pool token response missing access_token")
        self.access_token = token
        return token

    def fetch_day_ahead_area_prices(
        self,
        *,
        delivery_area: str,
        delivery_date,
        currency: str = "EUR",
    ) -> list[dict]:
        token = self._resolve_access_token()
        response = self.session.get(
            f"{self.base_url}/prices/area",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "deliveryArea": delivery_area,
                "date": delivery_date.isoformat(),
                "currency": currency,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = []
        for item in payload.get("data", []):
            timestamp = item.get("deliveryStart")
            price = item.get("price")
            if timestamp is None or price is None:
                continue
            rows.append(
                {
                    "timestamp_utc": timestamp,
                    "price": float(price),
                    "currency": item.get("currency", currency),
                    "unit": item.get("unit", "EUR/MWh"),
                }
            )
        return rows

    def fetch_intraday_trades_by_delivery_start(
        self,
        *,
        areas: list[str],
        delivery_start_from: dt.datetime,
        delivery_start_to: dt.datetime,
    ) -> list[dict]:
        token = self._resolve_access_token()
        response = self.session.get(
            url=f"{self.base_url}/api/v2/Intraday/Trades/ByDeliveryStart",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "areas": ",".join(areas),
                "deliveryStartFrom": delivery_start_from.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "deliveryStartTo": delivery_start_to.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = []
        for item in payload.get("data", []):
            timestamp = item.get("deliveryStart") or item.get("deliveryStartUtc")
            price = item.get("price") or item.get("tradePrice")
            if timestamp is None or price is None:
                continue
            rows.append(
                {
                    "timestamp_utc": timestamp,
                    "trade_time_utc": item.get("tradeTime") or item.get("tradeTimeUtc"),
                    "price": float(price),
                    "volume_mwh": float(item.get("volume") or item.get("volumeMWh") or 0.0),
                    "currency": item.get("currency", "EUR"),
                    "unit": item.get("unit", "EUR/MWh"),
                    "areas": item.get("areas", areas),
                }
            )
        return rows
