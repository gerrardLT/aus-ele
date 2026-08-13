"""Tests for Generate→Verify→Repair loop & feasibility parallelization (2026-08-13)."""

import asyncio
import os
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from agent.grounding import (
    REPAIR_MIN_CHECKED,
    REPAIR_RATIO_THRESHOLD,
    build_repair_feedback,
    should_repair,
)
from agent.schemas import AgentContext, ToolResult, ToolStatus


# =============================================================================
# Pure functions
# =============================================================================


class ShouldRepairTests(unittest.TestCase):
    def test_triggers_above_threshold(self):
        check = {"checked": 5, "grounded": 1, "ungrounded_ratio": 0.8, "ungrounded_samples": [1, 2]}
        self.assertTrue(should_repair(check))

    def test_no_trigger_below_threshold(self):
        check = {"checked": 5, "grounded": 4, "ungrounded_ratio": 0.2, "ungrounded_samples": [1]}
        self.assertFalse(should_repair(check))

    def test_no_trigger_when_too_few_checked(self):
        check = {"checked": 2, "grounded": 0, "ungrounded_ratio": 1.0, "ungrounded_samples": [1, 2]}
        self.assertFalse(should_repair(check))

    def test_no_trigger_zero_checked(self):
        self.assertFalse(should_repair({"checked": 0, "ungrounded_ratio": 0.0}))

    def test_invalid_input(self):
        self.assertFalse(should_repair(None))
        self.assertFalse(should_repair("not a dict"))

    def test_thresholds_align_with_risk_flag(self):
        self.assertEqual(REPAIR_MIN_CHECKED, 4)
        self.assertEqual(REPAIR_RATIO_THRESHOLD, 0.5)


class RepairFeedbackTests(unittest.TestCase):
    def test_feedback_contains_samples_and_prohibition(self):
        fb = build_repair_feedback([123.4, 5678.0])
        self.assertIn("123.4", fb)
        self.assertIn("5678.0", fb)
        self.assertIn("严禁编造", fb)
        self.assertIn("溯源修复", fb)

    def test_feedback_caps_samples_at_ten(self):
        fb = build_repair_feedback(list(range(20)))
        self.assertNotIn("15", fb.split("。")[1])


# =============================================================================
# Synthesizer injection
# =============================================================================


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    """Returns scripted responses in order and captures prompts."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def is_available(self) -> bool:
        return True

    async def chat(self, messages, **kwargs):
        user_msg = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        self.prompts.append(user_msg)
        return _FakeResponse(self._responses.pop(0))


def _tool_results_with_price(price: float = 100.0):
    return [
        ToolResult(
            tool_name="price_trend_analysis",
            status=ToolStatus.SUCCESS,
            data={"stats": {"avg_price": price, "negative_ratio_pct": 5.0}},
        )
    ]


class SynthesizerInjectionTests(unittest.TestCase):
    def test_repair_feedback_appended_to_prompt(self):
        from agent.synthesizer import synthesize_report

        llm = _FakeLLM(["均价为 100 AUD/MWh。"])
        asyncio.run(synthesize_report(
            query="test", tool_results=_tool_results_with_price(),
            context=AgentContext(), llm=llm,
            repair_feedback="【数值溯源修复要求】测试指令",
        ))
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("【数值溯源修复要求】测试指令", llm.prompts[0])

    def test_no_feedback_by_default(self):
        from agent.synthesizer import synthesize_report

        llm = _FakeLLM(["均价为 100 AUD/MWh。"])
        asyncio.run(synthesize_report(
            query="test", tool_results=_tool_results_with_price(),
            context=AgentContext(), llm=llm,
        ))
        self.assertNotIn("溯源修复", llm.prompts[0])


# =============================================================================
# Orchestrator repair loop integration
# =============================================================================


_BAD_REPORT = "均价 100 AUD/MWh，但 NPV 为 555555 AUD，IRR 33.3%，年收入 4444，资本开支 7777。"
_GOOD_REPORT = "均价 100 AUD/MWh，负价比例 5%。"


class OrchestratorRepairLoopTests(unittest.TestCase):
    def _make_orchestrator(self, responses):
        from agent.orchestrator import AgentOrchestrator
        from agent.tools import get_tool_registry

        return AgentOrchestrator(_FakeLLM(responses), get_tool_registry())

    def test_repair_triggered_and_improves(self):
        orch = self._make_orchestrator([_BAD_REPORT, _GOOD_REPORT])
        summary, rec, conf, full, repair_info = asyncio.run(
            orch._synthesize("test", _tool_results_with_price(), AgentContext())
        )
        self.assertTrue(repair_info["attempted"])
        self.assertTrue(repair_info["used"])
        self.assertTrue(repair_info["improved"])
        self.assertEqual(repair_info["before_ratio"], 0.8)
        self.assertEqual(repair_info["after_ratio"], 0.0)
        self.assertIn("均价 100", full)

    def test_no_repair_when_grounded(self):
        orch = self._make_orchestrator([_GOOD_REPORT])
        _, _, _, full, repair_info = asyncio.run(
            orch._synthesize("test", _tool_results_with_price(), AgentContext())
        )
        self.assertFalse(repair_info["attempted"])
        self.assertIn("均价 100", full)

    def test_env_flag_disables_repair(self):
        orch = self._make_orchestrator([_BAD_REPORT])
        old = os.environ.get("AUS_ELE_AGENT_GROUNDING_REPAIR")
        os.environ["AUS_ELE_AGENT_GROUNDING_REPAIR"] = "0"
        try:
            _, _, _, _, repair_info = asyncio.run(
                orch._synthesize("test", _tool_results_with_price(), AgentContext())
            )
        finally:
            if old is None:
                os.environ.pop("AUS_ELE_AGENT_GROUNDING_REPAIR", None)
            else:
                os.environ["AUS_ELE_AGENT_GROUNDING_REPAIR"] = old
        self.assertFalse(repair_info["attempted"])

    def test_repair_never_degrades_keeps_better_version(self):
        # 修复版不可溯源占比更高（77.8% > 50%）→ 保留原版（小整数 ≤20 被豁免不计）
        worse = "NPV 555555，IRR 33.3，收入 4444，开支 7777，另有 888888、999999、111111、222222 存疑。"
        orch = self._make_orchestrator([_BAD_REPORT, worse])
        _, _, _, full, repair_info = asyncio.run(
            orch._synthesize("test", _tool_results_with_price(), AgentContext())
        )
        self.assertTrue(repair_info["attempted"])
        self.assertFalse(repair_info["used"])
        self.assertGreater(repair_info["after_ratio"], repair_info["before_ratio"])
        self.assertIn("555555", full)


# =============================================================================
# Feasibility template parallelization
# =============================================================================


class FeasibilityParallelizationTests(unittest.TestCase):
    def test_revenue_deep_dive_tools_in_steps(self):
        from agent.workflows import get_workflow_template

        tmpl = get_workflow_template("full_investment_feasibility")
        for tool in ("spike_profit_analysis", "bess_revenue_benchmark"):
            self.assertIn(tool, tmpl.steps)

    def test_parallel_groups_valid_and_cover_all_steps(self):
        from agent.workflows import get_workflow_template

        tmpl = get_workflow_template("full_investment_feasibility")
        covered = []
        for group in tmpl.parallel_groups:
            for idx in group:
                self.assertLess(idx, len(tmpl.steps))
                covered.append(idx)
        self.assertEqual(sorted(covered), list(range(len(tmpl.steps))))

    def test_deep_dive_group_is_parallel(self):
        from agent.workflows import get_workflow_template

        tmpl = get_workflow_template("full_investment_feasibility")
        deep_dive = None
        for group in tmpl.parallel_groups:
            names = {tmpl.steps[i] for i in group}
            if "peak_analysis" in names:
                deep_dive = names
                break
        self.assertIsNotNone(deep_dive)
        self.assertTrue({"spike_profit_analysis", "bess_revenue_benchmark"} <= deep_dive)

    def test_benchmark_tool_wem_guard(self):
        from agent.schemas import MarketType
        from agent.tools import get_tool_registry

        registry = get_tool_registry()
        result = registry.get_executor("bess_revenue_benchmark")(
            {"region": "WEM"}, AgentContext(market=MarketType.WEM)
        )
        self.assertEqual(result.get("status"), "not_covered")


if __name__ == "__main__":
    unittest.main()
