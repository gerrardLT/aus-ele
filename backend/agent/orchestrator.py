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
from agent.tool_profiles import resolve_visible_tools, route_query_to_profile
from agent.workflows import get_workflow_template, match_workflow_from_query

logger = logging.getLogger(__name__)


# =============================================================================
# Progress Callback Type
# =============================================================================

ProgressCallback = Callable[[str], None]  # Receives progress message


# =============================================================================
# History budget (P2-5): bound multi-turn context
# =============================================================================

# Long multi-turn conversations can overflow the LLM context window. We bound
# the injected history with a sliding window (recency matters most for
# follow-ups) plus a rough character budget.
HISTORY_MAX_MESSAGES = 10
HISTORY_MAX_CHARS = 8000


def _trim_history(
    history: Optional[List[Dict[str, str]]],
    max_messages: int = HISTORY_MAX_MESSAGES,
    max_chars: int = HISTORY_MAX_CHARS,
) -> List[Dict[str, str]]:
    """Apply a sliding window + char budget to multi-turn history.

    Keeps only valid user/assistant turns, retains the most recent messages,
    and walks newest-to-oldest accumulating content until the char budget is
    exhausted. Returns messages in chronological order.

    Args:
        history: Raw history list of {role, content} messages (frontend-owned).
        max_messages: Maximum number of recent messages to consider.
        max_chars: Rough character budget across the kept messages.

    Returns:
        Trimmed history (chronological), safe to prepend to the conversation.
    """
    if not history:
        return []
    valid = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")]
    # Sliding window: keep the most recent max_messages.
    valid = valid[-max_messages:]
    # Char budget: walk newest -> oldest, stop once budget is exhausted.
    budget = max_chars
    kept: List[Dict[str, str]] = []
    for m in reversed(valid):
        cost = len(m["content"])
        if budget - cost < 0 and kept:
            break
        kept.append(m)
        budget -= cost
    kept.reverse()  # restore chronological order
    return kept


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

    # B1: 超过此体积的工具结果全量落盘 artifact，回灌只保留摘要+路径
    # （可恢复压缩，对应基线计量的 26.7% 不可逆压缩损失）
    _ARTIFACT_THRESHOLD_CHARS = 3000

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
        from agent.session import get_session_memory  # B6: Redis 后端（自动回落内存）
        self.session_memory = get_session_memory()

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

        # Reset token usage accumulator for this run (P1: cost visibility).
        # A4: 按 execution_id 隔离用量作用域，并发运行不再互相污染。
        if hasattr(self.llm, "reset_usage"):
            self.llm.reset_usage(run_id=execution_id)

        # Determine execution mode
        template = self._resolve_template(workflow_template_id, query)

        if template is not None:
            # Template-driven execution (deterministic)
            report = await self._run_template_mode(
                query, context, template, execution_id, progress_callback
            )
        elif await self.llm.health_check():
            # LLM-driven ReAct execution (only when a LIVE probe succeeds;
            # config-only availability is insufficient — a configured-but-403
            # proxy would otherwise yield an empty FAILED report).
            report = await self._run_react_mode(
                query, context, execution_id, progress_callback
            )
        else:
            # Fallback: try to match a template from query keywords.
            if self.llm.last_health_error:
                logger.warning(
                    "Agent run %s: LLM unhealthy (%s), degrading to template mode",
                    execution_id, self.llm.last_health_error,
                )
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
            # Surface the degradation reason in report metadata for transparency.
            if self.llm.last_health_error and report is not None:
                report.metadata["llm_degraded"] = True
                report.metadata["llm_degraded_reason"] = self.llm.last_health_error

        # Finalize timing
        report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
        report.id = execution_id

        # Record token usage for this run (P1: cost visibility).
        if hasattr(self.llm, "get_usage_snapshot"):
            report.metadata["llm_usage"] = self.llm.get_usage_snapshot(run_id=execution_id)
        if hasattr(self.llm, "end_usage_scope"):
            self.llm.end_usage_scope(run_id=execution_id)

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

        # Reset token usage accumulator for this run (P1: cost visibility).
        # A4: 按 execution_id 隔离用量作用域。
        if hasattr(self.llm, "reset_usage"):
            self.llm.reset_usage(run_id=execution_id)

        # Harness Agent: 取会话记忆上下文（在下方构建消息时 append-only 注入）
        session_id = context.session_id
        session_ctx = (
            self.session_memory.get_context_block(session_id) if session_id else ""
        )
        # 数据版本（会话缓存失效键，A5）：优先显式参数，否则目标年
        data_version = (
            context.params_override.get("data_version") or str(context.effective_year)
        )

        # Forced template or LLM unhealthy -> stream template execution
        # with per-tool events (keeps SSE connection alive). Uses a LIVE probe
        # (not config-only) so a configured-but-403 proxy degrades gracefully.
        template = self._resolve_template(workflow_template_id, query)
        llm_healthy = False if template is not None else await self.llm.health_check()
        if template is not None or not llm_healthy:
            if template is not None:
                reason = "指定模板模式"
            elif self.llm.last_health_error and self.llm.is_available():
                reason = f"LLM 不可用（{self.llm.last_health_error}），降级为模板模式"
            else:
                reason = "LLM 未配置，降级为模板模式"
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
                executive_summary, recommendation, confidence, full_analysis, grounding_repair = await self._synthesize(
                    query, tool_results, context
                )
            except Exception:  # noqa: BLE001
                executive_summary, recommendation, confidence, full_analysis, grounding_repair = ("", "", ConfidenceLevel.LOW, "", {})

            # 降级透明化：非用户指定模板而是因 LLM 不可用降级时，
            # 标记 llm_degraded 供前端 DegradedBanner 展示（与 run() 路径对齐）
            stream_meta = {
                "mode": "template_stream",
                "template_id": template.id,
                "params": effective_params,
            }
            if workflow_template_id is None and not llm_healthy:
                stream_meta["llm_degraded"] = True
                stream_meta["llm_degraded_reason"] = (
                    self.llm.last_health_error or "LLM 不可用"
                )

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
                metadata=stream_meta,
            )
            report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
            # Record token usage for this run (P1: cost visibility).
            if hasattr(self.llm, "get_usage_snapshot"):
                report.metadata["llm_usage"] = self.llm.get_usage_snapshot(run_id=execution_id)
            if hasattr(self.llm, "end_usage_scope"):
                self.llm.end_usage_scope(run_id=execution_id)

            report_answer = full_analysis or self._safe_reasoning_narrative(tool_results, context)
            self._apply_grounding_check(report, report_answer, tool_results, grounding_repair)

            yield {
                "type": "report",
                "report": report.model_dump(mode="json"),
                "answer": report_answer,
            }
            yield {"type": "done"}
            return

        # C4: Plan-and-Execute 波次并行模式（flag 隔离）。计划生成失败时
        # 自然回落下方 ReAct 路径（安全网）。
        if context.enable_plan_execute:
            pe_plan = await self._generate_execution_plan(query, context)
            if pe_plan:
                async for ev in self._run_plan_execute_stream(
                    query, context, execution_id, start_time, pe_plan
                ):
                    yield ev
                return
            yield {"type": "status", "message": "计划生成失败，切换 ReAct 模式"}

        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT + "\n" + DATABASE_SCHEMA_CONTEXT}]
        # P2-5: bound multi-turn history (sliding window + char budget) so long
        # conversations don't overflow the LLM context window.
        for m in _trim_history(history):
            messages.append({"role": m["role"], "content": m["content"]})
        user_content = f"{build_context_message(context)}\n\n用户请求: {query}"
        if session_ctx:
            # KV-cache 友好（Manus 原则：稳定前缀 + append-only）：系统提示前缀
            # 保持固定，动态会话记忆只追加到用户消息尾部，不再改写 messages[0]
            user_content += f"\n\n{session_ctx}"
        messages.append({"role": "user", "content": user_content})

        steps: List[AgentStep] = []
        tool_results: List[ToolResult] = []
        stage_results: List[StageResult] = []
        # PoC：按阶段工具子集暴露。优先级：显式 profile > 意图路由（需开启）> 全量。
        # 可见集运行内固定不变；路由器无法归类时回落全量动作空间（安全网）。
        active_profile = context.tool_profile
        profile_source = "explicit" if active_profile else None
        if active_profile is None and context.enable_tool_routing:
            active_profile = route_query_to_profile(query)
            if active_profile:
                profile_source = "routed"
        visible_tools = resolve_visible_tools(explicit=active_profile)
        openai_tools = self.tools.to_openai_tools(visible_tools)
        final_answer_given = False
        final_content = ""

        # --- Harness Agent: Planning phase ---
        if context.enable_planning and self.llm.is_available():
            # Skip planning if query matches a known template
            if not match_workflow_from_query(query):
                yield {"type": "status", "message": "正在制定分析计划..."}
                plan = await self._generate_plan(query, context, openai_tools)
                if plan:
                    # append-only：不改写已构建的前缀，计划以新消息追加到尾部
                    messages.append({
                        "role": "user",
                        "content": f"当前分析计划（按此计划执行）:\n{plan.model_dump_json()}",
                    })
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
                # A5: 会话缓存命中则跳过重复执行（强制消费 has_result）；
                # 缓存条目带 data_version 哈希，数据同步后自动失效。
                if context.session_id and self.session_memory.has_result(
                    context.session_id, tool_calls[idx]["name"],
                    merged_args_list[idx], data_version,
                ):
                    logger.info(
                        "Session cache hit, skipping %s", tool_calls[idx]["name"],
                    )
                    return ToolResult(
                        tool_name=tool_calls[idx]["name"],
                        call_id=tool_calls[idx]["id"],
                        status=ToolStatus.SUCCESS,
                        data={
                            "cached": True,
                            "summary": self.session_memory.get_summary(
                                context.session_id, tool_calls[idx]["name"],
                                merged_args_list[idx], data_version,
                            ),
                        },
                        metadata={"cached": True},
                    )
                result = await self._execute_tool_with_retry(
                    tool_name=tool_calls[idx]["name"],
                    call_id=tool_calls[idx]["id"],
                    merged_args=merged_args_list[idx],
                    context=context,
                )
                # B1：大结果落盘 artifact（可恢复压缩，回灌摘要附路径）
                self._maybe_persist_artifact(result, execution_id)
                return result

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
                for r, merged_args in zip(raw_results, merged_args_list):
                    if not isinstance(r, Exception) and r.status == ToolStatus.SUCCESS \
                            and not r.metadata.get("cached"):
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
            executive_summary, recommendation, confidence, full_analysis, grounding_repair = await self._synthesize(
                query, tool_results, context
            )
        except Exception as exc:  # noqa: BLE001 - synthesis is best-effort
            logger.warning("Synthesis failed in stream: %s", exc)
            executive_summary, recommendation, confidence, full_analysis, grounding_repair = (
                final_content, "", ConfidenceLevel.LOW, "", {},
            )

        report_metadata = {"mode": "react_stream", "llm_model": self.llm.config.model}
        if visible_tools is not None:
            # A/B 归因：记录本次运行使用的子集 profile、来源与可见工具数
            report_metadata["tool_profile"] = active_profile
            report_metadata["tool_profile_source"] = profile_source
            report_metadata["visible_tool_count"] = len(openai_tools)

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
            metadata=report_metadata,
        )
        report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
        # Record token usage for this run (P1: cost visibility).
        if hasattr(self.llm, "get_usage_snapshot"):
            report.metadata["llm_usage"] = self.llm.get_usage_snapshot(run_id=execution_id)
        if hasattr(self.llm, "end_usage_scope"):
            self.llm.end_usage_scope(run_id=execution_id)

        report_answer = final_content or executive_summary
        self._apply_grounding_check(report, report_answer, tool_results, grounding_repair)

        yield {
            "type": "report",
            "report": report.model_dump(mode="json"),
            "answer": report_answer,
        }
        yield {"type": "done"}

    # =========================================================================
    # Plan-and-Execute Mode (C4)
    # =========================================================================

    _MAX_PLAN_WAVES = 4
    _MAX_REPLAN = 1  # 重规划阀门：整波失败时最多重规划一次，防无限循环

    async def _generate_execution_plan(
        self, query: str, context: AgentContext
    ) -> Optional[Dict[str, Any]]:
        """LLM 生成波次结构执行计划（structured output，非法即返回 None）。"""
        from agent.prompts import PLAN_EXECUTE_PROMPT

        tool_names = [t["function"]["name"] for t in self.tools.to_openai_tools()]
        prompt = PLAN_EXECUTE_PROMPT.format(
            query=query,
            context=build_context_message(context),
            tools=", ".join(tool_names),
        )
        try:
            response = await self.llm.chat([
                {"role": "system", "content": "你是执行规划器。只输出 JSON。"},
                {"role": "user", "content": prompt},
            ])
            content = (response.content or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plan-execute planning failed: %s", exc)
            return None

        waves_raw = data.get("waves")
        if not isinstance(waves_raw, list) or not waves_raw or len(waves_raw) > self._MAX_PLAN_WAVES:
            return None
        registered = set(tool_names)
        waves: List[List[Dict[str, Any]]] = []
        for wave in waves_raw:
            if not isinstance(wave, list):
                return None
            steps = []
            for step in wave[:4]:  # 每波次最多 4 个工具
                if isinstance(step, dict) and step.get("tool") in registered:
                    args = step.get("args") if isinstance(step.get("args"), dict) else {}
                    steps.append({"tool": step["tool"], "args": args})
            if steps:
                waves.append(steps)
        if not waves:
            return None
        return {"goal": data.get("goal", ""), "waves": waves,
                "reasoning": data.get("reasoning", "")}

    async def _run_plan_execute_stream(
        self,
        query: str,
        context: AgentContext,
        execution_id: str,
        start_time: float,
        plan: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        """按波次并行执行计划（同波次 asyncio.gather），含一次重规划阀门。"""
        yield {"type": "plan", "plan": plan}

        steps: List[AgentStep] = []
        tool_results: List[ToolResult] = []
        stage_results: List[StageResult] = []
        replans_left = self._MAX_REPLAN
        wave_idx = 0

        while wave_idx < len(plan["waves"]):
            if time.perf_counter() - start_time > self.total_timeout:
                yield {"type": "status", "message": "达到总超时，提前结束"}
                break

            wave = plan["waves"][wave_idx]
            merged_args_list = []
            for st in wave:
                merged = dict(st["args"])
                if "region" not in merged and context.effective_region:
                    merged["region"] = context.effective_region
                if "year" not in merged:
                    merged["year"] = context.effective_year
                for k, v in context.params_override.items():
                    if k not in merged:
                        merged[k] = v
                merged_args_list.append(merged)

            for i, st in enumerate(wave):
                yield {
                    "type": "tool_call", "step": len(steps) + i + 1,
                    "name": st["tool"], "call_id": f"pe_{wave_idx}_{i}",
                    "arguments": merged_args_list[i],
                }

            async def _exec_pe(i: int, _wave=wave, _widx=wave_idx) -> ToolResult:
                return await self._execute_tool_with_retry(
                    tool_name=_wave[i]["tool"],
                    call_id=f"pe_{_widx}_{i}",
                    merged_args=merged_args_list[i],
                    context=context,
                )

            raw_results = await asyncio.gather(
                *[_exec_pe(i) for i in range(len(wave))], return_exceptions=True,
            )

            wave_has_success = False
            for i, raw in enumerate(raw_results):
                if isinstance(raw, Exception):
                    result = ToolResult(
                        tool_name=wave[i]["tool"], call_id=f"pe_{wave_idx}_{i}",
                        status=ToolStatus.ERROR, error_message=str(raw),
                    )
                else:
                    result = raw
                self._maybe_persist_artifact(result, execution_id)
                tool_results.append(result)
                sr = self._to_stage_result(result)
                stage_results.append(sr)
                steps.append(AgentStep(
                    step_number=len(steps) + 1,
                    thought=f"Plan wave {wave_idx + 1}",
                    action=ToolCall(id=f"pe_{wave_idx}_{i}", tool_name=wave[i]["tool"],
                                    arguments=merged_args_list[i]),
                    observation=result,
                ))
                yield {
                    "type": "tool_result", "step": len(steps),
                    "name": result.tool_name, "call_id": result.call_id,
                    "status": result.status.value, "duration_ms": result.duration_ms,
                    "summary": sr.summary, "key_metrics": sr.key_metrics,
                    "error": result.error_message, "retry_count": result.retry_count,
                    "chart": result.data.get("chart") if result.data else None,
                    "download_path": result.data.get("download_path") if result.data else None,
                }
                if result.status == ToolStatus.SUCCESS:
                    wave_has_success = True

            # 重规划阀门：整波失败且还有后续波次时，尝试重新规划一次
            if not wave_has_success and replans_left > 0 and wave_idx < len(plan["waves"]) - 1:
                replans_left -= 1
                yield {"type": "status", "message": "整波失败，尝试重新规划..."}
                new_plan = await self._generate_execution_plan(query, context)
                if new_plan:
                    plan = new_plan
                    wave_idx = 0
                    yield {"type": "plan", "plan": plan}
                    continue
            wave_idx += 1

        # 状态判定 + 综合（与 ReAct 分支同构）
        success_count = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
        if not tool_results:
            status = WorkflowStatus.FAILED
        elif success_count == len(tool_results):
            status = WorkflowStatus.COMPLETED
        elif success_count > 0:
            status = WorkflowStatus.PARTIAL
        else:
            status = WorkflowStatus.FAILED

        yield {"type": "status", "message": "正在生成结构化报告..."}
        try:
            executive_summary, recommendation, confidence, full_analysis, grounding_repair = await self._synthesize(
                query, tool_results, context
            )
        except Exception:  # noqa: BLE001
            executive_summary, recommendation, confidence, full_analysis, grounding_repair = ("", "", ConfidenceLevel.LOW, "", {})

        report = AgentReport(
            id=execution_id,
            query=query,
            workflow_type="plan_execute",
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
            metadata={"mode": "plan_execute", "llm_model": self.llm.config.model,
                      "plan_goal": plan.get("goal", "")},
        )
        report.total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
        if hasattr(self.llm, "get_usage_snapshot"):
            report.metadata["llm_usage"] = self.llm.get_usage_snapshot(run_id=execution_id)
        if hasattr(self.llm, "end_usage_scope"):
            self.llm.end_usage_scope(run_id=execution_id)

        report_answer = full_analysis or executive_summary
        self._apply_grounding_check(report, report_answer, tool_results, grounding_repair)

        yield {
            "type": "report",
            "report": report.model_dump(mode="json"),
            "answer": report_answer,
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
        executive_summary, recommendation, confidence, full_analysis, grounding_repair = await self._synthesize(
            query, tool_results, context
        )

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
            steps=steps,
            status=status,
            metadata={
                "mode": "template",
                "template_id": template.id,
                "template_name": template.name,
            },
        )
        self._apply_grounding_check(
            report, full_analysis or executive_summary, tool_results, grounding_repair
        )
        return report

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
        executive_summary, recommendation, confidence, full_analysis, grounding_repair = await self._synthesize(
            query, tool_results, context
        )

        report = AgentReport(
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
        self._apply_grounding_check(
            report, full_analysis or executive_summary, tool_results, grounding_repair
        )
        return report

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
    ) -> tuple[str, str, ConfidenceLevel, str, dict]:
        """Synthesize tool results into executive summary and recommendation.

        内嵌 Generate → Verify → Repair 溯源修复环（2026-08-13）：
        首次合成后做数值溯源检查，超阈值时带修复指令重合成一次，
        取两次中 ungrounded_ratio 更低者（绝不劣化）。修复环自身异常
        只降级不阻断；规则合成路径（LLM 不可用）不触发。

        Returns:
            Tuple of (executive_summary, recommendation, confidence_level,
            full_analysis, grounding_repair_info)
        """
        from agent.synthesizer import synthesize_report

        result = await synthesize_report(
            query=query,
            tool_results=tool_results,
            context=context,
            llm=self.llm,
        )
        repair_info: dict = {"attempted": False, "used": False}
        try:
            import os

            from agent.grounding import (
                build_repair_feedback,
                check_numeric_grounding,
                should_repair,
            )

            if os.environ.get("AUS_ELE_AGENT_GROUNDING_REPAIR", "1") not in ("0", "false", ""):
                check = check_numeric_grounding(result[3] or "", tool_results)
                if should_repair(check) and self.llm.is_available():
                    feedback = build_repair_feedback(check["ungrounded_samples"])
                    result2 = await synthesize_report(
                        query=query,
                        tool_results=tool_results,
                        context=context,
                        llm=self.llm,
                        repair_feedback=feedback,
                    )
                    check2 = check_numeric_grounding(result2[3] or "", tool_results)
                    repair_info.update({
                        "attempted": True,
                        "before_ratio": check["ungrounded_ratio"],
                        "after_ratio": check2["ungrounded_ratio"],
                    })
                    # 取更优者；修复无效则保留原版
                    if check2["ungrounded_ratio"] <= check["ungrounded_ratio"]:
                        result = result2
                        repair_info.update({
                            "used": True,
                            "improved": check2["ungrounded_ratio"] < check["ungrounded_ratio"],
                        })
        except Exception as exc:  # noqa: BLE001 - 修复环自身不得弄崩合成
            logger.debug("Grounding repair skipped: %s", exc)
            repair_info.setdefault("error", str(exc))

        return result[0], result[1], result[2], result[3], repair_info

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

    def _maybe_persist_artifact(self, result: ToolResult, execution_id: str) -> None:
        """B1：大结果全量落盘，回灌摘要附路径（可恢复压缩）。

        文件名平铺为 artifact_<execution_id>_<tool>_<rand>.json，复用现有
        /api/v1/agent/download/{filename} 路由（其路径穿越防护同样生效）。
        """
        if result.status != ToolStatus.SUCCESS or not isinstance(result.data, dict):
            return
        if result.metadata.get("artifact_path") or result.metadata.get("cached"):
            return
        try:
            payload = json.dumps(result.data, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            return
        if len(payload) <= self._ARTIFACT_THRESHOLD_CHARS:
            return
        try:
            from pathlib import Path

            out_dir = Path(__file__).resolve().parent.parent.parent / "output"
            out_dir.mkdir(exist_ok=True)
            safe_name = "".join(
                c if c.isalnum() or c in "_-" else "_" for c in result.tool_name
            )
            filename = f"artifact_{execution_id}_{safe_name}_{uuid.uuid4().hex[:6]}.json"
            (out_dir / filename).write_text(payload, encoding="utf-8")
            result.metadata["artifact_path"] = f"/api/v1/agent/download/{filename}"
            result.metadata["artifact_chars"] = len(payload)
            logger.debug("Artifact persisted: %s (%d chars)", filename, len(payload))
        except Exception as exc:  # noqa: BLE001 - 落盘失败不阻断主流程
            logger.debug("Artifact persist failed: %s", exc)

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
                    if res.get("fcas_compression_factor"):
                        parts.append(
                            "- FCAS 基线已按压缩因子 "
                            f"{res.get('fcas_compression_factor')} 下调（FCAS 收益持续压缩）\n"
                        )
                cis = data.get("cis_floor", {})
                if cis.get("included"):
                    if cis.get("binding"):
                        parts.append(
                            f"- CIS floor 抬升: NPV {self._fmt(cis.get('npv_before_cis_aud'))} → "
                            f"**{self._fmt(cis.get('npv_with_cis_floor_aud'))} AUD**"
                            f"（floor {self._fmt(cis.get('floor_aud_per_mw_year'))} AUD/MW/年，配置锚点）\n"
                        )
                    else:
                        parts.append("- CIS floor 不构成抬升（merchant 基线已高于 floor）\n")
            elif r.tool_name == "bess_revenue_benchmark":
                summary = data.get("summary", {})
                if summary:
                    parts.append(
                        f"- 最近完整月({summary.get('latest_month', '?')})基准收益: "
                        f"**{summary.get('latest_index_k_aud_per_mw_year', '?')} kAUD/MW/年**\n"
                    )
                    parts.append(
                        f"- 滚动均值: {summary.get('avg_index_k_aud_per_mw_year', '?')} kAUD/MW/年"
                        f"（偏离 {summary.get('latest_vs_avg_pct', '?')}%）\n"
                    )
                    parts.append("- 口径: derived 理想放电，FCAS/容量不含，不与第三方指数绝对值对比\n")
                if data.get("headline"):
                    parts.append(f"- {data['headline']}\n")
            elif r.tool_name == "grid_knowledge_lookup":
                matches = data.get("matches", [])
                if matches:
                    for m in matches[:3]:
                        parts.append(
                            f"- 【{m.get('market', '?')}】{m.get('title', '?')}"
                            f"（生效 {m.get('effective_date') or '待定'}，置信 {m.get('confidence', '?')}）\n"
                        )
                else:
                    parts.append("- 知识库未命中相关规则卡片\n")
            elif r.tool_name == "market_event_lookup":
                matches = data.get("matches", [])
                if matches:
                    for m in matches[:3]:
                        parts.append(
                            f"- 【案例】{m.get('title', '?')}（{m.get('period', '?')}，"
                            f"置信 {m.get('confidence', '?')}）\n"
                        )
                else:
                    parts.append("- 案例库未命中相关事件\n")
            elif r.tool_name == "asset_pipeline_lookup":
                if data.get("by_status"):
                    parts.append(
                        f"- 管线汇总({data.get('region', 'ALL')})：活跃供给 "
                        f"**{data.get('active_supply_mw', '?')} MW**"
                        f"（registered/committed/construction）\n"
                    )
                    fresh = data.get("freshness", {})
                    if fresh.get("stale"):
                        parts.append("- ⚠ 管线数据已超 120 天未更新，需走季度更新流程\n")
                elif data.get("matches") is not None:
                    parts.append(f"- 项目检索命中 {data.get('total_after_filter', 0)} 个\n")
            elif r.tool_name == "knowledge_health_check":
                summary = data.get("summary", {})
                if summary:
                    parts.append(
                        f"- 知识库体检：逾期 {summary.get('overdue', 0)} 项、"
                        f"临期 {summary.get('due_soon', 0)} 项、正常 {summary.get('ok', 0)} 项\n"
                    )
                for it in data.get("items", []):
                    if it.get("status") in ("overdue", "due_soon"):
                        mark = "⚠逾期" if it["status"] == "overdue" else "临期"
                        parts.append(f"- [{mark}] {it.get('name')}: {it.get('detail')}\n")
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

    # =========================================================================
    # Numeric Grounding Check (A1)
    # =========================================================================

    def _apply_grounding_check(
        self, report: AgentReport, answer: str, tool_results: List[ToolResult],
        grounding_repair: Optional[dict] = None,
    ) -> None:
        """数值溯源校验：结果写入 metadata，高占比不可溯源时追加风险标记。

        只观测不阻断：误报时最多多一条风险提示，不会让报告失败。
        grounding_repair（2026-08-13）：非空时写入修复环元信息。
        """
        if grounding_repair:
            report.metadata["grounding_repair"] = grounding_repair
        try:
            from agent.grounding import check_numeric_grounding

            check = check_numeric_grounding(answer or "", tool_results)
            report.metadata["numeric_grounding"] = check
            if check["checked"] >= 4 and check["ungrounded_ratio"] > 0.5:
                report.risk_flags.append(
                    f"数值溯源警示：回答中 {check['checked']} 个数字有 "
                    f"{check['checked'] - check['grounded']} 个未能追溯到工具结果，"
                    f"请人工复核关键数值"
                )
        except Exception as exc:  # noqa: BLE001 - 护栏自身不得弄崩报告
            logger.debug("Grounding check skipped: %s", exc)

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
