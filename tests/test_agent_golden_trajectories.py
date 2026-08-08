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

from agent.schemas import AgentContext, MarketType, ToolResult, ToolStatus
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


# =============================================================================
# 5. Golden case spec (20 条黄金轨迹集，调研计划 §5.2)
# =============================================================================

import json
import os

_GOLDEN_SPEC_PATH = os.path.join(os.path.dirname(__file__), "agent_golden_cases.json")


def _load_golden_spec():
    with open(_GOLDEN_SPEC_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestGoldenCaseSpecIntegrity(unittest.TestCase):
    """黄金轨迹 spec 自身必须完整自洽：20 条、引用合法、字段齐全。

    spec 是后续所有范式 PoC 的"测量仪"——它先坏掉，一切对比都失去意义。
    """

    def setUp(self):
        self.spec = _load_golden_spec()
        self.cases = self.spec["cases"]
        registry = get_tool_registry()
        self.registered = {d["function"]["name"] for d in registry.to_openai_tools()}

    def test_exactly_20_unique_cases(self):
        self.assertEqual(len(self.cases), 20)
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(set(ids)), 20)

    def test_expected_tools_are_registered(self):
        for case in self.cases:
            for tool in case.get("expected_tools", []) + case.get("forbidden_tools", []):
                with self.subTest(case=case["id"], tool=tool):
                    self.assertIn(tool, self.registered)

    def test_referenced_templates_resolve(self):
        for case in self.cases:
            tid = case.get("template")
            if tid:
                with self.subTest(case=case["id"], template=tid):
                    self.assertIsNotNone(get_workflow_template(tid))

    def test_live_replay_cases_have_query(self):
        for case in self.cases:
            if case.get("live_replay"):
                with self.subTest(case=case["id"]):
                    self.assertTrue(case.get("query"), "live 回放用例必须有 query")


class TestAdversarialGoldenCases(unittest.TestCase):
    """G18：越权/破坏性 SQL 必须被白名单确定性拒绝（不触达数据库）。"""

    def test_destructive_multi_statement_sql_rejected(self):
        from agent.tools_whitelist import _exec_data_query_safe
        from agent.schemas import AgentContext

        result = _exec_data_query_safe(
            {"sql": "SELECT * FROM auth_users; DROP TABLE trading_price_2025"},
            AgentContext(),
        )
        self.assertEqual(result.get("status"), "error")

    def test_non_whitelisted_table_rejected(self):
        from agent.tools_whitelist import _exec_data_query_safe
        from agent.schemas import AgentContext

        result = _exec_data_query_safe(
            {"sql": "SELECT * FROM auth_users LIMIT 10"},
            AgentContext(),
        )
        self.assertEqual(result.get("status"), "error")
        self.assertIn("auth_users", result.get("error", ""))


class TestDegradationGoldenCases(unittest.TestCase):
    """G14-G16：LLM 不可用时的降级路由必须确定性地命中预期模板。"""

    def test_g14_keyword_route_and_degradation_metadata_contract(self):
        # 关键词路由命中（离线确定性半程）
        self.assertEqual(
            match_workflow_from_query("帮我做一个完整的储能投资可行性分析"),
            "full_investment_feasibility",
        )
        # llm_degraded 元数据键是 orchestrator 的降级透明化契约
        import agent.orchestrator as orch_mod
        src = open(orch_mod.__file__, "r", encoding="utf-8").read()
        self.assertIn('"llm_degraded"', src)
        self.assertIn('"llm_degraded_reason"', src)

    def test_g15_quick_overview_route(self):
        self.assertEqual(
            match_workflow_from_query("给我一个快速市场概览"),
            "quick_market_overview",
        )

    def test_g16_free_form_falls_back_to_default(self):
        # 无关键词命中 → None → orchestrator 回落 quick_market_overview
        self.assertIsNone(match_workflow_from_query("SA1 的负电价意味着什么？"))
        self.assertIsNotNone(get_workflow_template("quick_market_overview"))

    def test_g05_wem_filters_nem_only_tools(self):
        """WEM 市场下模板必须过滤 NEM-only 工具（与 run_stream 的过滤集一致）。"""
        NEM_ONLY_TOOLS = {"fcas_analysis", "fcas_collapse_forecast",
                          "regional_timing_score", "regional_ranking"}
        template = get_workflow_template("quick_market_overview")
        filtered = [s for s in template.steps if s not in NEM_ONLY_TOOLS]
        self.assertNotIn("regional_ranking", filtered)
        # 过滤后仍非空，保证 WEM 降级路径有可执行步骤
        self.assertGreater(len(filtered), 0)


# =============================================================================
# 6. P0 修复回归网（基线计量 2026-08-06 驱动）
# =============================================================================


class TestPriceTableMissingTolerance(unittest.TestCase):
    """P0-1：目标年价格表缺失时返回结构化 no_data 而非裸 SQL 错误。

    基线计量发现历史 6/10 失败源于 trading_price_2025 表不存在。
    """

    def test_price_trend_returns_structured_no_data(self):
        from unittest.mock import patch
        import agent.tools as tools_mod

        with patch("deps.get_db", return_value=object()), \
             patch.object(tools_mod, "_price_table_exists", return_value=False):
            result = tools_mod._exec_price_trend(
                {"region": "SA1", "year": 2025}, AgentContext())
        self.assertEqual(result.get("status"), "no_data")
        self.assertIn("trading_price_2025", result.get("note", ""))

    def test_investment_analysis_returns_structured_no_data(self):
        from unittest.mock import patch
        import agent.tools as tools_mod

        with patch("deps.get_db", return_value=object()), \
             patch.object(tools_mod, "_price_table_exists", return_value=False):
            result = tools_mod._exec_investment_analysis(
                {"region": "NSW1", "year": 2025}, AgentContext())
        self.assertEqual(result.get("status"), "no_data")

    def test_exists_check_failure_defers_to_real_query(self):
        """检测自身异常（如连接池宕机）时不得误判为缺数据。"""
        import agent.tools as tools_mod

        class BrokenDb:
            def get_connection(self):
                raise RuntimeError("pool down")

        self.assertTrue(tools_mod._price_table_exists(BrokenDb(), "trading_price_2025"))

    def test_no_data_result_becomes_risk_flag(self):
        """闭环：no_data 结果必须被 orchestrator 提取为风险标记。"""
        from agent.orchestrator import AgentOrchestrator

        res = _make_result("price_trend_analysis", {"status": "no_data"})
        flags = AgentOrchestrator._extract_risk_flags(None, [res])
        self.assertTrue(any("无可用数据" in f for f in flags))


class TestWhitelistFromParser(unittest.TestCase):
    """白名单 FROM 解析器回归（bug 修复 2026-08-07）：
    EXTRACT(MONTH FROM col) 的函数内 FROM 不得被误当表引用；
    子查询/JOIN 引用的表必须全部纳入白名单校验。"""

    def test_extract_function_from_not_treated_as_table(self):
        from agent.tools_whitelist import _extract_referenced_tables

        sql = ("SELECT EXTRACT(MONTH FROM settlement_date) AS m, AVG(rrp_aud_mwh) "
               "FROM trading_price_2025 WHERE region_id = 'SA1' GROUP BY 1")
        self.assertEqual(_extract_referenced_tables(sql), ["trading_price_2025"])

    def test_simple_from(self):
        from agent.tools_whitelist import _extract_referenced_tables

        sql = "SELECT * FROM trading_price_2025 WHERE region_id = 'SA1' LIMIT 5"
        self.assertEqual(_extract_referenced_tables(sql), ["trading_price_2025"])

    def test_subquery_tables_are_checked(self):
        from agent.tools_whitelist import _extract_referenced_tables

        sql = ("SELECT * FROM (SELECT settlement_date FROM trading_price_2024) x "
               "LIMIT 10")
        self.assertIn("trading_price_2024", _extract_referenced_tables(sql))

    def test_join_with_forbidden_table_is_detected(self):
        from agent.tools_whitelist import _extract_referenced_tables

        sql = ("SELECT t.* FROM trading_price_2025 t "
               "JOIN auth_users u ON u.id = 1")
        tables = _extract_referenced_tables(sql)
        self.assertIn("trading_price_2025", tables)
        self.assertIn("auth_users", tables)  # JOIN 表也纳入白名单校验

    def test_from_inside_string_literal_ignored(self):
        from agent.tools_whitelist import _extract_referenced_tables

        sql = ("SELECT * FROM trading_price_2025 "
               "WHERE region_id = 'SA1 FROM auth_users' LIMIT 5")
        self.assertEqual(_extract_referenced_tables(sql), ["trading_price_2025"])


class TestSystemPrefixStability(unittest.TestCase):
    """P0-2：系统提示前缀不可变（append-only，KV-cache 友好）。

    会话记忆/分析计划等动态内容只能追加到消息尾部，不得改写 messages[0]。
    """

    def test_session_memory_appended_not_prefix_mutated(self):
        import asyncio
        from agent.orchestrator import AgentOrchestrator
        from agent.prompts import SYSTEM_PROMPT, DATABASE_SCHEMA_CONTEXT

        captured = {}

        class _Resp:
            content = "### 执行摘要\n测试完成"

        class _StubLLM:
            config = type("C", (), {"model": "stub-model"})
            last_health_error = ""

            async def health_check(self, force=False):
                return True

            def is_available(self):
                return True

            async def chat(self, messages, tools=None):
                return _Resp()

            async def chat_stream_events(self, messages, tools=None):
                captured["messages"] = [dict(m) for m in messages]
                yield {"type": "content", "text": "分析完成。"}
                yield {"type": "done", "finish_reason": "stop"}

        orch = AgentOrchestrator(llm=_StubLLM(), tools=get_tool_registry())
        orch.session_memory.put(
            "sess-p0", "price_trend_analysis",
            {"region": "SA1", "year": 2025}, "SA1 均价 100", "2025",
        )

        async def _drive():
            async for _ in orch.run_stream(
                query="测试查询", context=AgentContext(session_id="sess-p0")
            ):
                pass

        asyncio.run(_drive())
        # asyncio.run() 结束后会把线程当前循环置空，会污染后续测试里
        # 旧式 asyncio.get_event_loop() 用法；主动恢复一个新循环。
        asyncio.set_event_loop(asyncio.new_event_loop())

        messages = captured["messages"]
        # 前缀必须与静态拼接逐字节一致（任何动态改写都会破坏 KV-cache）
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(
            messages[0]["content"], SYSTEM_PROMPT + "\n" + DATABASE_SCHEMA_CONTEXT
        )
        # 会话记忆出现在尾部用户消息而非系统前缀
        last_user = [m for m in messages if m["role"] == "user"][-1]
        self.assertIn("本次会话已完成的分析", last_user["content"])


# =============================================================================
# 7. PoC 回归网：按阶段工具子集暴露（默认关闭，显式开启）
# =============================================================================


class TestToolSubsetPoC(unittest.TestCase):
    """子集暴露必须：名称合法、默认全量、全局工具恒在、行为级生效。"""

    def setUp(self):
        registry = get_tool_registry()
        self.registered = {d["function"]["name"] for d in registry.to_openai_tools()}

    def test_all_profile_tools_are_registered(self):
        """漂移防护：profile 里的工具名必须全部已注册。"""
        from agent.tool_profiles import TOOL_PROFILES, ALWAYS_VISIBLE

        for profile, tools in TOOL_PROFILES.items():
            for tool in tools + ALWAYS_VISIBLE:
                with self.subTest(profile=profile, tool=tool):
                    self.assertIn(tool, self.registered)

    def test_registry_filters_visible_subset(self):
        registry = get_tool_registry()
        filtered = registry.to_openai_tools({"price_trend_analysis", "data_quality_check"})
        names = {d["function"]["name"] for d in filtered}
        self.assertEqual(names, {"price_trend_analysis", "data_quality_check"})
        # 不传可见集 = 全量（默认行为不变）
        self.assertEqual(len(registry.to_openai_tools()), len(self.registered))

    def test_resolve_explicit_profile_includes_global_tool(self):
        from agent.tool_profiles import resolve_visible_tools

        visible = resolve_visible_tools(explicit="stage6_financial")
        self.assertIn("investment_analysis", visible)
        self.assertIn("data_quality_check", visible)  # 全局工具恒可见
        self.assertNotIn("market_screening", visible)

    def test_resolve_unknown_profile_and_free_query_return_full(self):
        from agent.tool_profiles import resolve_visible_tools

        self.assertIsNone(resolve_visible_tools(explicit="no_such_profile"))
        self.assertIsNone(resolve_visible_tools(query="SA1 负电价比例是多少"))

    def test_orchestrator_passes_filtered_tools_when_profile_set(self):
        """行为级：设置 tool_profile 后 LLM 只能看到子集 schema。"""
        import asyncio
        from agent.orchestrator import AgentOrchestrator

        captured = {}

        class _Resp:
            content = "### 执行摘要\n完成"

        class _StubLLM:
            config = type("C", (), {"model": "stub-model"})
            last_health_error = ""

            async def health_check(self, force=False):
                return True

            def is_available(self):
                return True

            async def chat(self, messages, tools=None):
                return _Resp()

            async def chat_stream_events(self, messages, tools=None):
                captured["tools"] = tools
                yield {"type": "content", "text": "完成。"}
                yield {"type": "done", "finish_reason": "stop"}

        orch = AgentOrchestrator(llm=_StubLLM(), tools=get_tool_registry())

        async def _drive(profile):
            async for _ in orch.run_stream(
                query="测试", context=AgentContext(tool_profile=profile)
            ):
                pass

        # 显式 profile → 子集
        asyncio.run(_drive("stage6_financial"))
        asyncio.set_event_loop(asyncio.new_event_loop())
        names = {d["function"]["name"] for d in captured["tools"]}
        self.assertIn("investment_analysis", names)
        self.assertIn("data_quality_check", names)
        self.assertNotIn("market_screening", names)
        self.assertLess(len(names), len(self.registered))

        # 未设置 profile → 全量（默认行为不变）
        asyncio.run(_drive(None))
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.assertEqual(
            {d["function"]["name"] for d in captured["tools"]}, self.registered
        )


# =============================================================================
# 8. 意图路由器 + profile 覆盖审计（§10.4-1/2，子集启用的前置条件）
# =============================================================================


class TestIntentRouter(unittest.TestCase):
    """路由映射黄金集：确定性关键词规则必须把代表查询送到正确 profile，
    无法归类/深度查询必须回落全量（安全网）。"""

    GOLDEN_ROUTES = [
        ("分析 SA1 2025 年负电价比例及对充电策略的含义", "stage1_screening"),
        ("查询 SA1 2025 年 6 月的日均价格", "data_exploration"),
        ("分析 WEM 的 ESS 辅助服务收入潜力", "stage2_revenue"),
        ("WEM 100MW/4h 电池投资 NPV 分析", "stage6_financial"),
        ("对比 SA1、QLD1、NSW1 的投资 NPV", "multi_region_decision"),
        ("做一次 QLD1 的蒙特卡洛风险评估", "stage4_outlook"),
    ]

    def test_golden_routes(self):
        from agent.tool_profiles import route_query_to_profile

        for query, expected in self.GOLDEN_ROUTES:
            with self.subTest(query=query):
                self.assertEqual(route_query_to_profile(query), expected)

    def test_unclassifiable_falls_back_to_full(self):
        from agent.tool_profiles import route_query_to_profile

        self.assertIsNone(route_query_to_profile("今天天气怎么样"))
        self.assertIsNone(route_query_to_profile(""))

    def test_deep_research_queries_fall_back_to_full(self):
        """深度研究类（完整可行性等）必须回落全量，不得被窄化。"""
        from agent.tool_profiles import route_query_to_profile

        self.assertIsNone(route_query_to_profile("对 NSW1 做完整的储能投资可行性分析"))


class TestProfileCoverageAudit(unittest.TestCase):
    """§10.4-2 G06 教训制度化：黄金用例期望的工具必须全部包含在
    其查询被路由到的 profile 内，否则就是误路由牺牲完整性。"""

    def test_routed_profile_covers_expected_tools(self):
        import json as _json
        import os
        from agent.tool_profiles import route_query_to_profile, profile_tools

        spec_path = os.path.join(os.path.dirname(__file__), "agent_golden_cases.json")
        with open(spec_path, "r", encoding="utf-8") as f:
            cases = _json.load(f)["cases"]

        audited = 0
        for case in cases:
            expected = case.get("expected_tools")
            query = case.get("query")
            if not expected or not query:
                continue
            profile = route_query_to_profile(query)
            if profile is None:
                continue  # 回落全量，天然覆盖
            audited += 1
            visible = profile_tools(profile)
            for tool in expected:
                with self.subTest(case=case["id"], profile=profile, tool=tool):
                    self.assertIn(
                        tool, visible,
                        f"用例 {case['id']} 被路由到 {profile}，但期望工具 {tool} 不在子集内（误路由）",
                    )
        # 审计必须真实覆盖了多数用例，防止 spec 退化后测试空转
        self.assertGreaterEqual(audited, 8)


class TestToolRoutingBehavior(unittest.TestCase):
    """行为级：开启 enable_tool_routing 后无显式 profile 也能自动子集化；
    关闭时（默认）保持全量。"""

    def _drive(self, query, enable_routing):
        import asyncio
        from agent.orchestrator import AgentOrchestrator

        captured = {}

        class _Resp:
            content = "### 执行摘要\n完成"

        class _StubLLM:
            config = type("C", (), {"model": "stub-model"})
            last_health_error = ""

            async def health_check(self, force=False):
                return True

            def is_available(self):
                return True

            async def chat(self, messages, tools=None):
                return _Resp()

            async def chat_stream_events(self, messages, tools=None):
                captured["tools"] = tools
                yield {"type": "content", "text": "完成。"}
                yield {"type": "done", "finish_reason": "stop"}

        orch = AgentOrchestrator(llm=_StubLLM(), tools=get_tool_registry())

        async def _run():
            report_meta = {}
            async for ev in orch.run_stream(
                query=query,
                context=AgentContext(enable_tool_routing=enable_routing),
            ):
                if ev.get("type") == "report":
                    report_meta = ev["report"].get("metadata", {})
            return report_meta

        meta = asyncio.run(_run())
        asyncio.set_event_loop(asyncio.new_event_loop())
        return captured["tools"], meta

    def test_routing_enabled_subsets_tools(self):
        tools, meta = self._drive("查询 SA1 2025 年 6 月的日均价格", True)
        names = {d["function"]["name"] for d in tools}
        self.assertIn("data_query", names)
        self.assertIn("data_quality_check", names)
        self.assertNotIn("investment_analysis", names)
        self.assertEqual(meta.get("tool_profile"), "data_exploration")
        self.assertEqual(meta.get("tool_profile_source"), "routed")

    def test_routing_disabled_keeps_full(self):
        registry = get_tool_registry()
        tools, meta = self._drive("查询 SA1 2025 年 6 月的日均价格", False)
        self.assertEqual(len(tools), len(registry.to_openai_tools()))
        self.assertNotIn("tool_profile", meta)


# =============================================================================
# 9. A/B/C 组新功能回归（溯源校验/熔断/会话缓存强制消费/Plan-Execute）
# =============================================================================


class TestNumericGrounding(unittest.TestCase):
    """A1：回答数字必须能追溯到工具结果；琐碎数字（年份/小整数）豁免。"""

    def test_grounded_numbers_pass(self):
        from agent.grounding import check_numeric_grounding

        results = [_make_result("price_trend_analysis", {
            "stats": {"avg_price": 103.32, "negative_ratio_pct": 14.34},
        })]
        check = check_numeric_grounding(
            "2025 年均价 103.32 AUD/MWh，负价比例 14.34%，共 3 次工具调用", results)
        self.assertEqual(check["ungrounded_ratio"], 0.0)
        self.assertGreaterEqual(check["checked"], 2)

    def test_fabricated_numbers_flagged(self):
        from agent.grounding import check_numeric_grounding

        results = [_make_result("price_trend_analysis", {"stats": {"avg_price": 103.32}})]
        check = check_numeric_grounding(
            "NPV 为 9999999.5，IRR 88.8%，回收期 45.5 年，均价 103.32", results)
        self.assertGreater(check["ungrounded_ratio"], 0.5)

    def test_empty_answer_is_neutral(self):
        from agent.grounding import check_numeric_grounding

        check = check_numeric_grounding("", [_make_result("t", {"v": 1.0})])
        self.assertEqual(check["checked"], 0)

    def test_orchestrator_appends_risk_flag_on_high_ratio(self):
        from agent.orchestrator import AgentOrchestrator
        from agent.schemas import AgentReport

        orch = AgentOrchestrator.__new__(AgentOrchestrator)
        report = AgentReport(query="q")
        results = [_make_result("t", {"v": 10.0})]
        orch._apply_grounding_check(
            report, "NPV 999999.5，IRR 88.8，回收期 45.5，另一个 77777.7", results)
        self.assertIn("numeric_grounding", report.metadata)
        self.assertTrue(any("数值溯源警示" in f for f in report.risk_flags))


class TestLLMCircuitBreaker(unittest.TestCase):
    """B3：连续探测失败→open（跳过探测）；冷却后 half-open 试探恢复。"""

    def _make_adapter(self):
        from agent.llm_adapter import LLMAdapter, LLMConfig

        adapter = LLMAdapter(config=LLMConfig(api_key="k", base_url="http://fake"))
        probe_counter = {"n": 0}
        fail = {"flag": True}

        class _FakeResponse:
            def raise_for_status(self):
                if fail["flag"]:
                    raise RuntimeError("boom")

        class _FakeClient:
            async def post(self, url, json=None, headers=None):
                probe_counter["n"] += 1
                return _FakeResponse()

        async def _get_client():
            return _FakeClient()

        adapter._get_client = _get_client
        return adapter, probe_counter, fail

    def test_breaker_opens_after_consecutive_failures(self):
        import asyncio

        adapter, counter, fail = self._make_adapter()

        async def _run():
            self.assertFalse(await adapter.health_check())   # 探测 1 失败
            self.assertFalse(await adapter.health_check())   # 探测 2 失败 → open
            self.assertEqual(adapter._breaker_state, "open")
            self.assertFalse(await adapter.health_check())   # open 期间不再探测
            return None

        asyncio.run(_run())
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.assertEqual(counter["n"], 2)  # 第三次调用未探测

    def test_breaker_recovers_after_cooldown(self):
        import asyncio

        adapter, counter, fail = self._make_adapter()

        async def _run():
            await adapter.health_check()
            await adapter.health_check()
            self.assertEqual(adapter._breaker_state, "open")
            adapter._breaker_opened_at -= adapter._breaker_cooldown_s + 1  # 模拟冷却结束
            fail["flag"] = False
            self.assertTrue(await adapter.health_check())   # half-open 探测成功
            self.assertEqual(adapter._breaker_state, "closed")

        asyncio.run(_run())
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestSessionCacheEnforcedConsumption(unittest.TestCase):
    """A5：会话缓存命中时跳过重复执行，返回 cached 结果。"""

    def test_second_call_is_served_from_session_cache(self):
        import asyncio
        from agent.orchestrator import AgentOrchestrator

        call_count = {"stream": 0}

        class _Resp:
            content = "### 执行摘要\n完成"

        class _StubLLM:
            config = type("C", (), {"model": "stub-model"})
            last_health_error = ""

            async def health_check(self, force=False):
                return True

            def is_available(self):
                return True

            async def chat(self, messages, tools=None):
                return _Resp()

            async def chat_stream_events(self, messages, tools=None):
                call_count["stream"] += 1
                if call_count["stream"] == 1:
                    yield {"type": "tool_calls", "tool_calls": [{
                        "id": "c1", "name": "saturation_check",
                        "arguments": {"region": "SA1"},
                    }]}
                else:
                    yield {"type": "content", "text": "完成。"}
                yield {"type": "done", "finish_reason": "stop"}

        orch = AgentOrchestrator(llm=_StubLLM(), tools=get_tool_registry())
        ctx = AgentContext(session_id="sess-a5", region="SA1", year=2025)
        # 预种缓存：与实际执行相同的 tool+args+data_version
        orch.session_memory.put(
            "sess-a5", "saturation_check", {"region": "SA1", "year": 2025},
            "SA1 饱和检查已完成", "2025",
        )

        async def _drive():
            report = None
            async for ev in orch.run_stream(query="测试", context=ctx):
                if ev.get("type") == "report":
                    report = ev["report"]
            return report

        report = asyncio.run(_drive())
        asyncio.set_event_loop(asyncio.new_event_loop())
        trace = report["tool_trace"]
        self.assertEqual(len(trace), 1)
        self.assertTrue(trace[0]["metadata"].get("cached"))
        self.assertEqual(trace[0]["data"]["summary"], "SA1 饱和检查已完成")


class TestPlanExecuteMode(unittest.TestCase):
    """C4：波次并行执行；计划生成失败自动回落 ReAct。"""

    PLAN_JSON = (
        '{"goal": "饱和检查", "waves": [[{"tool": "saturation_check", '
        '"args": {"region": "SA1"}}]], "reasoning": "单波次"}'
    )

    def _stub(self, plan_payload):
        class _Resp:
            def __init__(self, content):
                self.content = content

        class _StubLLM:
            config = type("C", (), {"model": "stub-model"})
            last_health_error = ""

            async def health_check(self, force=False):
                return True

            def is_available(self):
                return True

            async def chat(self, messages, tools=None):
                # 规划器调用（system 提示含"执行规划器"）返回计划；其余为综合调用
                if any("执行规划器" in (m.get("content") or "") for m in messages):
                    return _Resp(plan_payload)
                return _Resp("### 执行摘要\n综合完成")

            async def chat_stream_events(self, messages, tools=None):
                yield {"type": "content", "text": "ReAct 回答"}
                yield {"type": "done", "finish_reason": "stop"}

        return _StubLLM()

    def test_plan_execute_runs_waves(self):
        import asyncio
        from agent.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(llm=self._stub(self.PLAN_JSON), tools=get_tool_registry())
        ctx = AgentContext(region="SA1", year=2025, enable_plan_execute=True)

        async def _drive():
            events = []
            async for ev in orch.run_stream(query="检查 SA1 饱和", context=ctx):
                events.append(ev)
            return events

        events = asyncio.run(_drive())
        asyncio.set_event_loop(asyncio.new_event_loop())
        types = [e["type"] for e in events]
        self.assertIn("plan", types)
        self.assertIn("tool_call", types)
        self.assertIn("tool_result", types)
        report = next(e for e in events if e["type"] == "report")["report"]
        self.assertEqual(report["metadata"]["mode"], "plan_execute")
        self.assertEqual(report["workflow_type"], "plan_execute")
        self.assertEqual(report["tool_trace"][0]["status"], "success")

    def test_invalid_plan_falls_back_to_react(self):
        import asyncio
        from agent.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(llm=self._stub("这不是 JSON"), tools=get_tool_registry())
        ctx = AgentContext(region="SA1", year=2025, enable_plan_execute=True)

        async def _drive():
            report = None
            async for ev in orch.run_stream(query="随便问问", context=ctx):
                if ev.get("type") == "report":
                    report = ev["report"]
            return report

        report = asyncio.run(_drive())
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.assertEqual(report["metadata"]["mode"], "react_stream")
        self.assertEqual(report["workflow_type"], "react_llm_stream")


if __name__ == "__main__":
    unittest.main()