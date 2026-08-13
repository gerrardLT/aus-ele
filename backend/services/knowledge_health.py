"""知识库健康检查服务（Knowledge Health，2026-08-13）。

把运营节奏清单（docs/deployment/运营节奏清单.md）的到期判定自动化：
每周体检全部知识库，输出 ok / due_soon / overdue / informational 状态。
只做检查与报告，不做自动修复（维护动作必须人审）。

数据源与阈值见任务规划 docs/tasks/任务规划-2026-08-13-知识库健康检查自动化.md。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_ROOT, "data")
_KNOWLEDGE_DIR = os.path.join(_DATA_DIR, "knowledge")
_METHODOLOGY_DOC = os.path.join(
    _ROOT, "docs", "architecture", "NEM-BESS收益基准方法论.md"
)
_SOP_REF = "docs/deployment/运营节奏清单.md"

# 阈值（天）
PIPELINE_DUE_SOON_DAYS = 90
PIPELINE_OVERDUE_DAYS = 120
RULE_DUE_SOON_DAYS = 30
CALIBRATION_DUE_SOON_DAYS = 28
CALIBRATION_OVERDUE_DAYS = 35
EVENTS_INFO_DAYS = 90


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(f"knowledge health: cannot load {path}: {exc}")
        return {}


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _age_days(past: date, today: date) -> int:
    return (today - past).days


def _item(
    item_id: str,
    name: str,
    cadence: str,
    status: str,
    detail: str,
    *,
    due_date: Optional[str] = None,
    sop_section: str = "",
) -> dict:
    return {
        "id": item_id,
        "name": name,
        "cadence": cadence,
        "status": status,
        "detail": detail,
        "due_date": due_date,
        "sop_ref": f"{_SOP_REF} {sop_section}".strip(),
    }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_pipeline_freshness(today: date) -> dict:
    meta = _load_json(os.path.join(_DATA_DIR, "capacity_data.json")).get("metadata", {}) or {}
    updated = _parse_date(meta.get("last_updated"))
    if updated is None:
        return _item("pipeline_freshness", "管线库季度更新", "季度", "overdue",
                     "capacity_data.json 缺少可解析的 last_updated", sop_section="§1")
    age = _age_days(updated, today)
    due = updated.fromordinal(updated.toordinal() + PIPELINE_OVERDUE_DAYS)
    if age > PIPELINE_OVERDUE_DAYS:
        status = "overdue"
    elif age > PIPELINE_DUE_SOON_DAYS:
        status = "due_soon"
    else:
        status = "ok"
    return _item("pipeline_freshness", "管线库季度更新", "季度", status,
                 f"last_updated={updated.isoformat()}，距今 {age} 天（阈值 {PIPELINE_OVERDUE_DAYS} 天）",
                 due_date=due.isoformat(), sop_section="§1")


def check_rule_reviews(today: date) -> list[dict]:
    rules = _load_json(os.path.join(_KNOWLEDGE_DIR, "grid_rules.json")).get("rules", []) or []
    items = []
    for rule in rules:
        review = _parse_date(rule.get("review_date"))
        if review is None:
            continue
        delta = (review - today).days
        rule_id = rule.get("id", "?")
        if delta < 0:
            status, detail = "overdue", f"复核期已过 {-delta} 天"
        elif delta <= RULE_DUE_SOON_DAYS:
            status, detail = "due_soon", f"{delta} 天后到期"
        else:
            status, detail = "ok", f"还有 {delta} 天"
        items.append(_item(
            f"rule_review:{rule_id}", f"规则卡片复核：{rule.get('title', rule_id)}",
            "季度+即时", status,
            f"review_date={review.isoformat()}，{detail}（confidence={rule.get('confidence', '?')}）",
            due_date=review.isoformat(), sop_section="§4",
        ))
    return items


def _latest_calibration_date() -> Optional[date]:
    """从方法论文档 §6 校准记录表解析最新校准日期（表格首列 YYYY-MM-DD）。"""
    try:
        with open(_METHODOLOGY_DOC, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    section = text.split("校准记录表", 1)
    scope = section[1] if len(section) > 1 else text
    dates = [
        _parse_date(m)
        for m in re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|", scope)
    ]
    valid = [d for d in dates if d is not None]
    return max(valid) if valid else None


def check_benchmark_calibration(today: date) -> dict:
    last = _latest_calibration_date()
    if last is None:
        return _item("benchmark_calibration", "benchmark 月度校准", "月度", "overdue",
                     "方法论文档 §6 未解析到任何校准记录", sop_section="§2")
    age = _age_days(last, today)
    due = date.fromordinal(last.toordinal() + CALIBRATION_OVERDUE_DAYS)
    if age > CALIBRATION_OVERDUE_DAYS:
        status = "overdue"
    elif age > CALIBRATION_DUE_SOON_DAYS:
        status = "due_soon"
    else:
        status = "ok"
    return _item("benchmark_calibration", "benchmark 月度校准", "月度", status,
                 f"最近校准 {last.isoformat()}，距今 {age} 天（阈值 {CALIBRATION_OVERDUE_DAYS} 天）",
                 due_date=due.isoformat(), sop_section="§2")


def check_events_library(today: date) -> dict:
    events = _load_json(os.path.join(_KNOWLEDGE_DIR, "market_events.json")).get("events", []) or []
    recorded = [_parse_date(e.get("recorded_at")) for e in events]
    valid = [d for d in recorded if d is not None]
    if not valid:
        return _item("events_library", "事件案例补录", "事件驱动", "informational",
                     "案例库为空（等待首个事件录入）", sop_section="§3")
    latest = max(valid)
    age = _age_days(latest, today)
    status = "informational"
    detail = f"最近补录 {latest.isoformat()}（{age} 天前），共 {len(events)} 案例"
    if age > EVENTS_INFO_DAYS:
        detail += f"——已超 {EVENTS_INFO_DAYS} 天无补录，建议检查近期是否有漏录的市场大事"
    return _item("events_library", "事件案例补录", "事件驱动", status, detail, sop_section="§3")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def build_health_report(today: Optional[date] = None) -> dict[str, Any]:
    """生成知识库健康报告（纯函数，best-effort）。"""
    today = today or date.today()
    items: list[dict] = []
    items.append(check_pipeline_freshness(today))
    items.extend(check_rule_reviews(today))
    items.append(check_benchmark_calibration(today))
    items.append(check_events_library(today))

    summary = {"overdue": 0, "due_soon": 0, "ok": 0, "informational": 0}
    for it in items:
        summary[it["status"]] = summary.get(it["status"], 0) + 1

    return {
        "generated_at": today.isoformat(),
        "summary": summary,
        "healthy": summary["overdue"] == 0,
        "items": items,
        "action_note": "逾期/临期项按 sop_ref 指向的运营节奏清单章节人工执行，系统不自动修复",
    }
