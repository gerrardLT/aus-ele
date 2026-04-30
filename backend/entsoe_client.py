import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests


ENTSOE_XML_NS = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
ENTSOE_LOAD_XML_NS = {"ns": "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"}


def _parse_resolution(resolution: str | None) -> timedelta:
    if resolution == "PT15M":
        return timedelta(minutes=15)
    if resolution == "PT30M":
        return timedelta(minutes=30)
    return timedelta(hours=1)


def _to_utc_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EntsoeClient:
    def __init__(
        self,
        *,
        security_token: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.security_token = security_token or os.environ.get("ENTSOE_SECURITY_TOKEN")
        if not self.security_token:
            raise ValueError("ENTSOE_SECURITY_TOKEN is required")

        self.base_url = (base_url or os.environ.get("ENTSOE_API_BASE_URL") or "https://web-api.tp.entsoe.eu/api").rstrip("/")
        self.timeout_seconds = int(timeout_seconds if timeout_seconds is not None else os.environ.get("ENTSOE_TIMEOUT_SECONDS", "30"))
        self.session = requests.Session()

    def fetch_day_ahead_prices(
        self,
        *,
        in_domain: str,
        out_domain: str,
        period_start: str,
        period_end: str,
    ) -> list[dict]:
        response = self.session.get(
            self.base_url,
            params={
                "securityToken": self.security_token,
                "documentType": "A44",
                "processType": "A01",
                "in_Domain": in_domain,
                "out_Domain": out_domain,
                "periodStart": period_start,
                "periodEnd": period_end,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_day_ahead_prices_xml(response.text)

    def fetch_total_load(
        self,
        *,
        out_bidding_zone_domain: str,
        period_start: str,
        period_end: str,
    ) -> list[dict]:
        response = self.session.get(
            self.base_url,
            params={
                "securityToken": self.security_token,
                "documentType": "A65",
                "processType": "A16",
                "outBiddingZone_Domain": out_bidding_zone_domain,
                "periodStart": period_start,
                "periodEnd": period_end,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_total_load_xml(response.text)

    def fetch_aggregated_generation_per_type(
        self,
        *,
        in_domain: str,
        period_start: str,
        period_end: str,
    ) -> list[dict]:
        response = self.session.get(
            self.base_url,
            params={
                "securityToken": self.security_token,
                "documentType": "A75",
                "processType": "A16",
                "in_Domain": in_domain,
                "periodStart": period_start,
                "periodEnd": period_end,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_aggregated_generation_per_type_xml(response.text)

    def fetch_physical_flows(
        self,
        *,
        in_domain: str,
        out_domain: str,
        period_start: str,
        period_end: str,
    ) -> list[dict]:
        response = self.session.get(
            self.base_url,
            params={
                "securityToken": self.security_token,
                "documentType": "A11",
                "in_Domain": in_domain,
                "out_Domain": out_domain,
                "periodStart": period_start,
                "periodEnd": period_end,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_physical_flows_xml(response.text)

    def fetch_generation_forecast(
        self,
        *,
        in_domain: str,
        period_start: str,
        period_end: str,
    ) -> list[dict]:
        response = self.session.get(
            self.base_url,
            params={
                "securityToken": self.security_token,
                "documentType": "A71",
                "processType": "A01",
                "in_Domain": in_domain,
                "periodStart": period_start,
                "periodEnd": period_end,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_generation_forecast_xml(response.text)

    def _parse_day_ahead_prices_xml(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        rows: list[dict] = []
        for timeseries in root.findall("ns:TimeSeries", ENTSOE_XML_NS):
            currency = timeseries.findtext("ns:currency_Unit.name", default="EUR", namespaces=ENTSOE_XML_NS)
            unit_name = timeseries.findtext("ns:price_Measure_Unit.name", default="MWH", namespaces=ENTSOE_XML_NS)
            for period in timeseries.findall("ns:Period", ENTSOE_XML_NS):
                start_text = period.findtext("ns:timeInterval/ns:start", namespaces=ENTSOE_XML_NS)
                resolution = period.findtext("ns:resolution", namespaces=ENTSOE_XML_NS)
                if not start_text:
                    continue
                start_utc = datetime.fromisoformat(start_text.replace("Z", "+00:00")).astimezone(timezone.utc)
                step = _parse_resolution(resolution)
                for point in period.findall("ns:Point", ENTSOE_XML_NS):
                    position_text = point.findtext("ns:position", namespaces=ENTSOE_XML_NS)
                    price_text = point.findtext("ns:price.amount", namespaces=ENTSOE_XML_NS)
                    if not position_text or price_text is None:
                        continue
                    position = int(position_text)
                    timestamp = start_utc + (position - 1) * step
                    rows.append(
                        {
                            "timestamp_utc": _to_utc_z(timestamp),
                            "price": float(price_text),
                            "currency": currency,
                            "unit": unit_name,
                            "resolution": resolution or "PT60M",
                        }
                    )
        return rows

    def _parse_total_load_xml(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        rows: list[dict] = []
        for timeseries in root.findall("ns:TimeSeries", ENTSOE_LOAD_XML_NS):
            for period in timeseries.findall("ns:Period", ENTSOE_LOAD_XML_NS):
                start_text = period.findtext("ns:timeInterval/ns:start", namespaces=ENTSOE_LOAD_XML_NS)
                resolution = period.findtext("ns:resolution", namespaces=ENTSOE_LOAD_XML_NS)
                if not start_text:
                    continue
                start_utc = datetime.fromisoformat(start_text.replace("Z", "+00:00")).astimezone(timezone.utc)
                step = _parse_resolution(resolution)
                for point in period.findall("ns:Point", ENTSOE_LOAD_XML_NS):
                    position_text = point.findtext("ns:position", namespaces=ENTSOE_LOAD_XML_NS)
                    quantity_text = point.findtext("ns:quantity", namespaces=ENTSOE_LOAD_XML_NS)
                    if not position_text or quantity_text is None:
                        continue
                    position = int(position_text)
                    timestamp = start_utc + (position - 1) * step
                    rows.append(
                        {
                            "timestamp_utc": _to_utc_z(timestamp),
                            "load_mw": float(quantity_text),
                            "resolution": resolution or "PT60M",
                        }
                    )
        return rows

    def _parse_aggregated_generation_per_type_xml(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        rows: list[dict] = []
        for timeseries in root.findall("ns:TimeSeries", ENTSOE_LOAD_XML_NS):
            psr_type = timeseries.findtext("ns:MktPSRType/ns:psrType", namespaces=ENTSOE_LOAD_XML_NS)
            for period in timeseries.findall("ns:Period", ENTSOE_LOAD_XML_NS):
                start_text = period.findtext("ns:timeInterval/ns:start", namespaces=ENTSOE_LOAD_XML_NS)
                resolution = period.findtext("ns:resolution", namespaces=ENTSOE_LOAD_XML_NS)
                if not start_text:
                    continue
                start_utc = datetime.fromisoformat(start_text.replace("Z", "+00:00")).astimezone(timezone.utc)
                step = _parse_resolution(resolution)
                for point in period.findall("ns:Point", ENTSOE_LOAD_XML_NS):
                    position_text = point.findtext("ns:position", namespaces=ENTSOE_LOAD_XML_NS)
                    quantity_text = point.findtext("ns:quantity", namespaces=ENTSOE_LOAD_XML_NS)
                    if not position_text or quantity_text is None:
                        continue
                    position = int(position_text)
                    timestamp = start_utc + (position - 1) * step
                    rows.append(
                        {
                            "timestamp_utc": _to_utc_z(timestamp),
                            "quantity_mw": float(quantity_text),
                            "psr_type": psr_type,
                            "resolution": resolution or "PT60M",
                        }
                    )
        return rows

    def _parse_physical_flows_xml(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        rows: list[dict] = []
        for timeseries in root.findall("ns:TimeSeries", ENTSOE_XML_NS):
            in_domain = timeseries.findtext("ns:in_Domain.mRID", namespaces=ENTSOE_XML_NS)
            out_domain = timeseries.findtext("ns:out_Domain.mRID", namespaces=ENTSOE_XML_NS)
            for period in timeseries.findall("ns:Period", ENTSOE_XML_NS):
                start_text = period.findtext("ns:timeInterval/ns:start", namespaces=ENTSOE_XML_NS)
                resolution = period.findtext("ns:resolution", namespaces=ENTSOE_XML_NS)
                if not start_text:
                    continue
                start_utc = datetime.fromisoformat(start_text.replace("Z", "+00:00")).astimezone(timezone.utc)
                step = _parse_resolution(resolution)
                for point in period.findall("ns:Point", ENTSOE_XML_NS):
                    position_text = point.findtext("ns:position", namespaces=ENTSOE_XML_NS)
                    quantity_text = point.findtext("ns:quantity", namespaces=ENTSOE_XML_NS)
                    if not position_text or quantity_text is None:
                        continue
                    position = int(position_text)
                    timestamp = start_utc + (position - 1) * step
                    rows.append(
                        {
                            "timestamp_utc": _to_utc_z(timestamp),
                            "flow_mw": float(quantity_text),
                            "in_domain": in_domain,
                            "out_domain": out_domain,
                            "resolution": resolution or "PT60M",
                        }
                    )
        return rows

    def _parse_generation_forecast_xml(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        rows: list[dict] = []
        for timeseries in root.findall("ns:TimeSeries", ENTSOE_LOAD_XML_NS):
            for period in timeseries.findall("ns:Period", ENTSOE_LOAD_XML_NS):
                start_text = period.findtext("ns:timeInterval/ns:start", namespaces=ENTSOE_LOAD_XML_NS)
                resolution = period.findtext("ns:resolution", namespaces=ENTSOE_LOAD_XML_NS)
                if not start_text:
                    continue
                start_utc = datetime.fromisoformat(start_text.replace("Z", "+00:00")).astimezone(timezone.utc)
                step = _parse_resolution(resolution)
                for point in period.findall("ns:Point", ENTSOE_LOAD_XML_NS):
                    position_text = point.findtext("ns:position", namespaces=ENTSOE_LOAD_XML_NS)
                    quantity_text = point.findtext("ns:quantity", namespaces=ENTSOE_LOAD_XML_NS)
                    if not position_text or quantity_text is None:
                        continue
                    position = int(position_text)
                    timestamp = start_utc + (position - 1) * step
                    rows.append(
                        {
                            "timestamp_utc": _to_utc_z(timestamp),
                            "generation_forecast_mw": float(quantity_text),
                            "resolution": resolution or "PT60M",
                        }
                    )
        return rows
