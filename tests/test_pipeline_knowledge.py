"""Unit tests for asset & pipeline knowledge service (管线知识库, 2026-08-13)."""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.pipeline_knowledge import (
    ACTIVE_STATUSES,
    search_projects,
    summarize_pipeline,
)


class SummaryTests(unittest.TestCase):
    def test_summary_structure_and_active_supply(self):
        s = summarize_pipeline()
        self.assertTrue(s["available"])
        self.assertEqual(s["region"], "ALL")
        self.assertIn("by_status", s)
        self.assertGreater(s["active_supply_mw"], 0.0)
        self.assertEqual(s["active_statuses"], list(ACTIVE_STATUSES))
        # planning 不计入活跃供给
        planning_mw = s["by_status"].get("planning", {}).get("capacity_mw", 0.0)
        active_sum = sum(
            s["by_status"][st]["capacity_mw"] for st in ACTIVE_STATUSES if st in s["by_status"]
        )
        self.assertAlmostEqual(s["active_supply_mw"], round(active_sum, 1), places=1)
        self.assertGreaterEqual(planning_mw, 0.0)

    def test_region_filter(self):
        s = summarize_pipeline(region="qld1")
        self.assertTrue(s["available"])
        self.assertEqual(s["region"], "QLD1")
        self.assertGreater(s["active_supply_mw"], 0.0)

    def test_market_anchors_present(self):
        s = summarize_pipeline()
        anchors = s["market_pipeline_anchors"]
        self.assertIsNotNone(anchors)
        metrics = {a["metric"] for a in anchors["anchors"]}
        self.assertIn("nem_bess_pipeline_gw", metrics)

    def test_freshness_fields(self):
        s = summarize_pipeline()
        fresh = s["freshness"]
        self.assertIn("last_updated", fresh)
        self.assertIn("age_days", fresh)
        self.assertIn("stale", fresh)


class SearchProjectsTests(unittest.TestCase):
    def test_search_by_region_and_status(self):
        result = search_projects(region="QLD1", status="registered")
        self.assertTrue(result["available"])
        for p in result["matches"]:
            self.assertEqual(p["region"], "QLD1")
            self.assertEqual(p["status"], "registered")

    def test_search_by_name_substring(self):
        result = search_projects(name_contains="hornsdale")
        self.assertGreaterEqual(result["total_after_filter"], 1)
        self.assertIn("Hornsdale", result["matches"][0]["project_name"])

    def test_no_hit_returns_empty(self):
        result = search_projects(name_contains="zzz_no_such_project")
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["total_after_filter"], 0)


class AgentToolTests(unittest.TestCase):
    def test_tool_registered_and_executes(self):
        from agent.schemas import AgentContext
        from agent.tools import build_tool_registry

        registry = build_tool_registry()
        self.assertIsNotNone(registry.get_definition("asset_pipeline_lookup"))

        # summary 模式
        s = registry.get_executor("asset_pipeline_lookup")(
            {"mode": "summary", "region": "SA1"}, AgentContext()
        )
        self.assertTrue(s["available"])
        self.assertEqual(s["region"], "SA1")

        # projects 模式
        p = registry.get_executor("asset_pipeline_lookup")(
            {"mode": "projects", "region": "QLD1"}, AgentContext()
        )
        self.assertTrue(p["available"])
        self.assertGreater(p["total_after_filter"], 0)

    def test_profiles_expose_tool(self):
        from agent.tool_profiles import TOOL_PROFILES

        for profile in ("stage3_saturation", "stage4_outlook"):
            self.assertIn("asset_pipeline_lookup", TOOL_PROFILES[profile])


if __name__ == "__main__":
    unittest.main()
