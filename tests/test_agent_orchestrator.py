"""Unit tests for the AI Agent workflow orchestration system.

Covers:
- Schema validation (Pydantic models)
- Tool registry (registration, listing, execution)
- Workflow templates (definitions, keyword matching)
- Orchestrator (template mode, fallback routing)
- Synthesizer (rule-based report generation)
- API routes (endpoint integration via TestClient)
"""

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from agent.schemas import (
    AgentContext,
    AgentReport,
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    ConfidenceLevel,
    MarketType,
    StageResult,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolStatus,
    WorkflowStatus,
    WorkflowTemplate,
)
from agent.tools import ToolRegistry, get_tool_registry
from agent.workflows import (
    WORKFLOW_TEMPLATES,
    get_workflow_template,
    list_workflow_templates,
    match_workflow_from_query,
)
from agent.orchestrator import AgentOrchestrator, get_orchestrator
from agent.synthesizer import synthesize_report
from agent.llm_adapter import get_llm_adapter
from agent.prompts import (
    SYSTEM_PROMPT,
    SYNTHESIS_PROMPT,
    TOOL_STAGE_LABELS,
    build_context_message,
    get_tool_progress_label,
)

# Shared LLM adapter (unavailable without API key, triggers rule-based fallback)
_LLM = get_llm_adapter()


# =============================================================================
# Schema Tests
# =============================================================================


class TestAgentSchemas(unittest.TestCase):
    """Test Pydantic schema validation and defaults."""

    def test_agent_context_defaults(self):
        ctx = AgentContext()
        self.assertEqual(ctx.market, MarketType.NEM)
        self.assertIsNone(ctx.region)
        self.assertIsNone(ctx.year)
        self.assertEqual(ctx.max_steps, 15)
        self.assertEqual(ctx.params_override, {})

    def test_agent_context_effective_region_nem(self):
        ctx = AgentContext(market=MarketType.NEM)
        self.assertEqual(ctx.effective_region, "NSW1")

    def test_agent_context_effective_region_wem(self):
        ctx = AgentContext(market=MarketType.WEM)
        self.assertEqual(ctx.effective_region, "WEM")

    def test_agent_context_effective_region_explicit(self):
        ctx = AgentContext(region="SA1")
        self.assertEqual(ctx.effective_region, "SA1")

    def test_agent_context_effective_year(self):
        ctx = AgentContext(year=2025)
        self.assertEqual(ctx.effective_year, 2025)

    def test_agent_context_max_steps_bounds(self):
        with self.assertRaises(Exception):
            AgentContext(max_steps=0)
        with self.assertRaises(Exception):
            AgentContext(max_steps=31)

    def test_tool_definition_openai_schema(self):
        td = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        schema = td.to_openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "test_tool")
        self.assertEqual(schema["function"]["description"], "A test tool")

    def test_tool_result_to_llm_message_success(self):
        tr = ToolResult(
            tool_name="test",
            call_id="call_123",
            status=ToolStatus.SUCCESS,
            data={"value": 42},
        )
        msg = tr.to_llm_message()
        self.assertEqual(msg["role"], "tool")
        self.assertEqual(msg["tool_call_id"], "call_123")
        parsed = json.loads(msg["content"])
        self.assertEqual(parsed["value"], 42)

    def test_tool_result_to_llm_message_error(self):
        tr = ToolResult(
            tool_name="test",
            call_id="call_456",
            status=ToolStatus.ERROR,
            error_message="Something failed",
        )
        msg = tr.to_llm_message()
        parsed = json.loads(msg["content"])
        self.assertEqual(parsed["error"], "Something failed")
        self.assertEqual(parsed["status"], "error")

    def test_agent_report_defaults(self):
        report = AgentReport(query="test query")
        self.assertEqual(report.status, WorkflowStatus.COMPLETED)
        self.assertEqual(report.confidence_level, ConfidenceLevel.MEDIUM)
        self.assertEqual(report.stage_results, [])
        self.assertEqual(report.risk_flags, [])
        self.assertIsNotNone(report.generated_at)

    def test_agent_run_request_validation(self):
        req = AgentRunRequest(query="analyze NSW1")
        self.assertEqual(req.market, MarketType.NEM)
        self.assertEqual(req.max_steps, 15)

    def test_agent_run_request_empty_query_rejected(self):
        with self.assertRaises(Exception):
            AgentRunRequest(query="")

    def test_workflow_template_structure(self):
        wt = WorkflowTemplate(
            id="test",
            name="Test Workflow",
            steps=["tool_a", "tool_b"],
            parallel_groups=[[0, 1]],
        )
        self.assertEqual(len(wt.steps), 2)
        self.assertEqual(wt.parallel_groups, [[0, 1]])


# =============================================================================
# Tool Registry Tests
# =============================================================================


class TestToolRegistry(unittest.TestCase):
    """Test tool registration and execution."""

    def test_registry_has_19_tools(self):
        registry = get_tool_registry()
        definitions = registry.list_definitions()
        # 工具数量随功能演进已扩到 31（含 Phase 1-3 的 data_query/chart/
        # scenario/portfolio/generation/market_pulse/weather/report 等）。
        self.assertGreaterEqual(len(definitions), 20)

    def test_registry_tool_names(self):
        registry = get_tool_registry()
        definitions = registry.list_definitions()
        names = {d.name for d in definitions}
        # 核心工具（决策漏斗主链）必须存在；其余扩展工具不做等值断言。
        core_expected = {
            "market_screening",
            "price_trend_analysis",
            "regional_ranking",
            "spike_profit_analysis",
            "peak_analysis",
            "fcas_analysis",
            "saturation_check",
            "cannibalization_forecast",
            "fcas_collapse_forecast",
            "regional_timing_score",
            "merchant_risk_simulate",
            "forward_spread_projection",
            "co_optimized_backtest",
            "investment_analysis",
            "risk_stratification",
            "cross_validation",
            "narrative_attribution",
            "grid_forecast",
            "data_quality_check",
            "compare_regions",
        }
        self.assertTrue(
            core_expected.issubset(names),
            f"Missing core tools: {core_expected - names}",
        )

    def test_all_tools_have_descriptions(self):
        registry = get_tool_registry()
        for defn in registry.list_definitions():
            self.assertTrue(len(defn.description) > 10, f"{defn.name} has short description")

    def test_all_tools_have_stage_labels(self):
        for name in TOOL_STAGE_LABELS:
            self.assertIsInstance(TOOL_STAGE_LABELS[name], str)

    def test_registry_execute_unknown_tool(self):
        registry = get_tool_registry()
        ctx = AgentContext(market=MarketType.NEM, region="NSW1")
        result = asyncio.get_event_loop().run_until_complete(
            registry.execute("nonexistent_tool", {}, context=ctx)
        )
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("unknown tool", result.error_message.lower())

    def test_registry_custom_registration(self):
        registry = ToolRegistry()

        def my_executor(params):
            return {"result": "ok"}

        registry.register(
            ToolDefinition(name="custom", description="Custom tool", parameters={}),
            my_executor,
        )
        self.assertEqual(len(registry.list_definitions()), 1)


# =============================================================================
# Workflow Template Tests
# =============================================================================


class TestWorkflowTemplates(unittest.TestCase):
    """Test predefined workflow templates and keyword matching."""

    def test_six_templates_exist(self):
        templates = list_workflow_templates()
        self.assertEqual(len(templates), 7)

    def test_template_ids(self):
        expected_ids = {
            "full_investment_feasibility",
            "quick_market_overview",
            "fcas_opportunity",
            "revenue_deep_dive",
            "risk_assessment",
            "regional_comparison",
            "investment_screening",
        }
        self.assertEqual(set(WORKFLOW_TEMPLATES.keys()), expected_ids)

    def test_full_investment_has_correct_step_count(self):
        tmpl = get_workflow_template("full_investment_feasibility")
        self.assertIsNotNone(tmpl)
        self.assertEqual(len(tmpl.steps), 11)

    def test_all_template_steps_are_valid_tools(self):
        registry = get_tool_registry()
        valid_names = {d.name for d in registry.list_definitions()}
        for tmpl in list_workflow_templates():
            for step in tmpl.steps:
                self.assertIn(step, valid_names, f"Template '{tmpl.id}' has invalid step '{step}'")

    def test_parallel_groups_reference_valid_indices(self):
        for tmpl in list_workflow_templates():
            n_steps = len(tmpl.steps)
            for group in tmpl.parallel_groups:
                for idx in group:
                    self.assertLess(idx, n_steps, f"Template '{tmpl.id}' group index {idx} >= {n_steps}")

    def test_get_nonexistent_template(self):
        self.assertIsNone(get_workflow_template("does_not_exist"))

    def test_match_full_investment(self):
        self.assertEqual(match_workflow_from_query("run full feasibility analysis"), "full_investment_feasibility")

    def test_match_quick_overview(self):
        self.assertEqual(match_workflow_from_query("quick market overview"), "quick_market_overview")

    def test_match_fcas(self):
        self.assertEqual(match_workflow_from_query("check fcas opportunity"), "fcas_opportunity")

    def test_match_revenue(self):
        self.assertEqual(match_workflow_from_query("analyze revenue spread"), "revenue_deep_dive")

    def test_match_risk(self):
        self.assertEqual(match_workflow_from_query("assess risk profile"), "risk_assessment")

    def test_match_regional(self):
        self.assertEqual(match_workflow_from_query("compare regions ranking"), "regional_comparison")

    def test_match_no_match(self):
        self.assertIsNone(match_workflow_from_query("hello world"))


# =============================================================================
# Orchestrator Tests
# =============================================================================


class TestOrchestrator(unittest.TestCase):
    """Test orchestrator initialization and template execution."""

    def test_orchestrator_defaults(self):
        orch = get_orchestrator()
        self.assertEqual(orch.max_steps, 15)
        self.assertEqual(orch.tool_timeout, 30.0)
        self.assertEqual(orch.total_timeout, 180.0)

    def test_orchestrator_llm_unavailable_without_key(self):
        from agent.llm_adapter import LLMAdapter, LLMConfig

        # Explicitly construct an adapter without API key (isolated from .env)
        config = LLMConfig(provider="openai", api_key="", base_url="", model="gpt-4")
        adapter = LLMAdapter(config)
        self.assertFalse(adapter.is_available())

    def test_fallback_routing_via_keyword(self):
        """When no template specified and LLM unavailable, keyword matching routes."""
        from agent.llm_adapter import LLMAdapter, LLMConfig

        # Force an unavailable LLM so keyword fallback path is exercised
        config = LLMConfig(provider="openai", api_key="", base_url="", model="gpt-4")
        orch = AgentOrchestrator(LLMAdapter(config), get_tool_registry())
        ctx = AgentContext(market=MarketType.NEM, region="SA1")

        report = asyncio.get_event_loop().run_until_complete(
            orch.run(query="run full feasibility analysis for SA1", context=ctx)
        )

        self.assertIsInstance(report, AgentReport)
        self.assertEqual(report.workflow_type, "full_investment_feasibility")

    def test_template_execution_quick_overview(self):
        """Test that template mode executes and returns a report.

        Note: Tools may fail if PostgreSQL is not running, but the
        orchestrator should still return a structured report (possibly FAILED).
        """
        orch = get_orchestrator()
        ctx = AgentContext(market=MarketType.NEM, region="NSW1")

        report = asyncio.get_event_loop().run_until_complete(
            orch.run(
                query="quick market overview",
                context=ctx,
                workflow_template_id="quick_market_overview",
            )
        )

        self.assertIsInstance(report, AgentReport)
        self.assertEqual(report.workflow_type, "quick_market_overview")
        # Status depends on DB availability; all three are valid outcomes
        self.assertIn(report.status, [WorkflowStatus.COMPLETED, WorkflowStatus.PARTIAL, WorkflowStatus.FAILED])
        self.assertGreater(report.total_duration_ms, 0)
        # Stage results should be populated even on failure
        self.assertGreater(len(report.stage_results), 0)

    def test_progress_callback_invoked(self):
        """Progress callback should be called during execution."""
        orch = get_orchestrator()
        ctx = AgentContext(market=MarketType.NEM, region="NSW1")
        progress_msgs = []

        report = asyncio.get_event_loop().run_until_complete(
            orch.run(
                query="quick overview",
                context=ctx,
                workflow_template_id="quick_market_overview",
                progress_callback=lambda msg: progress_msgs.append(msg),
            )
        )

        self.assertGreater(len(progress_msgs), 0)


# =============================================================================
# Synthesizer Tests
# =============================================================================


class TestSynthesizer(unittest.TestCase):
    """Test rule-based report synthesis.

    synthesize_report returns Tuple[str, str, ConfidenceLevel]:
    (executive_summary, recommendation, confidence_level)
    """

    def _make_tool_results(self):
        return [
            ToolResult(
                tool_name="market_screening",
                status=ToolStatus.SUCCESS,
                data={"score": 72, "rank": 2, "region": "NSW1"},
                duration_ms=150.0,
            ),
            ToolResult(
                tool_name="fcas_analysis",
                status=ToolStatus.SUCCESS,
                data={"avg_price": 12.5, "trend": "declining"},
                duration_ms=200.0,
            ),
            ToolResult(
                tool_name="saturation_check",
                status=ToolStatus.ERROR,
                error_message="Data unavailable",
                duration_ms=50.0,
            ),
        ]

    def test_synthesize_returns_tuple(self):
        ctx = AgentContext(market=MarketType.NEM, region="NSW1")
        tool_results = self._make_tool_results()

        result = asyncio.get_event_loop().run_until_complete(
            synthesize_report(
                query="test analysis",
                tool_results=tool_results,
                context=ctx,
                llm=_LLM,
            )
        )

        self.assertIsInstance(result, tuple)
        # synthesize_report 现返回 4 元组（新增 full_analysis 完整 LLM 推理文本）。
        self.assertEqual(len(result), 4)
        summary, recommendation, confidence, full_analysis = result
        self.assertIsInstance(summary, str)
        self.assertIsInstance(recommendation, str)
        self.assertIn(confidence, [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW])

    def test_synthesize_summary_mentions_tools(self):
        ctx = AgentContext(market=MarketType.NEM, region="NSW1")
        tool_results = self._make_tool_results()

        summary, recommendation, confidence, _full = asyncio.get_event_loop().run_until_complete(
            synthesize_report(
                query="test analysis",
                tool_results=tool_results,
                context=ctx,
                llm=_LLM,
            )
        )

        # Rule-based synthesis should reference tool results
        self.assertGreater(len(summary), 0)
        self.assertGreater(len(recommendation), 0)

    def test_synthesize_confidence_with_errors(self):
        """When some tools fail, confidence should not be HIGH."""
        from agent.llm_adapter import LLMAdapter, LLMConfig

        ctx = AgentContext(market=MarketType.NEM, region="NSW1")
        tool_results = self._make_tool_results()  # includes one ERROR

        # Use an unavailable LLM to exercise the deterministic rule-based
        # path; a live LLM's free-text output makes confidence inference
        # non-deterministic and this assertion flaky.
        no_llm = LLMAdapter(LLMConfig(provider="openai", api_key="", base_url="", model="gpt-4"))
        _, _, confidence, _full = asyncio.get_event_loop().run_until_complete(
            synthesize_report(
                query="test",
                tool_results=tool_results,
                context=ctx,
                llm=no_llm,
            )
        )

        # With errors present, confidence should be medium or low
        self.assertIn(confidence, [ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW])

    def test_synthesize_all_success_high_confidence(self):
        """When all tools succeed, confidence can be higher."""
        ctx = AgentContext(market=MarketType.NEM, region="NSW1")
        tool_results = [
            ToolResult(
                tool_name="market_screening",
                status=ToolStatus.SUCCESS,
                data={"score": 85, "rank": 1},
                duration_ms=100.0,
            ),
            ToolResult(
                tool_name="fcas_analysis",
                status=ToolStatus.SUCCESS,
                data={"avg_price": 15.0, "trend": "stable"},
                duration_ms=120.0,
            ),
        ]

        _, _, confidence, _full = asyncio.get_event_loop().run_until_complete(
            synthesize_report(
                query="test",
                tool_results=tool_results,
                context=ctx,
                llm=_LLM,
            )
        )

        self.assertIn(confidence, [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM])


# =============================================================================
# Prompts Tests
# =============================================================================


class TestPrompts(unittest.TestCase):
    """Test prompt construction."""

    def test_system_prompt_contains_key_rules(self):
        self.assertIn("AEMO", SYSTEM_PROMPT)
        self.assertIn("NEM", SYSTEM_PROMPT)

    def test_build_context_message(self):
        ctx = AgentContext(market=MarketType.NEM, region="SA1", year=2025)
        msg = build_context_message(ctx)
        self.assertIn("SA1", msg)
        self.assertIn("NEM", msg)
        self.assertIn("2025", msg)

    def test_tool_progress_labels_cover_all_tools(self):
        registry = get_tool_registry()
        for defn in registry.list_definitions():
            label = get_tool_progress_label(defn.name)
            self.assertIsInstance(label, str)
            self.assertGreater(len(label), 0)


# =============================================================================
# API Route Integration Tests
# =============================================================================


class TestAgentRoutes(unittest.TestCase):
    """Test API endpoints via FastAPI TestClient."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("AUS_ELE_JWT_SECRET", "test_secret_for_agent_routes")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.agent_routes import router

        app = FastAPI()
        app.include_router(router)
        cls.client = TestClient(app)

        # 写操作端点现需 JWT Bearer（P0 安全加固），预先签发一个合法 token。
        import datetime as _dt
        from access_control import _issue_jwt_access_token

        token = _issue_jwt_access_token(
            token_id="test-token",
            principal_id="test-principal",
            workspace_id="test-workspace",
            session_id=None,
            expires_at=_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=1),
        )
        cls.auth_headers = {"Authorization": f"Bearer {token}"}

    def test_list_tools_endpoint(self):
        resp = self.client.get("/api/v1/agent/tools")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 工具数量随功能演进扩展（现 31），断言下限而非硬等值。
        self.assertGreaterEqual(data["total"], 20)
        self.assertEqual(len(data["tools"]), data["total"])

    def test_list_workflows_endpoint(self):
        resp = self.client.get("/api/v1/agent/workflows")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 7)
        self.assertEqual(len(data["workflows"]), 7)

    def test_run_endpoint_with_template(self):
        resp = self.client.post(
            "/api/v1/agent/run",
            headers=self.auth_headers,
            json={
                "query": "quick market overview",
                "market": "NEM",
                "region": "NSW1",
                "workflow_template": "quick_market_overview",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("report", data)
        self.assertIn("status", data)
        report = data["report"]
        self.assertEqual(report["workflow_type"], "quick_market_overview")

    def test_run_endpoint_requires_auth(self):
        # 无 token 应被拒绝（P0 安全加固）
        resp = self.client.post(
            "/api/v1/agent/run",
            json={"query": "quick overview", "workflow_template": "quick_market_overview"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_run_endpoint_invalid_request(self):
        resp = self.client.post(
            "/api/v1/agent/run",
            headers=self.auth_headers,
            json={"query": ""},  # Empty query should fail validation
        )
        self.assertEqual(resp.status_code, 422)

    def test_run_async_endpoint(self):
        resp = self.client.post(
            "/api/v1/agent/run-async",
            headers=self.auth_headers,
            json={
                "query": "quick overview",
                "workflow_template": "quick_market_overview",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("task_id", data)
        self.assertEqual(data["status"], "running")

    def test_task_not_found(self):
        resp = self.client.get("/api/v1/agent/task/nonexistent_id")
        self.assertEqual(resp.status_code, 404)

    def test_history_endpoint(self):
        resp = self.client.get("/api/v1/agent/history", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("executions", data)
        self.assertIn("total", data)


if __name__ == "__main__":
    unittest.main()
