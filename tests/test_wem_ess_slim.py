import json
import os
import tempfile
import unittest
from unittest import mock

from database import DatabaseManager
import server
import aemo_wem_ess_scraper


class FakeResponseCache:
    def __init__(self):
        self.store = {}

    def get_json(self, scope: str, cache_key: str):
        payload = self.store.get((scope, cache_key))
        return json.loads(json.dumps(payload)) if payload is not None else None

    def set_json(self, scope: str, cache_key: str, value, ttl_seconds: int):
        self.store[(scope, cache_key)] = json.loads(json.dumps(value))


SAMPLE_DISPATCH_PAYLOAD = {
    "data": {
        "solutionData": [
            {
                "scenario": "Reference",
                "dispatchType": "Dispatch",
                "dispatchInterval": "2026-04-13T08:00:00+08:00",
                "prices": {
                    "energy": 96.12,
                    "regulationRaise": 15.0,
                    "regulationLower": 11.0,
                    "contingencyRaise": 6.0,
                    "contingencyLower": 4.0,
                    "rocof": 3.0,
                },
                "availableQuantities": {
                    "energyInjectionCapacity": 962.178,
                    "energyWithdrawalCapacity": 0.0,
                    "contingencyRaise": 329.771,
                    "contingencyLower": 331.636,
                    "regulationRaise": 435.296,
                    "regulationLower": 437.024,
                    "rocof": 5966.0,
                },
                "inServiceQuantities": {
                    "energyInjectionCapacity": 4774.165,
                    "energyWithdrawalCapacity": -1135.0,
                    "contingencyRaise": 980.4,
                    "contingencyLower": 1055.398,
                    "regulationRaise": 979.74,
                    "regulationLower": 979.74,
                    "rocof": 12124.5,
                },
                "marketServiceRequirements": {
                    "energy": 1993.328,
                    "regulationRaise": 110.0,
                    "regulationLower": 110.0,
                    "contingencyRaise": 258.268,
                    "contingencyLower": 72.308,
                    "rocof": 12124.5,
                },
                "marketShortfalls": {
                    "energyDeficit": 0.0,
                    "regulationRaiseDeficit": 0.0,
                    "regulationLowerDeficit": 0.0,
                    "contingencyRaiseDeficit": 0.0,
                    "contingencyLowerDeficit": 0.0,
                    "rocofDeficit": 0.0,
                },
                "dispatchTotal": {
                    "energyInjectionCapacity": 2053.328,
                    "energyWithdrawalCapacity": -60.0,
                    "contingencyRaise": 268.853,
                    "contingencyLower": 72.308,
                    "regulationRaise": 110.0,
                    "regulationLower": 110.0,
                    "rocof": 12124.5,
                },
                "priceSetting": [
                    {"marketService": "energy", "isMarketServiceCapped": False},
                    {"marketService": "regulationRaise", "isMarketServiceCapped": True},
                ],
                "constraints": [
                    {
                        "id": "SystemEnergyBalance",
                        "constraintType": "Formulation",
                        "bindingConstraintFlag": True,
                        "nearBindingConstraintFlag": True,
                        "shadowPrice": 96.12,
                    },
                    {
                        "id": "OtherConstraint",
                        "constraintType": "Facility",
                        "bindingConstraintFlag": False,
                        "nearBindingConstraintFlag": True,
                        "shadowPrice": 15.0,
                    },
                ],
            }
        ]
    }
}

SAMPLE_HISTORICAL_DISPATCH_PAYLOAD = {
    "data": {
        "solutionData": [
            {
                "dispatchInterval": "2025-01-01T08:00:00+08:00",
                "prices": {
                    "energy": 105.5,
                    "regulationRaise": 12.0,
                    "regulationLower": 8.0,
                    "contingencyRaise": 4.0,
                    "contingencyLower": 3.0,
                    "rocof": 2.0,
                },
                "availableQuantities": {
                    "contingencyRaise": 200.0,
                    "contingencyLower": 180.0,
                    "regulationRaise": 150.0,
                    "regulationLower": 155.0,
                    "rocof": 500.0,
                },
                "inServiceQuantities": {
                    "contingencyRaise": 260.0,
                    "contingencyLower": 240.0,
                    "regulationRaise": 170.0,
                    "regulationLower": 172.0,
                    "rocof": 520.0,
                },
                "marketServiceRequirements": {
                    "regulationRaise": 110.0,
                    "regulationLower": 110.0,
                    "contingencyRaise": 120.0,
                    "contingencyLower": 70.0,
                    "rocof": 500.0,
                },
                "marketShortfalls": {
                    "regulationRaiseDeficit": 0.0,
                    "regulationLowerDeficit": 0.0,
                    "contingencyRaiseDeficit": 0.0,
                    "contingencyLowerDeficit": 0.0,
                    "rocofDeficit": 0.0,
                },
                "dispatchTotal": {
                    "regulationRaise": 110.0,
                    "regulationLower": 110.0,
                    "contingencyRaise": 121.0,
                    "contingencyLower": 70.0,
                    "rocof": 500.0,
                },
                "priceSetting": [],
                "constraints": [],
            }
        ]
    }
}

SAMPLE_MULTI_INTERVAL_PAYLOAD = {
    "data": {
        "primaryDispatchInterval": "2026-04-13T08:05:00+08:00",
        "solutionData": [
            {
                "scenario": "Reference",
                "dispatchType": "Dispatch",
                "dispatchInterval": "2026-04-13T08:00:00+08:00",
                "prices": {"energy": 90.0, "regulationRaise": 1.0},
                "availableQuantities": {"regulationRaise": 10.0},
                "inServiceQuantities": {"regulationRaise": 20.0},
                "marketServiceRequirements": {"regulationRaise": 5.0},
                "marketShortfalls": {"regulationRaiseDeficit": 0.0},
                "dispatchTotal": {"regulationRaise": 5.0},
                "priceSetting": [],
                "constraints": [],
            },
            {
                "scenario": "Reference",
                "dispatchType": "Dispatch",
                "dispatchInterval": "2026-04-13T08:05:00+08:00",
                "prices": {"energy": 95.0, "regulationRaise": 2.0},
                "availableQuantities": {"regulationRaise": 11.0},
                "inServiceQuantities": {"regulationRaise": 21.0},
                "marketServiceRequirements": {"regulationRaise": 6.0},
                "marketShortfalls": {"regulationRaiseDeficit": 0.0},
                "dispatchTotal": {"regulationRaise": 6.0},
                "priceSetting": [],
                "constraints": [],
            },
        ],
    }
}


class WemEssSlimParsingTests(unittest.TestCase):
    def test_extract_slim_solution_rows_returns_market_and_constraint_rows(self):
        raw = json.dumps(SAMPLE_DISPATCH_PAYLOAD).encode("utf-8")

        market_rows, constraint_rows = aemo_wem_ess_scraper.extract_slim_solution_rows(raw)

        self.assertEqual(len(market_rows), 1)
        self.assertEqual(len(constraint_rows), 1)

        market = market_rows[0]
        self.assertEqual(market["dispatch_interval"], "2026-04-13 08:00:00")
        self.assertEqual(market["regulation_raise_price"], 15.0)
        self.assertEqual(market["available_regulation_raise"], 435.296)
        self.assertEqual(market["in_service_rocof"], 12124.5)
        self.assertEqual(market["requirement_contingency_lower"], 72.308)
        self.assertEqual(market["shortfall_regulation_raise"], 0.0)
        self.assertEqual(market["dispatch_total_contingency_raise"], 268.853)
        self.assertEqual(market["capped_regulation_raise"], 1)

        constraint = constraint_rows[0]
        self.assertEqual(constraint["dispatch_interval"], "2026-04-13 08:00:00")
        self.assertEqual(constraint["binding_count"], 1)
        self.assertEqual(constraint["near_binding_count"], 2)
        self.assertEqual(constraint["binding_max_shadow_price"], 96.12)
        self.assertEqual(constraint["max_formulation_shadow_price"], 96.12)
        self.assertEqual(constraint["max_facility_shadow_price"], 0.0)

    def test_extract_slim_solution_rows_accepts_historical_rows_without_scenario_fields(self):
        raw = json.dumps(SAMPLE_HISTORICAL_DISPATCH_PAYLOAD).encode("utf-8")

        market_rows, constraint_rows = aemo_wem_ess_scraper.extract_slim_solution_rows(raw)

        self.assertEqual(len(market_rows), 1)
        self.assertEqual(len(constraint_rows), 1)
        self.assertEqual(market_rows[0]["dispatch_interval"], "2025-01-01 08:00:00")
        self.assertEqual(market_rows[0]["regulation_raise_price"], 12.0)
        self.assertEqual(market_rows[0]["dispatch_total_contingency_raise"], 121.0)

    def test_extract_slim_solution_rows_uses_primary_dispatch_interval_when_present(self):
        raw = json.dumps(SAMPLE_MULTI_INTERVAL_PAYLOAD).encode("utf-8")

        market_rows, constraint_rows = aemo_wem_ess_scraper.extract_slim_solution_rows(raw)

        self.assertEqual(len(market_rows), 1)
        self.assertEqual(len(constraint_rows), 1)
        self.assertEqual(market_rows[0]["dispatch_interval"], "2026-04-13 08:05:00")
        self.assertEqual(market_rows[0]["regulation_raise_price"], 2.0)

    def test_download_bytes_resumes_partial_stream_downloads(self):
        class FakeResponse:
            def __init__(self, status_code, headers, chunks, error=None):
                self.status_code = status_code
                self.headers = headers
                self._chunks = chunks
                self._error = error

            def iter_content(self, chunk_size=0):
                for chunk in self._chunks:
                    yield chunk
                if self._error:
                    raise self._error

        calls = []
        responses = [
            FakeResponse(
                200,
                {"Content-Length": "6"},
                [b"abc"],
                error=aemo_wem_ess_scraper.requests.exceptions.ChunkedEncodingError("boom"),
            ),
            FakeResponse(
                206,
                {"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
                [b"def"],
            ),
        ]

        def fake_get(url, headers, timeout, verify, stream):
            calls.append(headers.copy())
            return responses.pop(0)

        with mock.patch.object(aemo_wem_ess_scraper.requests, "get", side_effect=fake_get):
            with mock.patch.object(aemo_wem_ess_scraper.time, "sleep", return_value=None):
                payload = aemo_wem_ess_scraper.download_bytes(
                    "https://example.com/file.zip",
                    "resume-test",
                    stream=True,
                    max_retries=2,
                )

        self.assertEqual(payload, b"abcdef")
        self.assertNotIn("Range", calls[0])
        self.assertEqual(calls[1]["Range"], "bytes=3-")

    def test_download_bytes_ignores_stdout_flush_errors(self):
        class FakeResponse:
            def __init__(self, status_code, headers, chunks):
                self.status_code = status_code
                self.headers = headers
                self._chunks = chunks

            def iter_content(self, chunk_size=0):
                yield from self._chunks

        response = FakeResponse(
            200,
            {"Content-Length": "6"},
            [b"abcdef"],
        )

        with mock.patch.object(aemo_wem_ess_scraper.requests, "get", return_value=response):
            with mock.patch.object(aemo_wem_ess_scraper.sys.stdout, "flush", side_effect=OSError(22, "Invalid argument")):
                payload = aemo_wem_ess_scraper.download_bytes(
                    "https://example.com/file.zip",
                    "flush-test",
                    stream=True,
                    max_retries=1,
                )

        self.assertEqual(payload, b"abcdef")


class WemEssAnalysisEndpointTests(unittest.TestCase):
    def test_wem_fcas_analysis_uses_slim_market_table(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            db = DatabaseManager(path)
            with db.get_connection() as conn:
                db.ensure_wem_ess_tables(conn)
                conn.execute(
                    """
                    INSERT INTO wem_ess_market_price (
                        dispatch_interval,
                        energy_price,
                        regulation_raise_price,
                        regulation_lower_price,
                        contingency_raise_price,
                        contingency_lower_price,
                        rocof_price,
                        available_regulation_raise,
                        available_regulation_lower,
                        available_contingency_raise,
                        available_contingency_lower,
                        available_rocof,
                        in_service_regulation_raise,
                        in_service_regulation_lower,
                        in_service_contingency_raise,
                        in_service_contingency_lower,
                        in_service_rocof,
                        requirement_regulation_raise,
                        requirement_regulation_lower,
                        requirement_contingency_raise,
                        requirement_contingency_lower,
                        requirement_rocof,
                        shortfall_regulation_raise,
                        shortfall_regulation_lower,
                        shortfall_contingency_raise,
                        shortfall_contingency_lower,
                        shortfall_rocof,
                        dispatch_total_regulation_raise,
                        dispatch_total_regulation_lower,
                        dispatch_total_contingency_raise,
                        dispatch_total_contingency_lower,
                        dispatch_total_rocof,
                        capped_regulation_raise,
                        capped_regulation_lower,
                        capped_contingency_raise,
                        capped_contingency_lower,
                        capped_rocof
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        "2026-04-13 08:00:00",
                        96.12,
                        15.0,
                        11.0,
                        6.0,
                        4.0,
                        3.0,
                        435.296,
                        437.024,
                        329.771,
                        331.636,
                        5966.0,
                        979.74,
                        979.74,
                        980.4,
                        1055.398,
                        12124.5,
                        110.0,
                        110.0,
                        258.268,
                        72.308,
                        12124.5,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        110.0,
                        110.0,
                        268.853,
                        72.308,
                        12124.5,
                        1,
                        0,
                        0,
                        0,
                        0,
                    ),
                )
                conn.commit()

            original_db = server.db
            original_cache = server.response_cache
            server.db = db
            server.response_cache = FakeResponseCache()
            try:
                result = server.get_fcas_analysis(
                    year=2026,
                    region="WEM",
                    aggregation="daily",
                    capacity_mw=100,
                )
            finally:
                server.db = original_db
                server.response_cache = original_cache

            self.assertTrue(result["has_fcas_data"])
            self.assertEqual(result["region"], "WEM")
            keys = {item["key"] for item in result["service_breakdown"]}
            self.assertIn("regulation_raise", keys)
            self.assertIn("rocof", keys)
            self.assertEqual(result["summary"]["data_points_with_fcas"], 1)
        finally:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass


if __name__ == "__main__":
    unittest.main()
