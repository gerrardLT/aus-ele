"""Agent Orchestrator — Core ReAct execution loop.

Implements the main orchestration logic:
1. LLM-driven mode: ReAct loop where LLM decides which tools to call
2. Template mode: Deterministic execution of predefined workflow templates
3. Graceful degradation: Falls back to template mode when LLM is unavailable

The orchestrator coordinates tool execution, manages conversation state,
and delegates report synthesis to the Synthesizer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from agent.llm_adapter import LLMAdapter, LLMRequestError, LLMUnavailableError
from agent.prompts import (
    SYSTEM_PROMPT,
    build_context_message,
    get_tool_progress_label,
)
from agent.schemas import (
    AgentContext,
    AgentReport,
    AgentStep,
    ConfidenceLevel,
    StageResult,
    ToolCall,
    ToolResult,
    ToolStatus,
    WorkflowStatus,
    WorkflowTemplate,
)
from agent.tools import ToolRegistry
from agent.workflows import get_workflow_template, match_workflow_from_query

logger = logging.getLogger(__name__)


# =============================================================================
# Progress Callback Type
# =============================================================================

ProgressCallback = Callable[[str], None]  # Receives progress message


# =============================================================================
# Orchestrator
# =============================================================================


class AgentOrchestrator:
    """Core agent orchestrator implementing ReAct loop and template execution.

    Usage:
        orchestrator = AgentOrchestrator(llm, tools)
        report = await orchestrator.run("分析 NSW1 投资可行性", context)
    """

    def __init__(
        self,
        llm: LLMAdapter,
        tools: ToolRegistry,
        max_steps: int = 15,
        tool_timeout: float = 30.0,
        total_timeout: float = 180.0,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.tool_timeout = tool_timeout
        self.total_timeout = total_timeout

    async def run(
        self,
        query: str,
        context: AgentContext,
        workflow_template_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AgentReport:
        """Execute a complete agent workflow.

        Args:
            query: Natural language user request.
            context: Execution context (market, region, params).
            workflow_template_id: Force a specific template (bypasses LLM routing).
            progress_callback: Optional callback for progress updates.

        Returns:
            AgentReport with all results and synthesis.
        """
        execution_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        logger.info(
            "Agent run %s started: query=%r, market=%s, region=%s",
            execution_id, query[:80], context.market.value, context.effective_region,
        )

        # Determine execution mode
        template = self._resolve_template(workflow_template_id, query)

        if template is not None:
            # Template-driven execution (deterministic)
            report = await self._run_template_mode(
                query, context, template, execution_id, progress_callback
            )
        elif self.llm.is_available():
            # LLM-driven ReAct execution
            report = await self._run_react_mode(
                query, context, execution_id, progress_callback
            )
        else:
            # Fallback: try to match a template from query keywords
            fallback_id = match_workflow_from_query(query)
            if fallback_id:
                fallback_template = get_workflow_template(fallback_id)
                report = await self._run_template_mode(
                    query, context, fallback_template, execution_id, progress_callback
                )
            else:
                # Last resort: run quick_market_overview
                default_template = get_workflow_template("quick_market_overview")
                report = await self._run_template_mode(
                    query, context, default_template, execution_id, progress_callback
                )

        # Finalize timing
        report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
        report.id = execution_id

        logger.info(
            "Agent run %s completed: status=%s, duration=%.0fms, tools_called=%d",
            execution_id, report.status.value, report.total_duration_ms,
            len(report.tool_trace),
        )
        return report

    # =========================================================================
    # Template Resolution
    # =========================================================================

    def _resolve_template(
        self, template_id: Optional[str], query: str
    ) -> Optional[WorkflowTemplate]:
        """Resolve which template to use, if any."""
        if template_id:
            return get_workflow_template(template_id)
        return None

    # =========================================================================
    # Template Mode Execution
    # =========================================================================

    async def _run_template_mode(
        self,
        query: str,
        context: AgentContext,
        template: WorkflowTemplate,
        execution_id: str,
        progress_callback: Optional[ProgressCallback],
    ) -> AgentReport:
        """Execute a predefined workflow template deterministically."""
        logger.info("Running template mode: %s", template.id)

        steps: List[AgentStep] = []
        tool_results: List[ToolResult] = []
        stage_results: List[StageResult] = []

        # Merge template default params with context overrides
        effective_params = {**template.default_params, **context.params_override}

        # Execute steps by parallel groups
        if template.parallel_groups:
            step_idx = 0
            for group in template.parallel_groups:
                # Execute all tools in this group concurrently
                group_tasks = []
                for idx in group:
                    if idx < len(template.steps):
                        tool_name = template.steps[idx]
                        group_tasks.append(
                            self._execute_tool(tool_name, effective_params, context, step_idx)
                        )
                        step_idx += 1

                if group_tasks:
                    if progress_callback:
                        labels = [get_tool_progress_label(template.steps[i]) for i in group if i < len(template.steps)]
                        progress_callback("正在执行: " + " + ".join(labels))

                    results = await asyncio.gather(*group_tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            tool_name = template.steps[group[i]] if group[i] < len(template.steps) else "unknown"
                            result = ToolResult(
                                tool_name=tool_name,
                                status=ToolStatus.ERROR,
                                error_message=str(result),
                            )
                        tool_results.append(result)
                        steps.append(AgentStep(
                            step_number=len(steps) + 1,
                            thought=f"Template step: {result.tool_name}",
                            action=ToolCall(tool_name=result.tool_name, arguments=effective_params),
                            observation=result,
                        ))
                        stage_results.append(self._to_stage_result(result))
        else:
            # Sequential execution
            for i, tool_name in enumerate(template.steps):
                if progress_callback:
                    progress_callback(f"正在执行: {get_tool_progress_label(tool_name)}")

                result = await self._execute_tool(tool_name, effective_params, context, i)
                tool_results.append(result)
                steps.append(AgentStep(
                    step_number=i + 1,
                    thought=f"Template step: {tool_name}",
                    action=ToolCall(tool_name=tool_name, arguments=effective_params),
                    observation=result,
                ))
                stage_results.append(self._to_stage_result(result))

        # Determine overall status
        success_count = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
        if success_count == len(tool_results):
            status = WorkflowStatus.COMPLETED
        elif success_count > 0:
            status = WorkflowStatus.PARTIAL
        else:
            status = WorkflowStatus.FAILED

        # Generate synthesis (LLM or fallback)
        executive_summary, recommendation, confidence = await self._synthesize(
            query, tool_results, context
        )

        return AgentReport(
            id=execution_id,
            query=query,
            workflow_type=template.id,
            region=context.effective_region,
            market=context.market.value,
            executive_summary=executive_summary,
            stage_results=stage_results,
            recommendation=recommendation,
            confidence_level=confidence,
            risk_flags=self._extract_risk_flags(tool_results),
            data_quality_notes=self._extract_quality_notes(tool_results),
            tool_trace=tool_results,
            steps=steps,
            status=status,
            metadata={
                "mode": "template",
                "template_id": template.id,
                "template_name": template.name,
            },
        )

    # =========================================================================
    # ReAct Mode Execution (LLM-driven)
    # =========================================================================

    async def _run_react_mode(
        self,
        query: str,
        context: AgentContext,
        execution_id: str,
        progress_callback: Optional[ProgressCallback],
    ) -> AgentReport:
        """Execute using LLM-driven ReAct loop."""
        logger.info("Running ReAct mode (LLM-driven)")

        # Build initial messages
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{build_context_message(context)}\n\n用户请求: {query}"},
        ]

        steps: List[AgentStep] = []
        tool_results: List[ToolResult] = []
        stage_results: List[StageResult] = []
        openai_tools = self.tools.to_openai_tools()
        final_answer_given = False

        start_time = time.perf_counter()

        for step_num in range(1, self.max_steps + 1):
            # Check total timeout
            elapsed = time.perf_counter() - start_time
            if elapsed > self.total_timeout:
                logger.warning("Agent run %s hit total timeout (%.0fs)", execution_id, elapsed)
                break

            # Call LLM
            try:
                response = await self.llm.chat(messages, tools=openai_tools)
            except (LLMRequestError, LLMUnavailableError) as exc:
                logger.error("LLM call failed at step %d: %s", step_num, exc)
                break

            # If LLM returns content without tool calls → final answer
            if not response.has_tool_calls:
                final_answer_given = True
                steps.append(AgentStep(
                    step_number=step_num,
                    thought=response.content,
                ))
                break

            # Process tool calls
            # Add assistant message with tool calls to conversation
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in response.tool_calls:
                tool_name = tc["name"]
                arguments = tc["arguments"]
                call_id = tc["id"]

                if progress_callback:
                    progress_callback(f"正在执行: {get_tool_progress_label(tool_name)}")

                # Merge context defaults into the tool arguments without
                # mutating the dict returned by the LLM (which is also kept in
                # the assistant message sent back to the model).
                merged_args = dict(arguments)
                if "region" not in merged_args and context.effective_region:
                    merged_args["region"] = context.effective_region
                if "year" not in merged_args:
                    merged_args["year"] = context.effective_year
                # Apply user param overrides
                for k, v in context.params_override.items():
                    if k not in merged_args:
                        merged_args[k] = v

                result = await self.tools.execute(
                    tool_name=tool_name,
                    arguments=merged_args,
                    context=context,
                    call_id=call_id,
                    timeout_seconds=self.tool_timeout,
                )

                tool_results.append(result)
                steps.append(AgentStep(
                    step_number=step_num,
                    thought=response.content or "",
                    action=ToolCall(id=call_id, tool_name=tool_name, arguments=merged_args),
                    observation=result,
                ))
                stage_results.append(self._to_stage_result(result))

                # Add tool result to conversation
                messages.append(result.to_llm_message())

        # Determine status
        success_count = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
        if not tool_results:
            # No tools executed. A direct LLM final answer is a valid
            # completion; only treat it as failure when the loop ended without
            # any answer (e.g. LLM/timeout error).
            status = WorkflowStatus.COMPLETED if final_answer_given else WorkflowStatus.FAILED
        elif success_count == len(tool_results):
            status = WorkflowStatus.COMPLETED
        elif success_count > 0:
            status = WorkflowStatus.PARTIAL
        else:
            status = WorkflowStatus.FAILED

        # Synthesize final report
        executive_summary, recommendation, confidence = await self._synthesize(
            query, tool_results, context
        )

        return AgentReport(
            id=execution_id,
            query=query,
            workflow_type="react_llm",
            region=context.effective_region,
            market=context.market.value,
            executive_summary=executive_summary,
            stage_results=stage_results,
            recommendation=recommendation,
            confidence_level=confidence,
            risk_flags=self._extract_risk_flags(tool_results),
            data_quality_notes=self._extract_quality_notes(tool_results),
            tool_trace=tool_results,
            steps=steps,
            status=status,
            metadata={"mode": "react", "llm_model": self.llm.config.model},
        )

    # =========================================================================
    # Tool Execution Helper
    # =========================================================================

    async def _execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: AgentContext,
        step_idx: int,
    ) -> ToolResult:
        """Execute a single tool with context-aware parameter injection."""
        # Inject context defaults
        arguments = dict(params)
        if "region" not in arguments:
            arguments["region"] = context.effective_region
        if "year" not in arguments:
            arguments["year"] = context.effective_year

        call_id = f"call_{step_idx}_{tool_name}"
        return await self.tools.execute(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            call_id=call_id,
            timeout_seconds=self.tool_timeout,
        )

    # =========================================================================
    # Synthesis
    # =========================================================================

    async def _synthesize(
        self,
        query: str,
        tool_results: List[ToolResult],
        context: AgentContext,
    ) -> tuple[str, str, ConfidenceLevel]:
        """Synthesize tool results into executive summary and recommendation.

        Returns:
            Tuple of (executive_summary, recommendation, confidence_level)
        """
        from agent.synthesizer import synthesize_report

        return await synthesize_report(
            query=query,
            tool_results=tool_results,
            context=context,
            llm=self.llm,
        )

    # =========================================================================
    # Result Helpers
    # =========================================================================

    def _to_stage_result(self, result: ToolResult) -> StageResult:
        """Convert a ToolResult to a StageResult."""
        # Extract key metrics from data
        key_metrics = {}
        data = result.data
        if isinstance(data, dict):
            # Pull out summary/stats/results sub-dicts
            for key in ("summary", "stats", "results", "ranking"):
                if key in data and isinstance(data[key], dict):
                    key_metrics[key] = data[key]
            # Pull scalar values
            for k, v in data.items():
                if isinstance(v, (int, float, str, bool)) and k not in ("region", "year"):
                    key_metrics[k] = v

        return StageResult(
            stage_name=result.tool_name,
            tool_name=result.tool_name,
            summary=f"{result.tool_name}: {result.status.value}",
            key_metrics=key_metrics,
            status=result.status,
            duration_ms=result.duration_ms,
        )

    def _extract_risk_flags(self, tool_results: List[ToolResult]) -> List[str]:
        """Extract risk flags from tool results."""
        flags = []
        for result in tool_results:
            if result.status == ToolStatus.ERROR:
                flags.append(f"{result.tool_name} 执行失败: {result.error_message}")
            elif result.status == ToolStatus.TIMEOUT:
                flags.append(f"{result.tool_name} 执行超时")
            # Check for data quality issues in results
            if result.status == ToolStatus.SUCCESS:
                data = result.data
                if isinstance(data, dict):
                    if data.get("status") == "no_data":
                        flags.append(f"{result.tool_name}: 无可用数据")
        return flags

    def _extract_quality_notes(self, tool_results: List[ToolResult]) -> List[str]:
        """Extract data quality notes from results."""
        notes = []
        for result in tool_results:
            if result.tool_name == "data_quality_check" and result.status == ToolStatus.SUCCESS:
                markets = result.data.get("markets", {})
                for market, info in markets.items():
                    score = info.get("average_quality_score")
                    if score is not None and score < 0.7:
                        notes.append(f"{market} 数据质量偏低 (score={score:.2f})")
                    grades = info.get("data_grades", [])
                    if "preview" in grades or "analytical-preview" in grades:
                        notes.append(f"{market} 部分数据为预览级别 (preview)")
        if not notes:
            notes.append("数据质量检查未发现显著问题")
        return notes


# =============================================================================
# Singleton Factory
# =============================================================================

_orchestrator_instance: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the singleton orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        from agent.llm_adapter import get_llm_adapter
        from agent.tools import get_tool_registry

        _orchestrator_instance = AgentOrchestrator(
            llm=get_llm_adapter(),
            tools=get_tool_registry(),
        )
    return _orchestrator_instance
