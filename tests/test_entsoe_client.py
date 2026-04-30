import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from entsoe_client import EntsoeClient


class EntsoeClientTests(unittest.TestCase):
    @mock.patch("entsoe_client.requests.Session.get")
    def test_fetch_day_ahead_prices_uses_expected_query_and_parses_points(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries>
    <currency_Unit.name>EUR</currency_Unit.name>
    <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
    <Period>
      <timeInterval>
        <start>2026-04-28T00:00Z</start>
        <end>2026-04-28T02:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <price.amount>42.5</price.amount>
      </Point>
      <Point>
        <position>2</position>
        <price.amount>51.0</price.amount>
      </Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""
        mock_get.return_value = mock_response

        client = EntsoeClient(
            security_token="secret-token",
            base_url="https://web-api.tp.entsoe.eu/api",
            timeout_seconds=30,
        )
        rows = client.fetch_day_ahead_prices(
            in_domain="10YFI-1--------U",
            out_domain="10YFI-1--------U",
            period_start="202604280000",
            period_end="202604280200",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["price"], 42.5)
        self.assertEqual(rows[0]["currency"], "EUR")
        self.assertEqual(rows[0]["unit"], "MWH")
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["securityToken"], "secret-token")
        self.assertEqual(kwargs["params"]["documentType"], "A44")
        self.assertEqual(kwargs["params"]["processType"], "A01")
        self.assertEqual(kwargs["params"]["in_Domain"], "10YFI-1--------U")
        self.assertEqual(kwargs["params"]["out_Domain"], "10YFI-1--------U")

    @mock.patch("entsoe_client.requests.Session.get")
    def test_fetch_total_load_uses_expected_query_and_parses_points(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <Period>
      <timeInterval>
        <start>2026-04-28T00:00Z</start>
        <end>2026-04-28T02:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <quantity>8200</quantity>
      </Point>
      <Point>
        <position>2</position>
        <quantity>8350</quantity>
      </Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""
        mock_get.return_value = mock_response

        client = EntsoeClient(
            security_token="secret-token",
            base_url="https://web-api.tp.entsoe.eu/api",
            timeout_seconds=30,
        )
        rows = client.fetch_total_load(
            out_bidding_zone_domain="10YFI-1--------U",
            period_start="202604280000",
            period_end="202604280200",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["load_mw"], 8200.0)
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")
        self.assertEqual(rows[1]["load_mw"], 8350.0)

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["documentType"], "A65")
        self.assertEqual(kwargs["params"]["processType"], "A16")
        self.assertEqual(kwargs["params"]["outBiddingZone_Domain"], "10YFI-1--------U")

    @mock.patch("entsoe_client.requests.Session.get")
    def test_fetch_aggregated_generation_per_type_uses_expected_query_and_parses_points(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <MktPSRType>
      <psrType>B16</psrType>
    </MktPSRType>
    <Period>
      <timeInterval>
        <start>2026-04-28T00:00Z</start>
        <end>2026-04-28T02:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <quantity>4100</quantity>
      </Point>
      <Point>
        <position>2</position>
        <quantity>4300</quantity>
      </Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""
        mock_get.return_value = mock_response

        client = EntsoeClient(
            security_token="secret-token",
            base_url="https://web-api.tp.entsoe.eu/api",
            timeout_seconds=30,
        )
        rows = client.fetch_aggregated_generation_per_type(
            in_domain="10YFI-1--------U",
            period_start="202604280000",
            period_end="202604280200",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["quantity_mw"], 4100.0)
        self.assertEqual(rows[0]["psr_type"], "B16")
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["documentType"], "A75")
        self.assertEqual(kwargs["params"]["processType"], "A16")
        self.assertEqual(kwargs["params"]["in_Domain"], "10YFI-1--------U")

    @mock.patch("entsoe_client.requests.Session.get")
    def test_fetch_physical_flows_uses_expected_query_and_parses_points(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries>
    <in_Domain.mRID codingScheme="A01">10YFI-1--------U</in_Domain.mRID>
    <out_Domain.mRID codingScheme="A01">10YSE-1--------K</out_Domain.mRID>
    <Period>
      <timeInterval>
        <start>2026-04-28T00:00Z</start>
        <end>2026-04-28T02:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <quantity>850</quantity>
      </Point>
      <Point>
        <position>2</position>
        <quantity>910</quantity>
      </Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""
        mock_get.return_value = mock_response

        client = EntsoeClient(
            security_token="secret-token",
            base_url="https://web-api.tp.entsoe.eu/api",
            timeout_seconds=30,
        )
        rows = client.fetch_physical_flows(
            in_domain="10YFI-1--------U",
            out_domain="10YSE-1--------K",
            period_start="202604280000",
            period_end="202604280200",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["flow_mw"], 850.0)
        self.assertEqual(rows[0]["in_domain"], "10YFI-1--------U")
        self.assertEqual(rows[0]["out_domain"], "10YSE-1--------K")
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["documentType"], "A11")
        self.assertEqual(kwargs["params"]["in_Domain"], "10YFI-1--------U")
        self.assertEqual(kwargs["params"]["out_Domain"], "10YSE-1--------K")

    @mock.patch("entsoe_client.requests.Session.get")
    def test_fetch_generation_forecast_uses_expected_query_and_parses_points(self, mock_get):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <Period>
      <timeInterval>
        <start>2026-04-28T00:00Z</start>
        <end>2026-04-28T02:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <quantity>7600</quantity>
      </Point>
      <Point>
        <position>2</position>
        <quantity>7800</quantity>
      </Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""
        mock_get.return_value = mock_response

        client = EntsoeClient(
            security_token="secret-token",
            base_url="https://web-api.tp.entsoe.eu/api",
            timeout_seconds=30,
        )
        rows = client.fetch_generation_forecast(
            in_domain="10YFI-1--------U",
            period_start="202604280000",
            period_end="202604280200",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["timestamp_utc"], "2026-04-28T00:00:00Z")
        self.assertEqual(rows[0]["generation_forecast_mw"], 7600.0)
        self.assertEqual(rows[1]["timestamp_utc"], "2026-04-28T01:00:00Z")
        self.assertEqual(rows[1]["generation_forecast_mw"], 7800.0)

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["documentType"], "A71")
        self.assertEqual(kwargs["params"]["processType"], "A01")
        self.assertEqual(kwargs["params"]["in_Domain"], "10YFI-1--------U")


if __name__ == "__main__":
    unittest.main()
