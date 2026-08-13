"""市场事件案例库服务（Event Case Library，2026-08-13）。

读取 data/knowledge/market_events.json——重大事件因果卡片（事件 → 影响 →
教训），为 Agent market_event_lookup 工具提供确定性检索，支撑归因叙事与
"历史相似情景"引用。

设计约束：与 grid_knowledge 同模式——确定性关键词检索，宁可少返回。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "knowledge",
    "market_events.json",
)

_cache: Optional[dict] = None


def _load_events_kb() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_EVENTS_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(f"market_events.json unavailable: {exc}")
        _cache = {}
    return _cache


def _event_search_text(event: dict) -> str:
    parts = [
        event.get("title", ""),
        event.get("summary", ""),
        event.get("id", ""),
        event.get("category", ""),
    ]
    parts.extend(event.get("lessons", []) or [])
    impact = event.get("impact", {}) or {}
    parts.extend(str(v) for v in impact.values())
    return " ".join(parts).lower()


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"[\s,，。;；:：()（）\?？~～]+", query.lower()) if t]


def search_events(
    query: Optional[str] = None,
    *,
    market: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 5,
) -> dict[str, Any]:
    """按关键词/市场/类别检索事件案例卡片。"""
    kb = _load_events_kb()
    events = list(kb.get("events", []) or [])
    if not events:
        return {"available": False, "matches": [], "note": "事件案例库不可用"}

    if market:
        events = [e for e in events if e.get("market", "").upper() == market.upper()]
    if category:
        events = [e for e in events if e.get("category") == category]

    if query:
        tokens = _tokenize(query)
        scored: list[tuple[int, dict]] = []
        for event in events:
            text = _event_search_text(event)
            hits = sum(1 for t in tokens if t in text)
            if hits > 0:
                scored.append((hits, event))
        scored.sort(key=lambda x: x[0], reverse=True)
        events = [e for _, e in scored]

    return {
        "available": True,
        "total_after_filter": len(events),
        "matches": events[: max(1, int(limit))],
        "citation_note": "引用事件案例时请附 period 与 source_url；教训（lessons）为经验总结，不构成预测承诺",
    }


def get_event(event_id: str) -> Optional[dict]:
    for event in _load_events_kb().get("events", []) or []:
        if event.get("id") == event_id:
            return event
    return None
