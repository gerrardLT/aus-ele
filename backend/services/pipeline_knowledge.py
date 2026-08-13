"""资产与管线知识库服务（Pipeline Knowledge，2026-08-13）。

数据基础：``data/capacity_data.json``（项目级档案：区域/容量/时长/技术/状态/
并网时间/业主）+ ``market_pipeline_anchors``（市场级管线锚点，AEMO 季度口径）。

消费方：saturation_check / cannibalization_forecast / fcas_collapse（供给端输入）、
Agent 工具 asset_pipeline_lookup。

更新节奏（AGENTS.md 规划 §2.5）：AEMO 季度管线报告发布后人工更新，
每次更新必须刷新 metadata.last_updated 与 notes。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "capacity_data.json",
)

# 纳入"活跃供给"的状态（与 fcas_collapse_engine 口径一致；planning 不计入）
ACTIVE_STATUSES = ("registered", "committed", "construction")

_STALE_AFTER_DAYS = 120  # 数据超过 120 天未更新视为陈旧，提示走季度更新流程

_cache: Optional[dict] = None


def _load_capacity_data() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(f"capacity_data.json unavailable: {exc}")
        _cache = {}
    return _cache


def _freshness() -> dict[str, Any]:
    meta = _load_capacity_data().get("metadata", {}) or {}
    last_updated = meta.get("last_updated")
    info: dict[str, Any] = {
        "last_updated": last_updated,
        "source": meta.get("source"),
        "version": meta.get("version"),
    }
    if last_updated:
        try:
            dt = datetime.fromisoformat(str(last_updated))
            age_days = (datetime.now(dt.tzinfo) - dt).days if dt.tzinfo else (date.today() - dt.date()).days
            info["age_days"] = age_days
            info["stale"] = age_days > _STALE_AFTER_DAYS
        except ValueError:
            info["stale"] = None
    return info


def summarize_pipeline(region: Optional[str] = None) -> dict[str, Any]:
    """按状态聚合管线容量（BESS 口径，排除 Pumped Hydro）。"""
    data = _load_capacity_data()
    projects = data.get("projects", []) or []
    if not projects:
        return {"available": False, "note": "capacity_data.json 不可用"}

    if region:
        projects = [p for p in projects if p.get("region") == region.upper()]

    by_status: dict[str, dict[str, float]] = {}
    for p in projects:
        tech = str(p.get("technology", ""))
        if "Pumped Hydro" in tech:
            continue
        st = str(p.get("status", "unknown"))
        bucket = by_status.setdefault(st, {"count": 0, "capacity_mw": 0.0, "energy_mwh": 0.0})
        bucket["count"] += 1
        bucket["capacity_mw"] += float(p.get("capacity_mw") or 0.0)
        bucket["energy_mwh"] += float(p.get("energy_mwh") or 0.0)

    active_mw = sum(
        b["capacity_mw"] for st, b in by_status.items() if st in ACTIVE_STATUSES
    )
    return {
        "available": True,
        "region": region.upper() if region else "ALL",
        "by_status": {
            st: {
                "count": int(b["count"]),
                "capacity_mw": round(b["capacity_mw"], 1),
                "energy_mwh": round(b["energy_mwh"], 1),
            }
            for st, b in by_status.items()
        },
        "active_supply_mw": round(active_mw, 1),
        "active_statuses": list(ACTIVE_STATUSES),
        "market_pipeline_anchors": _load_capacity_data().get("market_pipeline_anchors"),
        "freshness": _freshness(),
        "caveat": (
            "项目档案为人工维护样本（非全量管线）；市场总量以 market_pipeline_anchors "
            "官方口径为准，两者不可混用"
        ),
    }


def search_projects(
    *,
    region: Optional[str] = None,
    status: Optional[str] = None,
    name_contains: Optional[str] = None,
    limit: int = 20,
) -> dict[str, Any]:
    """项目级检索（名称/区域/状态过滤）。"""
    data = _load_capacity_data()
    projects = list(data.get("projects", []) or [])
    if not projects:
        return {"available": False, "matches": [], "note": "capacity_data.json 不可用"}

    if region:
        projects = [p for p in projects if p.get("region") == region.upper()]
    if status:
        projects = [p for p in projects if p.get("status") == status]
    if name_contains:
        kw = name_contains.lower()
        projects = [p for p in projects if kw in str(p.get("project_name", "")).lower()]

    return {
        "available": True,
        "total_after_filter": len(projects),
        "matches": projects[: max(1, int(limit))],
        "freshness": _freshness(),
    }
