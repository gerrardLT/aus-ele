"""Agent 经验库汇总服务（Experience Analytics，2026-08-13）。

数据基础：``agent_execution_log`` 表（埋点已存在，_log_execution/_log_execution_dict
在每次运行后落库 query/steps/status/duration/answer）。本服务做月度汇总分析：

1. 问题意图聚类（确定性关键词规则，与 tool_profiles 路由规则同族）
2. 工具调用频次与失败率（发现"从未被调用的工具"与高失败工具）
3. 慢查询与失败案例抽样（答不好的问题线索）

设计约束：
- 只读聚合，不修改埋点数据；best-effort（表缺失/为空返回空汇总）
- 不存储用户身份；principal 不落经验库（隐私边界）
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 意图聚类规则（从具体到泛化，首中即止；未命中归 other）
_INTENT_RULES: list[tuple[str, list[str]]] = [
    ("rules_knowledge", ["什么是", "规则", "机制", "政策", "制度", "常识"]),
    ("events", ["大停电", "黑系统", "退役", "事件", "历史上", "负价潮"]),
    ("investment", ["npv", "irr", "投资", "回收期", "值得投", "可行性"]),
    ("benchmark", ["基准", "benchmark", "市场基准", "指数"]),
    ("revenue", ["收入", "收益", "套利", "fcas", "辅助服务", "尖峰", "价差"]),
    ("risk", ["风险", "崩塌", "蚕食", "饱和", "蒙特卡洛", "商户"]),
    ("market_overview", ["概览", "趋势", "现状", "怎么样", "筛选", "排名", "对比"]),
    ("data_export", ["导出", "csv", "图表", "画图", "数据"]),
]

# 已注册工具全集（用于发现"从未被调用的工具"）
_KNOWN_TOOLS = [
    "data_quality_check", "market_screening", "price_trend_analysis",
    "regional_ranking", "bess_revenue_benchmark", "grid_knowledge_lookup",
    "market_event_lookup", "spike_profit_analysis", "peak_analysis",
    "fcas_analysis", "saturation_check", "cannibalization_forecast",
    "fcas_collapse_forecast", "regional_timing_score", "merchant_risk_simulate",
    "forward_spread_projection", "co_optimized_backtest", "investment_analysis",
    "risk_stratification", "cross_validation", "narrative_attribution",
    "grid_forecast", "compare_regions", "scenario_simulation",
    "portfolio_analysis", "generate_report", "multi_market_analysis",
    "data_query", "timeseries_analysis", "export_data", "generate_chart",
    "market_pulse", "read_artifact", "weather_correlation", "generation_analysis",
    "asset_pipeline_lookup",
]


def classify_intent(query: str) -> str:
    """确定性意图分类（与路由规则同族，未命中归 other）。"""
    if not query:
        return "empty"
    q = query.lower()
    for intent, keywords in _INTENT_RULES:
        if any(kw in q for kw in keywords):
            return intent
    return "other"


def _extract_tool_usage(steps_json: str) -> list[dict]:
    try:
        steps = json.loads(steps_json) if steps_json else []
    except (TypeError, json.JSONDecodeError):
        return []
    usage = []
    for s in steps if isinstance(steps, list) else []:
        if not isinstance(s, dict):
            continue
        # 兼容三种历史格式：顶层 tool_name / action.tool_name / tool.name
        action = s.get("action") if isinstance(s.get("action"), dict) else {}
        obs = s.get("observation") if isinstance(s.get("observation"), dict) else {}
        tool = s.get("tool_name") or action.get("tool_name") or (s.get("tool") or {}).get("name")
        status = obs.get("status") or s.get("status") or (s.get("tool") or {}).get("status")
        if tool:
            usage.append({"tool_name": tool, "status": str(status or "").lower()})
    return usage


def build_experience_summary(days: int = 30, limit: int = 20) -> dict[str, Any]:
    """汇总最近 ``days`` 天的 Agent 使用经验。"""
    from deps import get_db

    days = max(1, min(int(days), 365))
    summary: dict[str, Any] = {
        "window_days": days,
        "total_runs": 0,
        "status_breakdown": {},
        "intent_breakdown": {},
        "tool_usage": {},
        "unused_tools": [],
        "slow_runs": [],
        "failed_queries": [],
    }

    try:
        db = get_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='agent_execution_log'"
            )
            if not cursor.fetchone():
                summary["note"] = "agent_execution_log 表不存在（尚无埋点数据）"
                return summary

            cursor.execute(
                "SELECT query, status, steps_json, total_duration_ms "
                "FROM agent_execution_log "
                "WHERE created_at >= NOW() - (? || ' days')::INTERVAL "
                "ORDER BY created_at DESC",
                (str(days),),
            )
            rows = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning(f"experience summary unavailable: {exc}")
        summary["note"] = f"汇总失败: {exc}"
        return summary

    tool_counter: dict[str, dict[str, int]] = {}
    for query, status, steps_json, duration_ms in rows:
        summary["total_runs"] += 1
        status = str(status or "unknown")
        summary["status_breakdown"][status] = summary["status_breakdown"].get(status, 0) + 1

        intent = classify_intent(query or "")
        summary["intent_breakdown"][intent] = summary["intent_breakdown"].get(intent, 0) + 1

        for u in _extract_tool_usage(steps_json):
            t = tool_counter.setdefault(u["tool_name"], {"calls": 0, "failures": 0})
            t["calls"] += 1
            if u["status"] not in ("", "success", "succeeded"):
                t["failures"] += 1

        dur = float(duration_ms or 0.0)
        if dur > 60_000 and len(summary["slow_runs"]) < limit:
            summary["slow_runs"].append({
                "query": (query or "")[:200],
                "duration_ms": round(dur),
                "status": status,
            })
        if status not in ("completed", "success") and len(summary["failed_queries"]) < limit:
            summary["failed_queries"].append({
                "query": (query or "")[:200],
                "status": status,
            })

    summary["tool_usage"] = {
        name: {
            "calls": t["calls"],
            "failures": t["failures"],
            "failure_rate_pct": round(t["failures"] / t["calls"] * 100, 1) if t["calls"] else 0.0,
        }
        for name, t in sorted(tool_counter.items(), key=lambda x: -x[1]["calls"])
    }
    summary["unused_tools"] = sorted(set(_KNOWN_TOOLS) - set(tool_counter.keys()))
    return summary
