import contextlib
import json
import os
import tempfile
import unittest
from unittest import mock

from database import DatabaseManager
import server


@contextlib.contextmanager
def patched_server_db(db_manager: DatabaseManager):
    original_db = server.db
    original_db_path = server.DB_PATH
    original_cache = server.response_cache
    server.db = db_manager
    server.DB_PATH = db_manager.db_path
    server.response_cache = FakeResponseCache()
    try:
        yield
    finally:
        server.db = original_db
        server.DB_PATH = original_db_path
        server.response_cache = original_cache


class FakeResponseCache:
    def __init__(self):
        self.store = {}

    def get_json(self, scope: str, cache_key: str):
        payload = self.store.get((scope, cache_key))
        return json.loads(json.dumps(payload)) if payload is not None else None

    def set_json(self, scope: str, cache_key: str, value, ttl_seconds: int):
        self.store[(scope, cache_key)] = json.loads(json.dumps(value))


@contextlib.contextmanager
def patched_server_response_cache(cache):
    original_cache = server.response_cache
    server.response_cache = cache
    try:
        yield
    finally:
        server.response_cache = original_cache


class EventOverlayLogicTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def test_market_notice_parser_maps_lor_notice_to_reserve_tightness(self):
        import grid_events

        raw_notice = """-------------------------------------------------------------------
                           MARKET NOTICE
-------------------------------------------------------------------

From :              AEMO
To   :              NEMITWEB1
Creation Date :     14/04/2026     09:10:48

-------------------------------------------------------------------

Notice ID               :         141082
Notice Type ID          :         RESERVE NOTICE
Notice Type Description :         Lack Of Reserve Notice
Issue Date              :         14/04/2026
External Reference      :         NSW region LOR2 condition declared

-------------------------------------------------------------------

Reason :

AEMO ELECTRICITY MARKET NOTICE.
NSW region LOR2 condition declared from 1030 hrs.

-------------------------------------------------------------------
END OF REPORT
-------------------------------------------------------------------
"""

        event = grid_events.parse_nem_market_notice_report(
            raw_notice,
            "https://www.nemweb.com.au/REPORTS/CURRENT/Market_Notice/NEMITWEB1_MKTNOTICE_20260414.R141082",
        )
        states = grid_events.normalize_raw_event_to_states(event)

        self.assertEqual(event["source_event_id"], "141082")
        self.assertIn("reserve_tightness", {state["state_type"] for state in states})
        self.assertTrue(any(state["region"] == "NSW1" for state in states))

    def test_merge_adjacent_states_collapses_same_region_and_type(self):
        import grid_events

        merged = grid_events.merge_explanation_states([
            {
                "market": "NEM",
                "region": "NSW1",
                "state_type": "reserve_tightness",
                "start_time": "2026-04-14 08:00:00",
                "end_time": "2026-04-14 09:00:00",
                "severity": "high",
                "confidence": 0.9,
                "headline": "LOR2 declared",
                "impact_domains": ["price_trend", "fcas_analysis"],
                "evidence_event_ids": [1],
                "evidence_summary_json": [{"source": "nem_market_notice"}],
            },
            {
                "market": "NEM",
                "region": "NSW1",
                "state_type": "reserve_tightness",
                "start_time": "2026-04-14 09:05:00",
                "end_time": "2026-04-14 10:00:00",
                "severity": "high",
                "confidence": 0.8,
                "headline": "LOR2 updated",
                "impact_domains": ["price_trend", "fcas_analysis"],
                "evidence_event_ids": [2],
                "evidence_summary_json": [{"source": "nem_market_notice"}],
            },
        ])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["start_time"], "2026-04-14 08:00:00")
        self.assertEqual(merged[0]["end_time"], "2026-04-14 10:00:00")
        self.assertEqual(set(merged[0]["evidence_event_ids"]), {1, 2})

    def test_event_overlay_endpoint_filters_month_and_day_type(self):
        self.db.upsert_grid_event_raw([
            {
                "market": "NEM",
                "source": "nem_market_notice",
                "source_event_id": "nem-1",
                "title": "NSW LOR2",
                "summary": "NSW region LOR2 condition declared.",
                "published_at": "2026-01-04 08:00:00",
                "effective_start": "2026-01-04 08:00:00",
                "effective_end": "2026-01-04 12:00:00",
                "region_scope": ["NSW1"],
                "asset_scope": [],
                "event_class_raw": "RESERVE NOTICE",
                "severity_raw": "high",
                "source_url": "https://example.com/nem-1",
                "raw_payload_json": {"body": "LOR2"},
            },
            {
                "market": "NEM",
                "source": "nem_market_notice",
                "source_event_id": "nem-2",
                "title": "NSW network outage",
                "summary": "Planned outage in NSW.",
                "published_at": "2026-04-06 08:00:00",
                "effective_start": "2026-04-06 08:00:00",
                "effective_end": "2026-04-06 18:00:00",
                "region_scope": ["NSW1"],
                "asset_scope": ["Line A"],
                "event_class_raw": "NETWORK OUTAGE",
                "severity_raw": "medium",
                "source_url": "https://example.com/nem-2",
                "raw_payload_json": {"body": "outage"},
            },
        ])
        self.db.replace_grid_event_states("NEM", [
            {
                "state_id": "state-nem-1",
                "market": "NEM",
                "region": "NSW1",
                "state_type": "reserve_tightness",
                "start_time": "2026-01-04 08:00:00",
                "end_time": "2026-01-04 12:00:00",
                "severity": "high",
                "confidence": 0.9,
                "headline": "NSW LOR2",
                "impact_domains": ["price_trend", "peak_analysis"],
                "evidence_event_ids": [1],
                "evidence_summary_json": [{"source": "nem_market_notice"}],
            },
            {
                "state_id": "state-nem-2",
                "market": "NEM",
                "region": "NSW1",
                "state_type": "network_stress",
                "start_time": "2026-04-06 08:00:00",
                "end_time": "2026-04-06 18:00:00",
                "severity": "medium",
                "confidence": 0.8,
                "headline": "NSW network outage",
                "impact_domains": ["price_trend", "peak_analysis"],
                "evidence_event_ids": [2],
                "evidence_summary_json": [{"source": "nem_market_notice"}],
            },
        ])
        self.db.upsert_grid_event_sync_states([
            {
                "source": "nem_market_notice",
                "last_success_at": "2026-04-14 10:00:00",
                "cursor": None,
                "last_backfill_at": "2026-04-14 10:00:00",
                "sync_status": "ok",
            },
            {
                "source": "bom_warnings",
                "last_success_at": "2026-04-14 10:00:00",
                "cursor": None,
                "last_backfill_at": "2026-04-14 10:00:00",
                "sync_status": "ok",
            },
        ])

        with patched_server_db(self.db):
            result = server.get_event_overlays(
                year=2026,
                region="NSW1",
                market=None,
                month="04",
                quarter="Q1",
                day_type="WEEKDAY",
            )

        self.assertEqual([state["state_id"] for state in result["states"]], ["state-nem-2"])
        self.assertEqual([rollup["date"] for rollup in result["daily_rollup"]], ["2026-04-06"])
        self.assertEqual(result["metadata"]["coverage_quality"], "partial")

    def test_event_overlay_endpoint_marks_wem_as_core_only(self):
        self.db.upsert_grid_event_raw([
            {
                "market": "WEM",
                "source": "wem_dispatch_advisory",
                "source_event_id": "wem-1",
                "title": "Low reserve advisory",
                "summary": "WEM low reserve condition.",
                "published_at": "2026-04-13 08:00:00",
                "effective_start": "2026-04-13 08:00:00",
                "effective_end": "2026-04-13 11:00:00",
                "region_scope": ["WEM"],
                "asset_scope": [],
                "event_class_raw": "Dispatch Advisory",
                "severity_raw": "high",
                "source_url": "https://example.com/wem-1",
                "raw_payload_json": {"body": "low reserve"},
            },
        ])
        self.db.replace_grid_event_states("WEM", [
            {
                "state_id": "state-wem-1",
                "market": "WEM",
                "region": "WEM",
                "state_type": "reserve_tightness",
                "start_time": "2026-04-13 08:00:00",
                "end_time": "2026-04-13 11:00:00",
                "severity": "high",
                "confidence": 0.85,
                "headline": "Low reserve advisory",
                "impact_domains": ["price_trend", "fcas_analysis"],
                "evidence_event_ids": [1],
                "evidence_summary_json": [{"source": "wem_dispatch_advisory"}],
            },
        ])
        self.db.upsert_grid_event_sync_states([
            {
                "source": "wem_dispatch_advisory",
                "last_success_at": "2026-04-14 10:00:00",
                "cursor": None,
                "last_backfill_at": "2026-04-14 10:00:00",
                "sync_status": "ok",
            },
            {
                "source": "wem_realtime_outage",
                "last_success_at": "2026-04-14 10:00:00",
                "cursor": None,
                "last_backfill_at": "2026-04-14 10:00:00",
                "sync_status": "ok",
            },
        ])

        with patched_server_db(self.db):
            result = server.get_event_overlays(
                year=2026,
                region="WEM",
                market=None,
                month=None,
                quarter=None,
                day_type=None,
            )

        self.assertEqual(result["metadata"]["coverage_quality"], "core_only")
        self.assertEqual(result["metadata"]["time_granularity"], "interval")
        self.assertEqual(result["daily_rollup"][0]["top_states"][0]["key"], "reserve_tightness")

    def test_event_overlay_endpoint_reports_no_verified_explanation(self):
        with patched_server_db(self.db):
            result = server.get_event_overlays(
                year=2026,
                region="NSW1",
                market=None,
                month="04",
                quarter=None,
                day_type=None,
            )

        self.assertEqual(result["metadata"]["coverage_quality"], "none")
        self.assertTrue(result["metadata"]["no_verified_event_explanation"])
        self.assertEqual(result["states"], [])
        self.assertEqual(result["events"], [])

    def test_event_overlay_route_uses_redis_response_cache(self):
        fake_cache = FakeResponseCache()
        fake_response = {
            "metadata": {"coverage_quality": "full", "no_verified_event_explanation": False},
            "states": [{"state_id": "demo"}],
            "daily_rollup": [],
            "events": [],
        }
        self.db.set_last_update_time("2026-04-16 10:15:00")

        with patched_server_db(self.db), patched_server_response_cache(fake_cache), \
            mock.patch("server._event_overlay_data_version", return_value="event-overlay-version"), \
            mock.patch("grid_events.get_event_overlay_response", return_value=fake_response) as mock_route:
            first = server.get_event_overlays(
                year=2026,
                region="NSW1",
                market="NEM",
                month="04",
                quarter=None,
                day_type=None,
            )
            second = server.get_event_overlays(
                year=2026,
                region="NSW1",
                market="NEM",
                month="04",
                quarter=None,
                day_type=None,
            )

        self.assertEqual(mock_route.call_count, 1)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
