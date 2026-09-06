# -*- coding: utf-8 -*-
"""手工维护领域 JSON 的 schema 校验层（R6.6，2026-09-06）。

诊断 §4.4：data/ 下 5 份手工维护的 JSON 是无 schema 校验的隐性单点 —— 任何一个
填错（字段名拼错、类型不对、值域越界）都会静默污染下游分析结论：capacity_data 被
forward_price_engine / ml_calibration_engine / regional_timing_engine / agent 工具
直接读取，regional_fee_defaults 解析失败时 cost_structure_engine 会静默回退
hardcoded 默认值（运营的修改无声丢失），financial_evidence 直接进基准校验。

本模块只做检查与报告，不改行为、不做自动修复（与 knowledge_health 同一纪律）；
结果挂入 knowledge_health 健康报告（失败 → overdue → healthy=False）。

与假设登记的联动：regional_fee 的校验直接复用 pydantic 真源
models.cost_structure_models.RegionalFeeConfig（含 Field 值域），不另写第二份口径；
pydantic 默认 extra=ignore 会静默吞掉拼错的字段名，因此本模块额外用
model_fields 比对未知键 —— 改 ``rate_per_mwh`` 打成 ``rate_per_mwhs`` 在这里被抓，
而不是被静默回退成默认值。

为什么不用 jsonschema 库：5 份文件的「schema」本质是消费方的字段访问路径，手写
检查函数可以直接对齐消费点真实读取的字段，且零新依赖。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any, Optional, get_args

from models.capacity_models import CapacityProject

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DATA_DIR = os.path.join(_ROOT, "data")

# NEM/WEM 区域白名单（与 cost_structure_engine 的 hardcoded 六区域一致；
# capacity_data 现值确认 2026-09-06：{NSW1, QLD1, SA1, TAS1, VIC1, WEM}）
REGION_WHITELIST = {"NSW1", "QLD1", "SA1", "TAS1", "VIC1", "WEM"}
# capacity_data projects[].status 白名单：从 pydantic 真源 CapacityProject 的
# Literal 派生，不另写第二份口径（R6.6 审查 #3，2026-09-06）。
# 消费方红门（regional_timing_engine 只分桶 committed/construction/planning，
# registered 待确认）由测试层锁住：Literal 加新值 → 白名单自动跟随 → 锁测试红
# → 强制先确认消费方再同步更新锁测试期望值。
PROJECT_STATUS_WHITELIST = set(get_args(CapacityProject.model_fields["status"].annotation))


def _parse_iso_date(value: Any) -> Optional[date]:
    """对齐 knowledge_health._parse_date 的宽容语义（ISO 前 10 位）。"""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _new_report(item_count: int = 0) -> dict:
    return {"ok": True, "errors": [], "warnings": [], "item_count": item_count}


def _err(report: dict, msg: str) -> None:
    report["ok"] = False
    report["errors"].append(msg)


def _warn(report: dict, msg: str) -> None:
    report["warnings"].append(msg)


def _check_updated_date(report: dict, meta: Any, field: str = "last_updated") -> None:
    """meta 里的日期字段必须可解析 —— knowledge_health 的时效判定直接消费它。"""
    if not isinstance(meta, dict):
        _err(report, f"metadata 缺失或不是对象，无法读取 {field}")
        return
    raw = meta.get(field)
    if _parse_iso_date(raw) is None:
        _err(report, f"metadata.{field} 不可解析为 ISO 日期：{raw!r}")


# ---------------------------------------------------------------------------
# Per-file validators（data: 已反序列化的 JSON 顶层对象）
# ---------------------------------------------------------------------------


def validate_capacity_data(data: Any) -> dict:
    """消费方：pipeline_knowledge / forward_price_engine / ml_calibration_engine /
    regional_timing_engine / agent.tools / knowledge_health。"""
    report = _new_report()
    if not isinstance(data, dict):
        _err(report, "顶层不是 JSON 对象")
        return report
    _check_updated_date(report, data.get("metadata"))

    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        _err(report, "projects 缺失或为空（28 个项目档案是管线库的主体）")
        projects = []
    for i, p in enumerate(projects):
        if not isinstance(p, dict):
            _err(report, f"projects[{i}] 不是对象")
            continue
        where = f"projects[{i}]({p.get('project_name', '?')})"
        if not str(p.get("project_name") or "").strip():
            _err(report, f"{where}: project_name 为空")
        if p.get("region") not in REGION_WHITELIST:
            _err(report, f"{where}: region {p.get('region')!r} 不在白名单 {sorted(REGION_WHITELIST)}")
        for num_field in ("capacity_mw", "duration_hours"):
            value = p.get(num_field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                _err(report, f"{where}: {num_field} 必须为正数，实际 {value!r}")
        if p.get("status") not in PROJECT_STATUS_WHITELIST:
            _err(report, f"{where}: status {p.get('status')!r} 不在白名单 {sorted(PROJECT_STATUS_WHITELIST)}")

    interconnectors = data.get("interconnectors")
    if not isinstance(interconnectors, list):
        _err(report, "interconnectors 缺失或不是数组")
        interconnectors = []
    for i, ic in enumerate(interconnectors):
        if not isinstance(ic, dict):
            _err(report, f"interconnectors[{i}] 不是对象")
            continue
        where = f"interconnectors[{i}]({ic.get('name', '?')})"
        for txt_field in ("name", "from_region", "to_region"):
            if not str(ic.get(txt_field) or "").strip():
                _err(report, f"{where}: {txt_field} 为空")
        cap = ic.get("capacity_mw")
        if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap <= 0:
            _err(report, f"{where}: capacity_mw 必须为正数，实际 {cap!r}")
        factor = ic.get("convergence_factor")
        if not isinstance(factor, (int, float)) or isinstance(factor, bool) or not (0 < factor <= 1):
            _err(report, f"{where}: convergence_factor 必须在 (0, 1]，实际 {factor!r}")

    if 0 < len(projects) < 5:
        _warn(report, f"projects 仅 {len(projects)} 条，远少于常态（季度更新的档案库疑似被截断）")
    report["item_count"] = len(projects)
    return report


def validate_coal_retirement_schedule(data: Any) -> dict:
    """消费方：forward_price_engine（煤退役时点直接影响远期价格曲线）。"""
    report = _new_report()
    if not isinstance(data, dict):
        _err(report, "顶层不是 JSON 对象")
        return report
    _check_updated_date(report, data.get("metadata"))

    retirements = data.get("retirements")
    if not isinstance(retirements, list) or not retirements:
        _err(report, "retirements 缺失或为空")
        retirements = []
    for i, r in enumerate(retirements):
        if not isinstance(r, dict):
            _err(report, f"retirements[{i}] 不是对象")
            continue
        where = f"retirements[{i}]({r.get('plant_name', '?')})"
        for txt_field in ("plant_name", "region", "confidence"):
            if not str(r.get(txt_field) or "").strip():
                _err(report, f"{where}: {txt_field} 为空")
        if r.get("region") not in REGION_WHITELIST:
            _err(report, f"{where}: region {r.get('region')!r} 不在白名单 {sorted(REGION_WHITELIST)}")
        cap = r.get("capacity_mw")
        if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap <= 0:
            _err(report, f"{where}: capacity_mw 必须为正数，实际 {cap!r}")
        if _parse_iso_date(r.get("expected_closure_date")) is None:
            _err(report, f"{where}: expected_closure_date 不可解析为 ISO 日期：{r.get('expected_closure_date')!r}")
    report["item_count"] = len(retirements)
    return report


def validate_regional_fee_defaults(data: Any) -> dict:
    """消费方：cost_structure_engine（解析失败会静默回退 hardcoded 默认 ——
    运营改的费率无声丢失，因此这里的校验比别处更严格）。"""
    report = _new_report()
    if not isinstance(data, dict):
        _err(report, "顶层不是 JSON 对象")
        return report

    from models.cost_structure_models import RegionalFeeConfig

    regions = {k: v for k, v in data.items() if not k.startswith("_")}
    missing = REGION_WHITELIST - set(regions)
    if missing:
        _err(report, f"缺少区域配置：{sorted(missing)}（cost_structure_engine 将对其回退 hardcoded 值）")
    known = RegionalFeeConfig.model_fields.keys()  # 循环不变量，不在内层重复求值（审查 #7）
    for key, value in regions.items():
        if not isinstance(value, dict):
            _err(report, f"{key}: 区域配置不是对象")
            continue
        if value.get("region") != key:
            _err(report, f"{key}: region 字段({value.get('region')!r})与键名不一致")
        # pydantic 真源校验（含全部 Field 值域，如 mlf ∈ [0.50, 1.50]）
        try:
            RegionalFeeConfig(**value)
        except Exception as exc:
            _err(report, f"{key}: 不满足 RegionalFeeConfig 契约：{exc}")
        # pydantic 默认 extra=ignore 会静默吞掉拼错的字段名 —— 手动比对已知键集
        for sub_name, sub in value.items():
            if sub_name not in known:
                _err(report, f"{key}.{sub_name}: 未知字段（known={sorted(known)}；拼错的字段会被静默忽略并用默认值）")
                continue
            if isinstance(sub, dict):
                field_model = RegionalFeeConfig.model_fields[sub_name]
                sub_model = field_model.annotation
                sub_keys = getattr(sub_model, "model_fields", None)
                if sub_keys is not None:
                    for k in sub:
                        if k not in sub_keys:
                            _err(report, f"{key}.{sub_name}.{k}: 未知字段（拼错的字段会被静默忽略并用默认值）")
    report["item_count"] = len(regions)
    return report


def validate_contract_revenue_defaults(data: Any) -> dict:
    """消费方：services/contract_revenue.py（CIS 与 WEM BRCP 合约收入默认值）。"""
    report = _new_report()
    if not isinstance(data, dict):
        _err(report, "顶层不是 JSON 对象")
        return report
    _check_updated_date(report, data.get("meta"), field="updated_at")
    for section in ("cis", "wem_brcp"):
        value = data.get(section)
        if not isinstance(value, dict) or not value:
            _err(report, f"{section} 缺失或为空（合约收入基准不完整）")
    report["item_count"] = len([k for k in data if not k.startswith("_")])
    return report


def validate_financial_evidence(data: Any) -> dict:
    """消费方：forward_price_engine 基准校验 / agent.tools。证据点为空只降级为
    warning：证据缺失是「可信度问题」不是「会算错」的问题。"""
    report = _new_report()
    if not isinstance(data, dict):
        _err(report, "顶层不是 JSON 对象")
        return report
    _check_updated_date(report, data.get("metadata"))
    for section in ("cost_structure_evidence", "forward_price_evidence"):
        block = data.get(section)
        if not isinstance(block, dict):
            _err(report, f"{section} 缺失或不是对象")
            continue
        points = block.get("evidence_points")
        if not isinstance(points, list):
            _err(report, f"{section}.evidence_points 缺失或不是数组")
        elif not points:
            _warn(report, f"{section}.evidence_points 为空 —— 该维度的财务结论暂无证据支撑")
    report["item_count"] = len([k for k in data if not k.startswith("_")])
    return report


# 文件名 → 校验器（顺序即报告顺序）
VALIDATORS: dict[str, Any] = {
    "capacity_data.json": validate_capacity_data,
    "coal_retirement_schedule.json": validate_coal_retirement_schedule,
    "regional_fee_defaults.json": validate_regional_fee_defaults,
    "contract_revenue_defaults.json": validate_contract_revenue_defaults,
    "financial_evidence.json": validate_financial_evidence,
}


def validate_all(data_dir: Optional[str] = None) -> dict[str, dict]:
    """校验全部手工领域 JSON。每份文件独立 best-effort：一份不可读不影响其余。

    返回 ``{file: {"ok": bool, "errors": [str], "warnings": [str], "item_count": int}}``。
    """
    base = data_dir or _DEFAULT_DATA_DIR
    result: dict[str, dict] = {}
    for name, validator in VALIDATORS.items():
        path = os.path.join(base, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            result[name] = {
                "ok": False, "errors": [f"文件不存在：{path}"], "warnings": [], "item_count": 0,
            }
            continue
        except json.JSONDecodeError as exc:
            result[name] = {
                "ok": False, "errors": [f"JSON 不可解析：{exc}"], "warnings": [], "item_count": 0,
            }
            continue
        except (UnicodeDecodeError, ValueError) as exc:
            # 非 UTF-8 文件（如中文 Windows 下误存 GBK/UTF-16）在 json.load 读取时
            # 抛 UnicodeDecodeError —— 它继承 ValueError 而非 OSError，不在此前三分支
            # 内会直接逃逸击穿「逐份 best-effort」契约，整份健康报告不可用（审查 #1）。
            # json.JSONDecodeError 也是 ValueError 子类，故本分支必须排在它之后。
            result[name] = {
                "ok": False, "errors": [f"文件编码/解析异常：{exc}"], "warnings": [], "item_count": 0,
            }
            continue
        except OSError as exc:
            result[name] = {
                "ok": False, "errors": [f"文件不可读：{exc}"], "warnings": [], "item_count": 0,
            }
            continue
        try:
            result[name] = validator(data)
        except Exception as exc:  # 校验器自身异常不吞掉整份报告
            logger.exception("domain data validator crashed: %s", name)
            result[name] = {
                "ok": False, "errors": [f"校验器内部异常：{exc}"], "warnings": [], "item_count": 0,
            }
    return result
