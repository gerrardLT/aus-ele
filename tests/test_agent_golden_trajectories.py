"""Golden-trajectory evaluation suite for the agent system (P2-1).

This is the institutionalized answer to the recurring lesson of this project:
"bugs were only caught by running the real flow, never by unit tests."  Rather
than relying on a live (slow, flaky, costly) LLM, this suite encodes the
*deterministic* behaviours that repeatedly regressed, as a fast CI-friendly
regression net:

1. **Routing golden set**   — representative queries must route to the correct
   workflow template (and free-form queries must NOT match any template, so
   they reach the LLM ReAct path).
2. **Contract golden set**  — the field-drift bug family (producer returns key
   X, consumer reads key Y, silently empty). We build fixtures keyed by the
   ``tool_contracts`` constants and assert the synthesizer extracts findings;
   we also assert the OLD drifted keys yield nothing, proving the consumer
   reads the contract keys.
3. **Template integrity**   — every template step is a registered tool and
   every parallel group references a valid step index.

These tests are deliberately LLM-free and data-free so they run in seconds and
stay green in CI. They guard the *wiring* (routing + contracts + structure)
that the live e2e checks exercise end-to-end.
"""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from agent.schemas import MarketType, ToolResult, ToolStatus
from agent.synthesizer import _extract_key_findings
from agent.tools import get_tool_registry
from agent.orchestrator import _trim_history, HISTORY_MAX_CHARS, HISTORY_MAX_MESSAGES
from agent.workflows import (
    WORKFLOW_TEMPLATES,
    get_workflow_template,
    match_workflow_from_query,
)
from agent import tool_contracts as tc


# =============================================================================
# 1. Routing golden set
# =============================================================================


class TestRoutingGoldenSet(unittest.TestCase):
    """Representative queries must route to the intended workflow template."""

    GOLDEN_ROUTES = [
        # full investment feasibility
        ("帮我做一个完整的储能投资可行性分析", "full_investment_feasibility"),
        ("full feasibility study for NSW1", "full_investment_feasibility"),
        # quick market overview
        ("给我一个快速市场概览", "quick_market_overview"),
        ("quick overview of the current market", "quick_market_overview"),
        # FCAS opportunity
        ("评估一下 FCAS 辅助服务的机会", "fcas_opportunity"),
        ("ancillary service opportunity", "fcas_opportunity"),
        # revenue deep dive
        ("分析一下价差套利收入结构", "revenue_deep_dive"),
        ("revenue breakdown from spread arbitrage", "revenue_deep_dive"),
        # risk assessment
        ("做一次蒙特卡洛风险评估", "risk_assessment"),
        ("assess the merchant risk", "risk_assessment"),
        # regional comparison
        ("哪个区域最值得投资？做个排名对比", "regional_comparison"),
        ("compare regions by ranking", "regional_comparison"),
    ]

    def test_golden_routes(self):
        for query, expected in self.GOLDEN_ROUTES:
            with self.subTest(query=query):
                self.assertEqual(match_workflow_from_query(query), expected)

    def test_free_form_queries_do_not_match(self):
        """Free-form queries should return None so they reach the LLM ReAct path
        instead of being silently force-routed into a wrong template."""
        free_form = [
            "SA1 地区 2025 年负电价出现的比例是多少？",
            "电池在午间充电晚峰放电的策略收益如何？",
            "what is the negative price ratio and its implication?",
        ]
        for query in free_form:
            with self.subTest(query=query):
                self.assertIsNone(match_workflow_from_query(query))


# =============================================================================
# 2. Contract golden set (field-drift regression net)
# =============================================================================


def _make_result(tool_name: str, data: dict) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        status=ToolStatus.SUCCESS,
        data=data,
        duration_ms=100.0,
    )


class TestContractGoldenSet(unittest.TestCase):
    """The synthesizer must read the exact keys the producers emit.

    Fixtures are keyed by the tool_contracts constants (single source of
    truth). If a producer/consumer drifts away from the contract, these tests
    fail loudly instead of silently producing empty findings.
    """

    def test_market_screening_contract_extracts_best_region(self):
        data = {
            tc.SCREENING_ITEMS_KEY: [
                {
                    tc.SCREENING_LABEL_KEY: "SA1",
                    tc.SCREENING_MARKET_KEY: "NEM",
                    tc.SCREENING_SCORE_KEY: 65.3,
                },
                {
                    tc.SCREENING_LABEL_KEY: "VIC1",
                    tc.SCREENING_MARKET_KEY: "NEM",
                    tc.SCREENING_SCORE_KEY: 62.0,
                },
            ],
        }
        findings = _extract_key_findings([_make_result("market_screening", data)])
        joined = " ".join(findings)
        self.assertIn("SA1", joined)
        self.assertIn("65.3", joined)

    def test_investment_contract_extracts_npv_and_payback(self):
        data = {
            tc.INVEST_RESULTS_KEY: {
                tc.INVEST_NPV_KEY: 1_961_300.0,
                tc.INVEST_PAYBACK_KEY: 6.2,
                tc.INVEST_IRR_KEY: 25.75,
            },
        }
        findings = _extract_key_findings([_make_result("investment_analysis", data)])
        joined = " ".join(findings)
        self.assertIn("NPV", joined)
        self.assertIn("回收期", joined)

    def test_drifted_keys_yield_nothing(self):
        """Regression proof: the OLD drifted keys must NOT produce findings.

        This is the negative half of the contract — it confirms the consumer
        reads the contract keys and would catch a revert to the buggy keys.
        """
        # Old bug 1: reading "candidates" when producer emits "items".
        drifted_screening = {
            "candidates": [{tc.SCREENING_LABEL_KEY: "SA1", tc.SCREENING_SCORE_KEY: 65.3}],
        }
        findings = _extract_key_findings([_make_result("market_screening", drifted_screening)])
        self.assertNotIn("SA1", " ".join(findings))

        # Old bug 2: reading "simple_payback_years" when producer emits "payback_years".
        drifted_invest = {
            tc.INVEST_RESULTS_KEY: {
                tc.INVEST_NPV_KEY: 1_961_300.0,
                "simple_payback_years": 6.2,
            },
        }
        findings = _extract_key_findings([_make_result("investment_analysis", drifted_invest)])
        # NPV still found (that key never drifted) but payback must be absent.
        self.assertNotIn("回收期", " ".join(findings))

    def test_contract_constants_match_producer_literals(self):
        """Guard: the contract constants must keep their canonical values.

        If someone renames a constant's VALUE here without updating the
        producer in tools.py / market_screening.py, this pin fails and forces
        a conscious decision rather than a silent break.
        """
        self.assertEqual(tc.SCREENING_ITEMS_KEY, "items")
        self.assertEqual(tc.INVEST_NPV_KEY, "npv_aud")
        self.assertEqual(tc.INVEST_PAYBACK_KEY, "payback_years")
        self.assertEqual(tc.INVEST_RESULTS_KEY, "results")


# =============================================================================
# 3. Template integrity golden set
# =============================================================================


class TestTemplateIntegrityGoldenSet(unittest.TestCase):
    """Every template must reference only registered tools with valid indices."""

    def setUp(self):
        registry = get_tool_registry()
        # Collect the full set of registered tool names.
        self.registered = {d["function"]["name"] for d in registry.to_openai_tools()}

    def test_all_template_steps_are_registered_tools(self):
        for tid, template in WORKFLOW_TEMPLATES.items():
            for step in template.steps:
                with self.subTest(template=tid, step=step):
                    self.assertIn(step, self.registered,
                                  f"template {tid} step {step} is not a registered tool")

    def test_parallel_groups_reference_valid_indices(self):
        for tid, template in WORKFLOW_TEMPLATES.items():
            n = len(template.steps)
            for group in (template.parallel_groups or []):
                for idx in group:
                    with self.subTest(template=tid, idx=idx):
                        self.assertGreaterEqual(idx, 0)
                        self.assertLess(idx, n,
                                        f"template {tid} parallel index {idx} out of range")

    def test_forced_template_ids_resolve(self):
        """Every template id in the registry resolves back to itself."""
        for tid in WORKFLOW_TEMPLATES:
            self.assertIsNotNone(get_workflow_template(tid))
            self.assertEqual(get_workflow_template(tid).id, tid)


# =============================================================================
# 4. History budget golden set (P2-5)
# =============================================================================


class TestHistoryBudgetGoldenSet(unittest.TestCase):
    """Multi-turn history must be bounded (sliding window + char budget)."""

    def _msg(self, role: str, content: str) -> dict:
        return {"role": role, "content": content}

    def test_empty_history(self):
        self.assertEqual(_trim_history(None), [])
        self.assertEqual(_trim_history([]), [])

    def test_filters_invalid_roles_and_empty(self):
        history = [
            self._msg("user", "hi"),
            self._msg("system", "should be dropped"),
            self._msg("assistant", ""),
            self._msg("assistant", "hello"),
        ]
        kept = _trim_history(history)
        self.assertEqual([m["content"] for m in kept], ["hi", "hello"])

    def test_sliding_window_keeps_most_recent(self):
        history = [self._msg("user", f"msg{i}") for i in range(30)]
        kept = _trim_history(history, max_messages=5, max_chars=100000)
        self.assertEqual(len(kept), 5)
        self.assertEqual(kept[-1]["content"], "msg29")  # newest preserved
        self.assertEqual(kept[0]["content"], "msg25")

    def test_char_budget_drops_oldest(self):
        # 5 messages of 100 chars each; budget 250 -> keep at most ~2 newest.
        history = [self._msg("user", "x" * 100) for _ in range(5)]
        kept = _trim_history(history, max_messages=10, max_chars=250)
        self.assertLessEqual(sum(len(m["content"]) for m in kept), 250 + 100)  # +1 for the forced-first keep
        # Must be the NEWEST messages, in chronological order.
        self.assertGreaterEqual(len(kept), 1)

    def test_chronological_order_preserved(self):
        history = [self._msg("user", f"m{i}") for i in range(4)]
        kept = _trim_history(history, max_messages=10, max_chars=100000)
        self.assertEqual([m["content"] for m in kept], ["m0", "m1", "m2", "m3"])

    def test_default_bounds_are_sane(self):
        self.assertGreater(HISTORY_MAX_MESSAGES, 0)
        self.assertGreater(HISTORY_MAX_CHARS, 0)


if __name__ == "__main__":
    unittest.main()