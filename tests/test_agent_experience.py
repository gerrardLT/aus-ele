"""Unit tests for agent experience analytics service (经验库, 2026-08-13)."""

import json
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.agent_experience import (
    _extract_tool_usage,
    _KNOWN_TOOLS,
    build_experience_summary,
    classify_intent,
)


class IntentClassificationTests(unittest.TestCase):
    def test_investment_intent(self):
        self.assertEqual(classify_intent("SA1 100MW 投资 NPV 多少"), "investment")

    def test_benchmark_intent(self):
        self.assertEqual(classify_intent("当前市场基准收益如何"), "benchmark")

    def test_rules_knowledge_intent(self):
        self.assertEqual(classify_intent("什么是 FCAS"), "rules_knowledge")

    def test_events_intent(self):
        self.assertEqual(classify_intent("历史上 SA 大停电的影响"), "events")

    def test_unknown_falls_to_other(self):
        self.assertEqual(classify_intent("xyzzy"), "other")

    def test_empty_query(self):
        self.assertEqual(classify_intent(""), "empty")


class ToolUsageExtractionTests(unittest.TestCase):
    def test_extract_from_steps(self):
        steps = [
            {"tool_name": "price_trend_analysis", "status": "SUCCESS"},
            {"tool_name": "fcas_analysis", "status": "ERROR"},
            {"not_a_tool": True},
        ]
        usage = _extract_tool_usage(json.dumps(steps))
        self.assertEqual(len(usage), 2)
        self.assertEqual(usage[1], {"tool_name": "fcas_analysis", "status": "error"})

    def test_extract_action_observation_format(self):
        # 生产实际格式：steps[].action.tool_name + steps[].observation.status
        steps = [
            {
                "step_number": 1,
                "action": {"tool_name": "data_quality_check", "arguments": {}},
                "observation": {"status": "success"},
            },
            {
                "step_number": 2,
                "action": {"tool_name": "market_pulse", "arguments": {}},
                "observation": {"status": "error"},
            },
        ]
        usage = _extract_tool_usage(json.dumps(steps))
        self.assertEqual(len(usage), 2)
        self.assertEqual(usage[0], {"tool_name": "data_quality_check", "status": "success"})
        self.assertEqual(usage[1], {"tool_name": "market_pulse", "status": "error"})

    def test_invalid_json_returns_empty(self):
        self.assertEqual(_extract_tool_usage("not json"), [])
        self.assertEqual(_extract_tool_usage(None), [])


class RegistryCompletenessTests(unittest.TestCase):
    def test_known_tools_match_registry(self):
        # _KNOWN_TOOLS 必须与实际注册表一致（防止工具增删后经验库漏统计）
        from agent.tools import build_tool_registry

        registered = {d.name for d in build_tool_registry().list_definitions()}
        known = set(_KNOWN_TOOLS)
        self.assertEqual(known, registered)


class SummarySmokeTests(unittest.TestCase):
    def test_summary_returns_structure(self):
        # 真实库冒烟：表存在与否都应返回完整结构（best-effort）
        summary = build_experience_summary(days=30)
        for key in ("total_runs", "status_breakdown", "intent_breakdown",
                    "tool_usage", "unused_tools", "slow_runs", "failed_queries"):
            self.assertIn(key, summary)
        self.assertGreaterEqual(summary["total_runs"], 0)


if __name__ == "__main__":
    unittest.main()
