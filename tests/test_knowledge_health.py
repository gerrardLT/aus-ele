"""Unit tests for knowledge base health service (知识库健康检查, 2026-08-13)."""

import unittest
from datetime import date

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.knowledge_health import (
    _latest_calibration_date,
    build_health_report,
    check_benchmark_calibration,
    check_events_library,
    check_pipeline_freshness,
    check_rule_reviews,
)


class ReportStructureTests(unittest.TestCase):
    def test_report_structure_and_summary(self):
        report = build_health_report(today=date(2026, 8, 13))
        self.assertIn("generated_at", report)
        self.assertIn("healthy", report)
        self.assertIn("summary", report)
        self.assertGreater(len(report["items"]), 0)
        # summary 计数与 items 一致
        for status in ("overdue", "due_soon", "ok", "informational"):
            expected = sum(1 for i in report["items"] if i["status"] == status)
            self.assertEqual(report["summary"].get(status, 0), expected)

    def test_every_item_has_sop_reference(self):
        report = build_health_report(today=date(2026, 8, 13))
        for item in report["items"]:
            self.assertIn("运营节奏清单", item["sop_ref"])


class PipelineFreshnessTests(unittest.TestCase):
    def test_current_data_is_ok(self):
        # capacity_data.json last_updated=2026-05-29，距 2026-08-13 约 76 天 < 90
        item = check_pipeline_freshness(today=date(2026, 8, 13))
        self.assertEqual(item["status"], "ok")

    def test_due_soon_threshold(self):
        # 95 天后 → due_soon
        item = check_pipeline_freshness(today=date(2026, 9, 1))
        self.assertEqual(item["status"], "due_soon")

    def test_overdue_threshold(self):
        # 超过 120 天 → overdue
        item = check_pipeline_freshness(today=date(2026, 10, 15))
        self.assertEqual(item["status"], "overdue")


class RuleReviewTests(unittest.TestCase):
    def test_review_dates_classified(self):
        items = check_rule_reviews(today=date(2026, 8, 13))
        self.assertGreater(len(items), 0)
        by_id = {i["id"]: i for i in items}
        # review_date=2026-09-12 的条目（PFR/Operating Reserve）距 30 天 → due_soon
        sept = [i for i in items if i["due_date"] == "2026-09-12"]
        self.assertTrue(sept)
        self.assertTrue(all(i["status"] == "due_soon" for i in sept))
        # review_date=2026-11-12 的条目还有 91 天 → ok
        nov = [i for i in items if i["due_date"] == "2026-11-12"]
        self.assertTrue(nov)
        self.assertTrue(all(i["status"] == "ok" for i in nov))

    def test_overdue_when_past_review_date(self):
        items = check_rule_reviews(today=date(2026, 12, 31))
        self.assertTrue(all(i["status"] == "overdue" for i in items))


class CalibrationTests(unittest.TestCase):
    def test_parses_latest_calibration_date(self):
        last = _latest_calibration_date()
        self.assertIsNotNone(last)
        self.assertGreaterEqual(last, date(2026, 8, 1))

    def test_calibration_ok_right_after_entry(self):
        item = check_benchmark_calibration(today=date(2026, 8, 13))
        self.assertEqual(item["status"], "ok")

    def test_calibration_overdue_after_35_days(self):
        item = check_benchmark_calibration(today=date(2026, 10, 1))
        self.assertEqual(item["status"], "overdue")


class EventsLibraryTests(unittest.TestCase):
    def test_events_informational(self):
        item = check_events_library(today=date(2026, 8, 13))
        self.assertEqual(item["status"], "informational")
        self.assertIn("5 案例", item["detail"])


class AgentToolTests(unittest.TestCase):
    def test_tool_registered_and_executes(self):
        from agent.schemas import AgentContext
        from agent.tools import build_tool_registry

        registry = build_tool_registry()
        self.assertIsNotNone(registry.get_definition("knowledge_health_check"))
        result = registry.get_executor("knowledge_health_check")({}, AgentContext())
        self.assertIn("summary", result)
        self.assertIn("items", result)

    def test_stage1_profile_exposes_tool(self):
        from agent.tool_profiles import TOOL_PROFILES

        self.assertIn("knowledge_health_check", TOOL_PROFILES["stage1_screening"])


if __name__ == "__main__":
    unittest.main()
