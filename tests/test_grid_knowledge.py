"""Unit tests for grid knowledge base & lookup service (规则知识库, 2026-08-12)."""

import json
import os
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.grid_knowledge import (
    _KNOWLEDGE_PATH,
    get_rule,
    get_timeline,
    search_rules,
)


class KnowledgeFileTests(unittest.TestCase):
    def test_knowledge_file_loads(self):
        self.assertTrue(os.path.exists(_KNOWLEDGE_PATH))
        with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["meta"]["schema_version"], 1)
        self.assertGreaterEqual(len(data["rules"]), 9)
        self.assertGreaterEqual(len(data["timeline"]), 8)

    def test_rules_carry_four_elements(self):
        with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for rule in data["rules"]:
            for field in ("source_url", "confidence", "review_date"):
                self.assertIn(field, rule, f"{rule['id']} 缺 {field}")
            self.assertIn("effective_date", rule, f"{rule['id']} 缺 effective_date")

    def test_ids_unique_and_markets_valid(self):
        with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        ids = [r["id"] for r in data["rules"]]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in data["rules"]:
            self.assertIn(rule["market"], ("NEM", "WEM"))


class SearchTests(unittest.TestCase):
    def test_search_fcas_hits_nem_card(self):
        result = search_rules(query="FCAS 服务")
        self.assertTrue(result["available"])
        ids = [m["id"] for m in result["matches"]]
        self.assertIn("nem_fcas_services", ids)

    def test_search_chinese_query(self):
        result = search_rules(query="容量机制")
        ids = [m["id"] for m in result["matches"]]
        self.assertIn("wem_rcm_brcp", ids)

    def test_market_filter(self):
        result = search_rules(market="WEM", limit=10)
        self.assertTrue(all(m["market"] == "WEM" for m in result["matches"]))
        self.assertGreaterEqual(len(result["matches"]), 3)

    def test_no_hit_returns_empty_matches(self):
        result = search_rules(query="zzz_no_such_keyword_zzz")
        self.assertEqual(result["matches"], [])

    def test_get_rule_and_timeline(self):
        rule = get_rule("nem_iess_rule")
        self.assertIsNotNone(rule)
        self.assertIn("IESS", rule["title"])
        timeline = get_timeline(10)
        self.assertGreaterEqual(len(timeline), 8)
        dates = [t["date"] for t in timeline]
        self.assertEqual(dates, sorted(dates))


class AgentToolTests(unittest.TestCase):
    def test_tool_registered_and_executes(self):
        from agent.schemas import AgentContext
        from agent.tools import build_tool_registry

        registry = build_tool_registry()
        self.assertIsNotNone(registry.get_definition("grid_knowledge_lookup"))

        result = registry.get_executor("grid_knowledge_lookup")(
            {"query": "什么是 FCAS"}, AgentContext()
        )
        self.assertTrue(result["available"])
        self.assertGreaterEqual(len(result["matches"]), 1)
        # 每个命中卡片都带引用要素
        for m in result["matches"]:
            self.assertIn("source_url", m)
            self.assertIn("confidence", m)

    def test_profiles_expose_tool(self):
        from agent.tool_profiles import TOOL_PROFILES

        for profile in ("stage1_screening", "stage2_revenue", "stage6_financial"):
            self.assertIn("grid_knowledge_lookup", TOOL_PROFILES[profile])


if __name__ == "__main__":
    unittest.main()
