"""Report Synthesizer.

Synthesizes multiple tool results into a coherent executive summary
and investment recommendation. Supports two modes:
1. LLM-powered: Uses LLM to generate natural language synthesis
2. Rule-based fallback: Deterministic template when LLM is unavailable
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from agent.llm_adapter import LLMAdapter, LLMRequestError, LLMUnavailableError
from agent.prompts import SYNTHESIS_PROMPT, FALLBACK_REPORT_TEMPLATE
from agent.schemas import AgentContext, ConfidenceLevel, ToolResult, ToolStatus
from agent.tool_contracts import (
    INVEST_NPV_KEY,
    INVEST_PAYBACK_KEY,
    INVEST_RESULTS_KEY,
    SCREENING_ITEMS_KEY,
    SCREENING_LABEL_KEY,
    SCREENING_SCORE_KEY,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Main Synthesis Function
# =============================================================================


async def synthesize_report(
    query: str,
    tool_results: List[ToolResult],
    context: AgentContext,
    llm: LLMAdapter,
) -> Tuple[str, str, ConfidenceLevel, str]:
    """Synthesize tool results into executive summary and recommendation.

    Args:
        query: Original user query.
        tool_results: List of all tool execution results.
        context: Agent execution context.
        llm: LLM adapter instance.

    Returns:
        Tuple of (executive_summary, recommendation, confidence_level, full_analysis)
        where full_analysis is the complete LLM reasoning text (empty for rule-based).
    """
    if llm.is_available():
        try:
            return await _llm_synthesize(query, tool_results, context, llm)
        except (LLMRequestError, LLMUnavailableError) as exc:
            logger.warning("LLM synthesis failed, falling back to rules: %s", exc)

    summary, rec, conf = _rule_based_synthesize(query, tool_results, context)
    return summary, rec, conf, ""


# =============================================================================
# LLM-Powered Synthesis
# =============================================================================


async def _llm_synthesize(
    query: str,
    tool_results: List[ToolResult],
    context: AgentContext,
    llm: LLMAdapter,
) -> Tuple[str, str, ConfidenceLevel, str]:
    """Use LLM to generate synthesis from tool results."""
    # Build compact tool results summary for LLM context
    results_text = _format_tool_results_for_llm(tool_results)

    prompt = SYNTHESIS_PROMPT.format(
        query=query,
        tool_results=results_text,
    )

    messages = [
        {"role": "system", "content": "你是能源市场分析专家。基于提供的工具调用结果生成分析报告。只使用提供的数据，不编造数值。"},
        {"role": "user", "content": prompt},
    ]

    response = await llm.chat(messages)
    content = response.content

    # Parse structured output from LLM response
    executive_summary = _extract_section(content, "执行摘要") or content[:500]
    recommendation = _extract_section(content, "综合建议") or ""
    confidence = _infer_confidence(tool_results, content)

    # Return full LLM analysis as the 4th value for "reasoning process" display
    return executive_summary, recommendation, confidence, content


def _format_tool_results_for_llm(tool_results: List[ToolResult]) -> str:
    """Format tool results into a compact text representation for LLM context.

    Uses the same structured-summary strategy as ToolResult.to_llm_message
    (P1: unified truncation path) instead of brute-force JSON slicing, so
    synthesis and the ReAct loop feed the LLM consistent, information-dense
    representations rather than arbitrarily cut JSON.
    """
    parts = []
    for result in tool_results:
        if result.status == ToolStatus.SUCCESS:
            data = result.data
            if isinstance(data, dict):
                # Structured summary (stats/lengths/samples), capped at 2000 chars.
                data_str = result._summarize_dict(data, max_chars=2000)
            else:
                data_str = json.dumps(data, ensure_ascii=False, default=str)
                if len(data_str) > 2000:
                    data_str = data_str[:2000] + "...(truncated)"
            parts.append(f"### {result.tool_name} (成功, {result.duration_ms:.0f}ms)\n{data_str}")
        else:
            parts.append(f"### {result.tool_name} ({result.status.value})\n错误: {result.error_message}")
    return "\n\n".join(parts)


def _extract_section(text: str, section_name: str) -> str:
    """Extract a named section from markdown-formatted LLM output."""
    lines = text.split("\n")
    capturing = False
    section_lines = []
    for line in lines:
        if section_name in line and line.strip().startswith("#"):
            capturing = True
            continue
        if capturing:
            if line.strip().startswith("#"):
                break
            section_lines.append(line)
    return "\n".join(section_lines).strip()


def _infer_confidence(tool_results: List[ToolResult], llm_text: str) -> ConfidenceLevel:
    """Infer confidence level from tool results, data quality, and LLM output.

    Upgraded algorithm considers:
    1. Critical tool success (investment_analysis, co_optimized_backtest)
    2. Data quality grade (preview caps at MEDIUM)
    3. Overall tool success ratio
    4. LLM explicit confidence markers (only as tiebreaker)
    """
    total = len(tool_results)
    if total == 0:
        return ConfidenceLevel.LOW

    success = sum(1 for r in tool_results if r.status == ToolStatus.SUCCESS)
    ratio = success / total

    # Check data quality — preview grade caps confidence at MEDIUM
    data_grade_preview = False
    for r in tool_results:
        if r.tool_name == "data_quality_check" and r.status == ToolStatus.SUCCESS:
            markets = r.data.get("markets", [])
            if isinstance(markets, list):
                for m in markets:
                    if isinstance(m, dict) and m.get("data_grade") == "preview":
                        data_grade_preview = True
                        break

    # Check critical tools
    CRITICAL_TOOLS = {"investment_analysis", "co_optimized_backtest", "merchant_risk_simulate"}
    critical_failed = any(
        r.tool_name in CRITICAL_TOOLS and r.status != ToolStatus.SUCCESS
        for r in tool_results
    )

    # Base confidence from success ratio
    if ratio >= 0.9 and not critical_failed:
        base = ConfidenceLevel.HIGH
    elif ratio >= 0.6:
        base = ConfidenceLevel.MEDIUM
    else:
        base = ConfidenceLevel.LOW

    # Downgrade rules
    if data_grade_preview and base == ConfidenceLevel.HIGH:
        base = ConfidenceLevel.MEDIUM
    if critical_failed and base == ConfidenceLevel.HIGH:
        base = ConfidenceLevel.MEDIUM

    # LLM text as tiebreaker (only upgrade MEDIUM→HIGH if all tools succeeded)
    if base == ConfidenceLevel.MEDIUM and ratio == 1.0 and not data_grade_preview:
        text_lower = llm_text.lower()
        if "high" in text_lower or "高置信" in text_lower:
            base = ConfidenceLevel.HIGH

    return base


# =============================================================================
# Rule-Based Fallback Synthesis
# =============================================================================


def _rule_based_synthesize(
    query: str,
    tool_results: List[ToolResult],
    context: AgentContext,
) -> Tuple[str, str, ConfidenceLevel]:
    """Generate deterministic synthesis without LLM."""
    success_results = [r for r in tool_results if r.status == ToolStatus.SUCCESS]
    failed_results = [r for r in tool_results if r.status != ToolStatus.SUCCESS]

    # Build executive summary from available data
    summary_parts = []
    summary_parts.append(
        f"针对「{query}」的分析工作流已完成，"
        f"共执行 {len(tool_results)} 个分析工具，"
        f"其中 {len(success_results)} 个成功返回。"
    )

    # Extract key findings from successful tools
    key_findings = _extract_key_findings(success_results)
    if key_findings:
        summary_parts.append("核心发现: " + "; ".join(key_findings[:3]))

    if failed_results:
        failed_names = [r.tool_name for r in failed_results]
        summary_parts.append(f"以下分析未能完成: {', '.join(failed_names)}")

    executive_summary = " ".join(summary_parts)

    # Build recommendation
    recommendation = _build_rule_recommendation(success_results, context)

    # Determine confidence
    total = len(tool_results)
    success_count = len(success_results)
    if total == 0:
        confidence = ConfidenceLevel.LOW
    elif success_count / total >= 0.9:
        confidence = ConfidenceLevel.MEDIUM  # Rule-based is never "high"
    elif success_count / total >= 0.5:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    return executive_summary, recommendation, confidence


def _extract_key_findings(results: List[ToolResult]) -> List[str]:
    """Extract key findings from successful tool results."""
    findings = []
    for result in results:
        data = result.data
        if not isinstance(data, dict):
            continue

        # Price trend findings
        if result.tool_name == "price_trend_analysis":
            stats = data.get("stats", {})
            if stats:
                avg = stats.get("avg_price")
                neg = stats.get("negative_ratio_pct")
                if avg is not None:
                    findings.append(f"均价 {avg} AUD/MWh")
                if neg is not None and neg > 5:
                    findings.append(f"负价比例 {neg}%")

        # Investment analysis findings
        elif result.tool_name == "investment_analysis":
            res = data.get(INVEST_RESULTS_KEY, {})
            npv = res.get(INVEST_NPV_KEY)
            payback = res.get(INVEST_PAYBACK_KEY)
            if npv is not None:
                findings.append(f"NPV {npv:,.0f} AUD")
            if payback is not None and payback < 30:
                findings.append(f"回收期 {payback} 年")

        # Market screening findings
        elif result.tool_name == "market_screening":
            candidates = data.get(SCREENING_ITEMS_KEY, [])
            if candidates:
                top = candidates[0]
                findings.append(f"最优区域 {top.get(SCREENING_LABEL_KEY, '?')} (评分 {top.get(SCREENING_SCORE_KEY, '?')})")

        # FCAS findings
        elif result.tool_name == "fcas_analysis":
            summary = data.get("summary", {})
            total_rev = summary.get("total_net_incremental_revenue_k")
            if total_rev is not None and total_rev > 0:
                findings.append(f"FCAS 增量收入 {total_rev:.0f}k AUD/年")

    return findings


def _build_rule_recommendation(results: List[ToolResult], context: AgentContext) -> str:
    """Build a rule-based recommendation from tool results."""
    # Look for investment analysis result
    for result in results:
        if result.tool_name == "investment_analysis" and result.status == ToolStatus.SUCCESS:
            res = result.data.get("results", {})
            npv = res.get("npv_aud")
            if npv is not None:
                if npv > 0:
                    return (
                        f"基于当前数据，{context.effective_region} 区域 BESS 投资 NPV 为正值 "
                        f"({npv:,.0f} AUD)，在给定假设条件下具备投资吸引力。"
                        f"建议结合 FCAS 收入叠加和前瞻情景进一步验证。"
                    )
                else:
                    return (
                        f"基于当前数据，{context.effective_region} 区域 BESS 投资 NPV 为负值 "
                        f"({npv:,.0f} AUD)，在当前假设条件下投资回报不达标。"
                        f"建议调整参数假设或考虑其他区域。"
                    )

    # Fallback recommendation
    return (
        f"已完成 {context.effective_region} 区域的多维度分析。"
        f"请查阅各阶段详细数据，结合投资目标和风险偏好做出判断。"
        f"本报告为分析参考，不构成投资建议。"
    )
