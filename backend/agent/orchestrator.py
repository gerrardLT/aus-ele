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
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from agent.llm_adapter import LLMAdapter, LLMRequestError, LLMUnavailableError
from agent.prompts import (
    SYSTEM_PROMPT,
    DATABASE_SCHEMA_CONTEXT,
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

    # Tools that are pure-read and safe to cache within a session.
    # Only tools whose output depends solely on (region, year) belong here.
    # peak_analysis (window_hours) and spike_profit (threshold) are excluded.
    _CACHEABLE_TOOLS = {
        "data_quality_check", "price_trend_analysis",
        "saturation_check", "market_screening",
    }
    _CACHE_TTL_SECONDS = 300  # 5 minutes

    # Per-tool timeout overrides (seconds). Heavy tools scan large tables or run
    # MILP/backtests and legitimately exceed the default 30s under real data.
    # market_screening/regional_ranking share the market-screening engine which
    # aggregates a full year of 5-minute prices (~540k rows) across regions.
    _HEAVY_TOOL_TIMEOUTS = {
        "market_screening": 90.0,
        "regional_ranking": 90.0,
        "co_optimized_backtest": 90.0,
        "investment_analysis": 60.0,
    }

    def _timeout_for(self, tool_name: str) -> float:
        """Resolve the effective per-tool timeout (heavy tools get a longer budget)."""
        return self._HEAVY_TOOL_TIMEOUTS.get(tool_name, self.tool_timeout)

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
        self._tool_cache: Dict[str, tuple] = {}  # key -> (timestamp, ToolResult)
        from agent.session import SessionMemory  # Harness Agent
        self.session_memory = SessionMemory()  # Harness Agent

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
    # Streaming ReAct Execution (SSE)
    # =========================================================================

    async def run_stream(
        self,
        query: str,
        context: AgentContext,
        history: Optional[List[Dict[str, str]]] = None,
        workflow_template_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute a ReAct run, yielding SSE events for live debugging.

        Event types yielded (dicts):
            start        {execution_id}
            status       {message}
            token        {step, delta}          -- assistant reasoning/answer tokens
            tool_call    {step, name, call_id, arguments}
            tool_result  {step, name, call_id, status, duration_ms, summary, key_metrics, error}
            answer_end   {step}                  -- terminal answer finished streaming
            report       {report, answer}        -- final structured report
            error        {message}
            done         {}

        Multi-turn: ``history`` is a list of prior {role, content} messages
        (owned by the frontend). Follow-ups re-enter the full ReAct loop and
        may call tools again.
        """
        execution_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        yield {"type": "start", "execution_id": execution_id}

        # Harness Agent: inject session memory context
        session_id = context.session_id
        if session_id:
            session_ctx = self.session_memory.get_context_block(session_id)
            if session_ctx:
                # Will be injected into messages after they're built
                pass  # stored for later injection

        # Forced template or LLM unavailable -> stream template execution
        # with per-tool events (keeps SSE connection alive).
        template = self._resolve_template(workflow_template_id, query)
        if template is not None or not self.llm.is_available():
            reason = "指定模板模式" if template is not None else "LLM 未配置，降级为模板模式"
            yield {"type": "status", "message": reason}

            # Resolve template for fallback keyword matching
            if template is None:
                fallback_id = match_workflow_from_query(query)
                template = get_workflow_template(fallback_id or "quick_market_overview")

            effective_params = {**template.default_params, **context.params_override}
            tool_results: List[ToolResult] = []
            stage_results: List[StageResult] = []
            step_num = 0

            # Market-aware filtering: skip NEM-only tools for WEM
            NEM_ONLY_TOOLS = {"fcas_analysis", "fcas_collapse_forecast", "regional_timing_score", "regional_ranking"}
            is_wem = context.market.value == "WEM"
            filtered_steps = [
                s for s in template.steps if not (is_wem and s in NEM_ONLY_TOOLS)
            ]
            total_steps = len(filtered_steps)

            # Rebuild parallel groups with filtered indices
            step_to_idx = {s: i for i, s in enumerate(template.steps)}
            filtered_groups = []
            for group in (template.parallel_groups or [[i] for i in range(len(template.steps))]):
                fg = [step_to_idx[template.steps[idx]] for idx in group
                      if idx < len(template.steps) and not (is_wem and template.steps[idx] in NEM_ONLY_TOOLS)]
                if fg:
                    filtered_groups.append(fg)

            for group in filtered_groups:
                group_tasks = []
                group_names = []
                for idx in group:
                    if idx < len(template.steps):
                        tool_name = template.steps[idx]
                        group_names.append(tool_name)
                        # Emit tool_call event
                        step_num += 1
                        yield {
                            "type": "tool_call",
                            "step": step_num,
                            "total": total_steps,
                            "name": tool_name,
                            "call_id": f"tmpl_{step_num}",
                            "arguments": effective_params,
                        }
                        group_tasks.append(
                            self._execute_tool(tool_name, effective_params, context, step_num)
                        )

                if not group_tasks:
                    continue

                results = await asyncio.gather(*group_tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        result = ToolResult(
                            tool_name=group_names[i],
                            status=ToolStatus.ERROR,
                            error_message=str(result),
                        )
                    tool_results.append(result)
                    sr = self._to_stage_result(result)
                    stage_results.append(sr)
                    yield {
                        "type": "tool_result",
                        "step": step_num - len(group_tasks) + 1 + i,
                        "name": result.tool_name,
                        "call_id": f"tmpl_{step_num - len(group_tasks) + 1 + i}",
                        "status": result.status.value,
                        "duration_ms": result.duration_ms,
                        "summary": sr.summary,
                        "key_metrics": sr.key_metrics,
                        "error": result.error_message,
                        "retry_count": result.retry_count,
                        "chart": result.data.get("chart") if result.data else None,
                        "download_path": result.data.get("download_path") if result.data else None,
                    }

            # Determine status
            success_count = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
            if not tool_results:
                status = WorkflowStatus.FAILED
            elif success_count == len(tool_results):
                status = WorkflowStatus.COMPLETED
            elif success_count > 0:
                status = WorkflowStatus.PARTIAL
            else:
                status = WorkflowStatus.FAILED

            # Synthesize
            yield {"type": "status", "message": "正在生成结构化报告..."}
            try:
                executive_summary, recommendation, confidence, full_analysis = await self._synthesize(
                    query, tool_results, context
                )
            except Exception:  # noqa: BLE001
                executive_summary, recommendation, confidence, full_analysis = ("", "", ConfidenceLevel.LOW, "")

            report = AgentReport(
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
                steps=[],
                status=status,
                metadata={"mode": "template_stream", "template_id": template.id, "params": effective_params},
            )
            report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)

            yield {
                "type": "report",
                "report": report.model_dump(mode="json"),
                "answer": full_analysis or self._safe_reasoning_narrative(tool_results, context),
            }
            yield {"type": "done"}
            return

        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT + "\n" + DATABASE_SCHEMA_CONTEXT}]
        if history:
            for m in history:
                role = m.get("role")
                content = m.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({
            "role": "user",
            "content": f"{build_context_message(context)}\n\n用户请求: {query}",
        })

        # Harness Agent: inject session memory into system message
        if session_id:
            session_ctx = self.session_memory.get_context_block(session_id)
            if session_ctx:
                messages[0]["content"] += f"\n\n{session_ctx}"

        steps: List[AgentStep] = []
        tool_results: List[ToolResult] = []
        stage_results: List[StageResult] = []
        openai_tools = self.tools.to_openai_tools()
        final_answer_given = False
        final_content = ""

        # --- Harness Agent: Planning phase ---
        if context.enable_planning and self.llm.is_available():
            # Skip planning if query matches a known template
            if not match_workflow_from_query(query):
                yield {"type": "status", "message": "正在制定分析计划..."}
                plan = await self._generate_plan(query, context, openai_tools)
                if plan:
                    messages[0]["content"] += f"\n\n当前分析计划:\n{plan.model_dump_json()}"
                    yield {"type": "plan", "plan": plan.model_dump()}

        for step_num in range(1, self.max_steps + 1):
            if time.perf_counter() - start_time > self.total_timeout:
                yield {"type": "status", "message": "达到总超时，提前结束"}
                break

            content_buf = ""
            tool_calls: List[Dict[str, Any]] = []
            try:
                async for ev in self.llm.chat_stream_events(messages, openai_tools):
                    etype = ev.get("type")
                    if etype == "content":
                        content_buf += ev["text"]
                        yield {"type": "token", "step": step_num, "delta": ev["text"]}
                    elif etype == "tool_calls":
                        tool_calls = ev["tool_calls"]
            except (LLMRequestError, LLMUnavailableError) as exc:
                logger.error("Stream LLM call failed at step %d: %s", step_num, exc)
                yield {"type": "error", "message": f"LLM 调用失败: {exc}"}
                break

            # --- Harness Agent: Reflection parsing ---
            if context.enable_reflection and content_buf:
                reflection = self._parse_reflection(content_buf)
                if reflection:
                    yield {
                        "type": "reflection",
                        "step": step_num,
                        "verdict": reflection["verdict"],
                        "reason": reflection["reason"],
                    }

            # No tool calls -> the streamed content is the final answer.
            if not tool_calls:
                final_answer_given = True
                final_content = content_buf
                steps.append(AgentStep(step_number=step_num, thought=content_buf))
                yield {"type": "answer_end", "step": step_num}
                break

            # Record assistant turn (with tool calls) into the conversation.
            messages.append({
                "role": "assistant",
                "content": content_buf or "",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # Emit all tool_call events first (frontend shows them as running)
            merged_args_list = []
            for tc in tool_calls:
                merged_args = dict(tc["arguments"])
                if "region" not in merged_args and context.effective_region:
                    merged_args["region"] = context.effective_region
                if "year" not in merged_args:
                    merged_args["year"] = context.effective_year
                for k, v in context.params_override.items():
                    if k not in merged_args:
                        merged_args[k] = v
                merged_args_list.append(merged_args)
                yield {
                    "type": "tool_call",
                    "step": step_num,
                    "name": tc["name"],
                    "call_id": tc["id"],
                    "arguments": merged_args,
                }

            # Execute tools in parallel (with retry)
            async def _exec_one(idx: int) -> ToolResult:
                return await self._execute_tool_with_retry(
                    tool_name=tool_calls[idx]["name"],
                    call_id=tool_calls[idx]["id"],
                    merged_args=merged_args_list[idx],
                    context=context,
                )

            raw_results = await asyncio.gather(
                *[_exec_one(i) for i in range(len(tool_calls))],
                return_exceptions=True,
            )

            # Process results and emit events
            for i, raw in enumerate(raw_results):
                if isinstance(raw, Exception):
                    result = ToolResult(
                        tool_name=tool_calls[i]["name"],
                        call_id=tool_calls[i]["id"],
                        status=ToolStatus.ERROR,
                        error_message=str(raw),
                    )
                else:
                    result = raw
                tool_results.append(result)
                sr = self._to_stage_result(result)
                stage_results.append(sr)
                steps.append(AgentStep(
                    step_number=step_num,
                    thought=content_buf if i == 0 else "",
                    action=ToolCall(id=tool_calls[i]["id"], tool_name=tool_calls[i]["name"], arguments=merged_args_list[i]),
                    observation=result,
                ))
                yield {
                    "type": "tool_result",
                    "step": step_num,
                    "name": tool_calls[i]["name"],
                    "call_id": tool_calls[i]["id"],
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                    "summary": sr.summary,
                    "key_metrics": sr.key_metrics,
                    "error": result.error_message,
                    "retry_count": result.retry_count,
                    "chart": result.data.get("chart") if result.data else None,
                    "download_path": result.data.get("download_path") if result.data else None,
                }
                messages.append(result.to_llm_message())
            content_buf = ""  # avoid attributing prior reasoning to next tool

            # Harness Agent: store successful results in session memory (version-aware cache)
            if session_id:
                # Get current data version from context.params_override['data_version'] or compute default
                data_version = context.params_override.get("data_version")
                if not data_version:
                    # Default: effective_year as string (e.g. '2026')
                    data_version = str(context.effective_year)
                
                for r, merged_args in zip(raw_results, merged_args_list):
                    if not isinstance(r, Exception) and r.status == ToolStatus.SUCCESS:
                        summary = self._to_stage_result(r).summary or r.tool_name
                        self.session_memory.put(session_id, r.tool_name, merged_args, summary, data_version)

        # Determine status
        success_count = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
        if not tool_results:
            status = WorkflowStatus.COMPLETED if final_answer_given else WorkflowStatus.FAILED
        elif success_count == len(tool_results):
            status = WorkflowStatus.COMPLETED
        elif success_count > 0:
            status = WorkflowStatus.PARTIAL
        else:
            status = WorkflowStatus.FAILED

        # Build the structured report card (synthesizer may call the LLM).
        yield {"type": "status", "message": "正在生成结构化报告..."}
        try:
            executive_summary, recommendation, confidence, full_analysis = await self._synthesize(
                query, tool_results, context
            )
        except Exception as exc:  # noqa: BLE001 - synthesis is best-effort
            logger.warning("Synthesis failed in stream: %s", exc)
            executive_summary, recommendation, confidence, full_analysis = (
                final_content, "", ConfidenceLevel.LOW, "",
            )

        report = AgentReport(
            id=execution_id,
            query=query,
            workflow_type="react_llm_stream",
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
            metadata={"mode": "react_stream", "llm_model": self.llm.config.model},
        )
        report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)

        yield {
            "type": "report",
            "report": report.model_dump(mode="json"),
            "answer": final_content or executive_summary,
        }
        yield {"type": "done"}

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
        executive_summary, recommendation, confidence, _ = await self._synthesize(
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
            {"role": "system", "content": SYSTEM_PROMPT + "\n" + DATABASE_SCHEMA_CONTEXT},
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

            # Execute tool calls in parallel
            merged_args_list = []
            for tc in response.tool_calls:
                merged_args = dict(tc["arguments"])
                if "region" not in merged_args and context.effective_region:
                    merged_args["region"] = context.effective_region
                if "year" not in merged_args:
                    merged_args["year"] = context.effective_year
                for k, v in context.params_override.items():
                    if k not in merged_args:
                        merged_args[k] = v
                merged_args_list.append(merged_args)

            if progress_callback:
                labels = [get_tool_progress_label(tc["name"]) for tc in response.tool_calls]
                progress_callback("正在执行: " + " + ".join(labels))

            async def _exec_react(idx: int) -> ToolResult:
                return await self.tools.execute(
                    tool_name=response.tool_calls[idx]["name"],
                    arguments=merged_args_list[idx],
                    context=context,
                    call_id=response.tool_calls[idx]["id"],
                    timeout_seconds=self._timeout_for(response.tool_calls[idx]["name"]),
                )

            raw_results = await asyncio.gather(
                *[_exec_react(i) for i in range(len(response.tool_calls))],
                return_exceptions=True,
            )

            for i, raw in enumerate(raw_results):
                if isinstance(raw, Exception):
                    result = ToolResult(
                        tool_name=response.tool_calls[i]["name"],
                        call_id=response.tool_calls[i]["id"],
                        status=ToolStatus.ERROR,
                        error_message=str(raw),
                    )
                else:
                    result = raw
                tool_results.append(result)
                steps.append(AgentStep(
                    step_number=step_num,
                    thought=response.content or "" if i == 0 else "",
                    action=ToolCall(id=response.tool_calls[i]["id"], tool_name=response.tool_calls[i]["name"], arguments=merged_args_list[i]),
                    observation=result,
                ))
                stage_results.append(self._to_stage_result(result))
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
        executive_summary, recommendation, confidence, _ = await self._synthesize(
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
        """Execute a single tool with context-aware parameter injection and caching."""
        # Inject context defaults
        arguments = dict(params)
        if "region" not in arguments:
            arguments["region"] = context.effective_region
        if "year" not in arguments:
            arguments["year"] = context.effective_year

        # Session-level cache for read-only tools
        if tool_name in self._CACHEABLE_TOOLS:
            cache_key = f"{tool_name}:{arguments.get('region')}:{arguments.get('year')}"
            cached = self._tool_cache.get(cache_key)
            if cached:
                ts, result = cached
                if time.perf_counter() - ts < self._CACHE_TTL_SECONDS:
                    logger.debug("Cache hit for %s", cache_key)
                    return result

        call_id = f"call_{step_idx}_{tool_name}"
        result = await self.tools.execute(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            call_id=call_id,
            timeout_seconds=self._timeout_for(tool_name),
        )

        # Store in cache if successful
        if tool_name in self._CACHEABLE_TOOLS and result.status == ToolStatus.SUCCESS:
            cache_key = f"{tool_name}:{arguments.get('region')}:{arguments.get('year')}"
            self._tool_cache[cache_key] = (time.perf_counter(), result)

        return result

    # =========================================================================
    # Synthesis
    # =========================================================================

    async def _synthesize(
        self,
        query: str,
        tool_results: List[ToolResult],
        context: AgentContext,
    ) -> tuple[str, str, ConfidenceLevel, str]:
        """Synthesize tool results into executive summary and recommendation.

        Returns:
            Tuple of (executive_summary, recommendation, confidence_level, full_analysis)
        """
        from agent.synthesizer import synthesize_report

        return await synthesize_report(
            query=query,
            tool_results=tool_results,
            context=context,
            llm=self.llm,
        )

    # =========================================================================
    # Harness Agent: Planning, Reflection, Retry
    # =========================================================================

    async def _generate_plan(
        self, query: str, context: AgentContext, tools: List[Dict[str, Any]]
    ) -> Optional["AnalysisPlan"]:
        """Call LLM to generate an analysis plan (does not execute)."""
        from agent.prompts import PLANNING_PROMPT
        from agent.schemas import AnalysisPlan

        tool_names = [t["function"]["name"] for t in tools]
        prompt = PLANNING_PROMPT.format(
            query=query,
            context=build_context_message(context),
            tools=", ".join(tool_names),
        )
        try:
            response = await self.llm.chat([
                {"role": "system", "content": "你是分析规划器。只输出 JSON。"},
                {"role": "user", "content": prompt},
            ])
            # Try to parse JSON from response
            content = response.content.strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(content)
            return AnalysisPlan(**data)
        except Exception as exc:
            logger.debug("Planning failed (non-critical): %s", exc)
            return None

    def _parse_reflection(self, content: str) -> Optional[Dict[str, str]]:
        """Parse inline [REFLECT] tag from LLM content."""
        import re
        match = re.search(
            r'\[REFLECT\]\s*step=(\d+)\s*verdict=(\w+)\s*reason="([^"]*)"',
            content,
        )
        if match:
            return {
                "step": match.group(1),
                "verdict": match.group(2),
                "reason": match.group(3),
            }
        return None

    def _adapt_args_on_failure(
        self, tool_name: str, args: Dict[str, Any], error: Optional[str]
    ) -> Dict[str, Any]:
        """Rule-based parameter adaptation on tool failure (no LLM needed)."""
        adapted = dict(args)
        err_lower = (error or "").lower()

        if "timeout" in err_lower or "timed out" in err_lower:
            # Reduce computation-heavy params
            if "n_simulations" in adapted:
                adapted["n_simulations"] = max(50, adapted["n_simulations"] // 2)
            if "projection_years" in adapted:
                adapted["projection_years"] = max(5, adapted["projection_years"] // 2)
        elif "no_data" in err_lower or "no data" in err_lower or "not found" in err_lower:
            # Try previous year
            if "year" in adapted and isinstance(adapted["year"], int):
                adapted["year"] = adapted["year"] - 1

        return adapted

    async def _execute_tool_with_retry(
        self, tool_name: str, call_id: str, merged_args: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Execute a tool with adaptive retry on failure."""
        max_attempts = (context.max_retries + 1) if context.enable_retry else 1
        result: Optional[ToolResult] = None

        for attempt in range(max_attempts):
            result = await self.tools.execute(
                tool_name=tool_name,
                arguments=merged_args,
                context=context,
                call_id=call_id,
                timeout_seconds=self._timeout_for(tool_name),
            )
            result.retry_count = attempt

            if result.status == ToolStatus.SUCCESS:
                return result

            # Adapt args for next attempt
            if attempt < max_attempts - 1:
                merged_args = self._adapt_args_on_failure(tool_name, merged_args, result.error_message)

        return result  # type: ignore[return-value]

    # =========================================================================
    # Reasoning Narrative (rule-based, always available)
    # =========================================================================

    def _safe_reasoning_narrative(
        self, tool_results: List[ToolResult], context: AgentContext
    ) -> str:
        """Wrapper that never crashes — returns empty string on any error."""
        try:
            return self._build_reasoning_narrative(tool_results, context)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reasoning narrative generation failed: %s", exc)
            return ""

    @staticmethod
    def _fmt(value, fmt_str: str = "{:,.0f}") -> str:
        """Safe formatter: returns '?' for None/non-numeric values."""
        if value is None:
            return "?"
        try:
            return fmt_str.format(value)
        except (TypeError, ValueError):
            return str(value)

    def _build_reasoning_narrative(
        self, tool_results: List[ToolResult], context: AgentContext
    ) -> str:
        """Generate a step-by-step reasoning narrative from tool results.

        Produces a readable analysis walkthrough regardless of LLM availability.
        """
        from agent.prompts import get_tool_progress_label

        parts: List[str] = []
        parts.append(f"## 分析推理过程\n")
        parts.append(f"市场: **{context.market.value}** / 区域: **{context.effective_region}** / 年份: **{context.effective_year}**\n")

        for i, r in enumerate(tool_results, 1):
            label = get_tool_progress_label(r.tool_name)
            if r.status != ToolStatus.SUCCESS:
                parts.append(f"### {i}. {label}\n")
                parts.append(f"- 状态: **失败** — {r.error_message or '未知错误'}\n")
                continue

            parts.append(f"### {i}. {label}\n")
            data = r.data or {}

            # Extract key findings per tool type
            if r.tool_name == "data_quality_check":
                markets = data.get("markets", [])
                for m in (markets if isinstance(markets, list) else []):
                    if isinstance(m, dict):
                        parts.append(f"- {m.get('market', '?')}: quality_score={m.get('quality_score', '?')}, grade={m.get('data_grade', '?')}\n")
            elif r.tool_name == "price_trend_analysis":
                stats = data.get("stats", {})
                if stats:
                    parts.append(f"- 均价: **{stats.get('avg_price', '?')} AUD/MWh**\n")
                    parts.append(f"- 价格范围: {stats.get('min_price', '?')} ~ {stats.get('max_price', '?')}\n")
                    parts.append(f"- 波动率(标准差): {stats.get('std_dev', '?')}\n")
                    parts.append(f"- 负价比例: **{stats.get('negative_ratio_pct', '?')}%**\n")
            elif r.tool_name == "peak_analysis":
                summary = data.get("summary", {})
                if summary:
                    parts.append(f"- 最优充电均价: {summary.get('charge_avg_price', '?')} AUD/MWh\n")
                    parts.append(f"- 最优放电均价: {summary.get('discharge_avg_price', '?')} AUD/MWh\n")
                    parts.append(f"- 毛价差: **{summary.get('gross_spread', '?')} AUD/MWh**\n")
            elif r.tool_name == "investment_analysis":
                res = data.get("results", {})
                if res:
                    parts.append(f"- NPV: **{self._fmt(res.get('npv_aud'))} AUD**\n")
                    parts.append(f"- IRR: {self._fmt(res.get('irr_pct'), '{:.1f}')}%\n")
                    parts.append(f"- 简单回收期: {res.get('simple_payback_years', '?')} 年\n")
                    parts.append(f"- 年均净收入: {self._fmt(res.get('annual_net_revenue_aud'))} AUD\n")
            elif r.tool_name == "fcas_analysis":
                summary = data.get("summary", {})
                if summary:
                    rev = summary.get("total_net_incremental_revenue_k")
                    parts.append(f"- FCAS 净增量收入: {self._fmt(rev, '{:.0f}')}k AUD/年\n")
                    parts.append(f"- 可行服务数: {summary.get('viable_service_count', '?')}\n")
            elif r.tool_name == "merchant_risk_simulate":
                dist = data.get("distribution", {})
                if dist:
                    parts.append(f"- P10: {self._fmt(dist.get('p10'))} AUD/MW/年\n")
                    parts.append(f"- P50: **{self._fmt(dist.get('p50'))} AUD/MW/年**\n")
                    parts.append(f"- P90: {self._fmt(dist.get('p90'))} AUD/MW/年\n")
            elif r.tool_name == "grid_forecast":
                summary = data.get("summary", {})
                if summary:
                    parts.append(f"- 电网压力: {summary.get('grid_stress_score', '?')}\n")
                    parts.append(f"- 价格尖峰风险: {summary.get('price_spike_risk_score', '?')}\n")
            elif r.tool_name == "co_optimized_backtest":
                parts.append(f"- 能量收入: {self._fmt(data.get('energy_revenue'))} AUD\n")
                parts.append(f"- FCAS 收入: {self._fmt(data.get('fcas_revenue'))} AUD\n")
                parts.append(f"- 联合优化提升: {self._fmt(data.get('co_optimization_uplift'))} AUD\n")
            elif r.tool_name == "risk_stratification":
                l1 = data.get("layer1", {})
                l3 = data.get("layer3", {})
                parts.append(f"- Layer 1 (基础套利): {self._fmt(l1.get('revenue') if isinstance(l1, dict) else None)} AUD\n")
                parts.append(f"- Layer 3 (极端事件): {self._fmt(l3.get('revenue') if isinstance(l3, dict) else None)} AUD\n")
            else:
                # Generic: show first few keys
                keys = list(data.keys())[:4]
                if keys:
                    parts.append(f"- 返回字段: {', '.join(keys)}\n")

        # Closing judgment
        success_count = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
        parts.append(f"\n## 综合判断\n")
        parts.append(f"共执行 {len(tool_results)} 个分析工具，{success_count} 个成功返回。")
        if success_count < len(tool_results):
            failed = [r.tool_name for r in tool_results if r.status != ToolStatus.SUCCESS]
            parts.append(f"以下分析未能完成: {', '.join(failed)}，结论置信度相应降低。")

        return "\n".join(parts)

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
