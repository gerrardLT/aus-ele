"""电网规则与制度知识库服务（Rule Knowledge，2026-08-12）。

读取 data/knowledge/grid_rules.json（NEM/WEM 规则卡片 + 政策时间线），
为 Agent grid_knowledge_lookup 工具提供确定性关键词检索。

设计约束：
- 确定性检索（无向量/无 LLM）：query 分词后对 title/summary/key_points
  做包含匹配，按命中次数排序——宁可少返回，不做语义猜测
- 知识库缺失时返回空结果 + available=False，消费方如实报告缺失
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_KNOWLEDGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "knowledge",
    "grid_rules.json",
)

_cache: Optional[dict] = None


def _load_knowledge() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(f"grid_rules.json unavailable: {exc}")
        _cache = {}
    return _cache


def _rule_search_text(rule: dict) -> str:
    parts = [rule.get("title", ""), rule.get("summary", ""), rule.get("id", "")]
    parts.extend(rule.get("key_points", []) or [])
    parts.extend(rule.get("affected_value_streams", []) or [])
    return " ".join(str(p) for p in parts).lower()


def _tokenize(query: str) -> list[str]:
    """粗分词：英文按词、中文按连续片段整体参与匹配（包含式）。"""
    tokens = [t for t in re.split(r"[\s,，。;；:：()（）\?？]+", query.lower()) if t]
    return tokens


def search_rules(
    query: Optional[str] = None,
    *,
    market: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 5,
) -> dict[str, Any]:
    """按关键词/市场/类别检索规则卡片。

    query 为空且无过滤条件时返回全部卡片（截断到 limit）。
    """
    kb = _load_knowledge()
    rules = list(kb.get("rules", []) or [])
    if not rules:
        return {"available": False, "matches": [], "note": "规则知识库不可用"}

    if market:
        rules = [r for r in rules if r.get("market", "").upper() == market.upper()]
    if category:
        rules = [r for r in rules if r.get("category") == category]

    if query:
        tokens = _tokenize(query)
        scored: list[tuple[int, dict]] = []
        for rule in rules:
            text = _rule_search_text(rule)
            hits = sum(1 for t in tokens if t in text)
            if hits > 0:
                scored.append((hits, rule))
        scored.sort(key=lambda x: x[0], reverse=True)
        rules = [r for _, r in scored]

    matches = rules[: max(1, int(limit))]
    return {
        "available": True,
        "total_after_filter": len(rules),
        "matches": matches,
        "citation_note": "引用规则时请附 source_url 与 effective_date；confidence=medium 的条目需提示以官方最新口径为准",
    }


def get_rule(rule_id: str) -> Optional[dict]:
    for rule in _load_knowledge().get("rules", []) or []:
        if rule.get("id") == rule_id:
            return rule
    return None


def get_timeline(limit: int = 20) -> list[dict]:
    timeline = list(_load_knowledge().get("timeline", []) or [])
    timeline.sort(key=lambda x: x.get("date", ""))
    return timeline[: max(1, int(limit))]
