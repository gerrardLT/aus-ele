"""Unit tests for market event case library & lookup tool (2026-08-13)."""

import json
import os
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.market_events import (
    _EVENTS_PATH,
    get_event,
    search_events,
)


class EventsFileTests(unittest.TestCase):
    def test_events_file_loads_with_five_cases(self):
        self.assertTrue(os.path.exists(_EVENTS_PATH))
        with open(_EVENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertGreaterEqual(len(data["events"]), 5)

    def test_events_carry_causal_fields(self):
        with open(_EVENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for event in data["events"]:
            for field in ("summary", "impact", "lessons", "source_url", "confidence", "period"):
                self.assertIn(field, event, f"{event['id']} 缺 {field}")
            impact = event["impact"]
            self.assertIn("price", impact)
            self.assertIn("bess", impact)
            self.assertGreater(len(event["lessons"]), 0)

    def test_ids_unique(self):
        with open(_EVENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        ids = [e["id"] for e in data["events"]]
        self.assertEqual(len(ids), len(set(ids)))


class SearchEventsTests(unittest.TestCase):
    def test_search_negative_price_hits_wave_case(self):
        result = search_events(query="负价")
        self.assertTrue(result["available"])
        ids = [m["id"] for m in result["matches"]]
        self.assertIn("negative_price_wave_2025q4", ids)

    def test_category_filter(self):
        result = search_events(category="fcas_collapse")
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["id"], "fcas_collapse_2024_2026")

    def test_no_hit_returns_empty(self):
        result = search_events(query="zzz_no_such_event_zzz")
        self.assertEqual(result["matches"], [])

    def test_get_event(self):
        event = get_event("sa_black_system_2016")
        self.assertIsNotNone(event)
        self.assertEqual(event["market"], "NEM")
        self.assertIsNone(get_event("no_such_event"))


class AgentToolTests(unittest.TestCase):
    def test_tool_registered_and_executes(self):
        from agent.schemas import AgentContext
        from agent.tools import build_tool_registry

        registry = build_tool_registry()
        self.assertIsNotNone(registry.get_definition("market_event_lookup"))

        result = registry.get_executor("market_event_lookup")(
            {"query": "FCAS 崩塌"}, AgentContext()
        )
        self.assertTrue(result["available"])
        self.assertGreaterEqual(len(result["matches"]), 1)
        for m in result["matches"]:
            self.assertIn("source_url", m)
            self.assertIn("lessons", m)

    def test_profiles_expose_tool(self):
        from agent.tool_profiles import TOOL_PROFILES

        for profile in ("stage2_revenue", "stage4_outlook"):
            self.assertIn("market_event_lookup", TOOL_PROFILES[profile])


if __name__ == "__main__":
    unittest.main()
