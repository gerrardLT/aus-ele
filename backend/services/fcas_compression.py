"""FCAS revenue compression risk label（Phase 2，2026-08-12）。

把 FcasCollapseEngine 的供需比预测压缩成可挂到任意响应 payload 的
结构化风险标签，供 investment / revenue 路由与 Agent 工具复用。

市场事实锚点（2026 调研）：NEM BESS 收入中 FCAS 占比已降至约 3%
（同比 -43%），套利占约 97%——标签 note 中引用该事实提醒口径。

设计约束：
- best-effort：计算失败返回 available=False，绝不阻断主响应
- 模块级缓存 10 分钟（FCAS 崩塌预测是低频变化量）
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# 2026 调研事实（docs/research/调研-竞品动态与BESS收益基准-…-2026-08-12.md）
FCAS_SHARE_FACT_PCT = 3.0

_CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, dict]] = {}


def _classify(collapsed_count: int, at_risk_count: int, ceiling_k: float) -> str:
    if collapsed_count >= 3 or ceiling_k < 20.0:
        return "high"
    if collapsed_count > 0 or at_risk_count > 0:
        return "medium"
    return "low"


def get_fcas_compression_label(year: int = 2026) -> dict:
    """计算 FCAS 收益压缩风险标签（带 10 分钟缓存，失败降级）。"""
    now = time.time()
    cached = _cache.get("label")
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        from deps import get_db
        from engines.fcas_collapse_engine import FcasCollapseEngine

        fc = FcasCollapseEngine(get_db()).forecast(year=year).model_dump()
        services = fc.get("services", []) or []
        collapsed = sum(1 for s in services if s.get("classification") == "collapsed")
        at_risk = sum(1 for s in services if s.get("classification") == "at_risk")
        ceiling_k = (fc.get("total_fcas_ceiling_per_mw_year") or 0.0) / 1000.0
        label = {
            "available": True,
            "risk_label": "fcas_revenue_compression",
            "severity": _classify(collapsed, at_risk, ceiling_k),
            "collapsed_service_count": collapsed,
            "at_risk_service_count": at_risk,
            "max_realistic_fcas_revenue_k_per_mw_year": round(ceiling_k, 1),
            "fcas_share_of_bess_revenue_pct": FCAS_SHARE_FACT_PCT,
            "note": (
                "FCAS 收益持续压缩：当前 NEM BESS 收入中 FCAS 占比约 3%（同比 -43%），"
                "能量套利约占 97%。投资测算中的 FCAS 收益假设应显式下调并做敏感性检验。"
            ),
        }
    except Exception as exc:  # noqa: BLE001 — best-effort 降级
        logger.warning(f"FCAS compression label unavailable: {exc}")
        label = {"available": False, "risk_label": "fcas_revenue_compression"}

    _cache["label"] = (now, label)
    return label
