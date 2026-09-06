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
# 容器内无 docs/（Dockerfile 只拷 backend/scrapers），校准日期另存 data 层
# 镜像内可读；两处均需同步更新（运营节奏清单 §2）
_CALIBRATION_STATE = os.path.join(_KNOWLEDGE_DIR, "benchmark_calibration.json")
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
    """解析最新校准日期：优先方法论文档 §6 校准表，回退 data 层状态文件。

    回退原因：生产容器不包含 docs/（Dockerfile 只拷 backend/scrapers），
    data/knowledge/benchmark_calibration.json 是容器内可读的镜像源。
    """
    candidates: list[date] = []
    try:
        with open(_METHODOLOGY_DOC, "r", encoding="utf-8") as f:
            text = f.read()
        section = text.split("校准记录表", 1)
        scope = section[1] if len(section) > 1 else text
        candidates.extend(
            d for d in (_parse_date(m) for m in re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|", scope)) if d
        )
    except FileNotFoundError:
        pass

    state = _load_json(_CALIBRATION_STATE)
    state_date = _parse_date(state.get("last_calibration"))
    if state_date is not None:
        candidates.append(state_date)

    return max(candidates) if candidates else None


def check_benchmark_calibration(today: date) -> dict:
    last = _latest_calibration_date()
    if last is None:
        return _item("benchmark_calibration", "benchmark 月度校准", "月度", "overdue",
                     "方法论文档 §6 与 benchmark_calibration.json 均未解析到校准记录",
                     sop_section="§2")
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


def check_domain_data_schemas() -> dict:
    """手工领域 JSON 的结构校验（R6.6，2026-09-06）。

    诊断 §4.4：5 份手工 JSON 无 schema 校验，填错会静默污染下游分析。
    status 映射：error → overdue（healthy=False，强制人看）；warning → due_soon
    （证据缺失级别，需关注但不阻断）；校验层自身不可用 → overdue（审查 #2：
    其余检查项都经 _load_json 做 best-effort，本项不能因为 import/调用报错把
    整份报告从「部分降级」带成「完全不可用」）。
    """
    try:
        from services.domain_data_validation import validate_all

        result = validate_all()
    except Exception as exc:  # noqa: BLE001 —— 兜底所有失败模式，降级为 overdue
        logger.warning(f"knowledge health: domain data validation unavailable: {exc}")
        return _item(
            "domain_data_schema", "手工领域 JSON 结构校验", "随更新+周检",
            "overdue", f"校验层不可用：{exc}（需人工排查 services.domain_data_validation）",
            sop_section="§6",
        )
    broken = {name: r for name, r in result.items() if r["errors"]}
    warned = [name for name, r in result.items() if r["warnings"]]
    if broken:
        detail = f"{len(broken)} 份文件校验失败：{', '.join(sorted(broken))}；详见 services.domain_data_validation.validate_all()"
        return _item("domain_data_schema", "手工领域 JSON 结构校验", "随更新+周检",
                     "overdue", detail, sop_section="§6")
    file_count = len(result)  # 份数跟随 VALIDATORS 注册数，不写字面量（审查 #6）
    if warned:
        return _item("domain_data_schema", "手工领域 JSON 结构校验", "随更新+周检",
                     "due_soon", f"{file_count} 份全部通过，但有 warnings：{', '.join(sorted(warned))}（证据缺失级别）",
                     sop_section="§6")
    total_warnings = sum(len(r["warnings"]) for r in result.values())
    return _item("domain_data_schema", "手工领域 JSON 结构校验", "随更新+周检",
                 "ok", f"{file_count} 份手工 JSON 全部通过结构校验（{total_warnings} warnings）",
                 sop_section="§6")


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
    # R6.6：手工领域 JSON 的结构校验 —— 5 份无 schema 的手工文件是静默污染源
    items.append(check_domain_data_schemas())

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
