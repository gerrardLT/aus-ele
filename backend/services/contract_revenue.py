"""合约型收益锚点服务：CIS floor 与 WEM BRCP（Phase 3，2026-08-12）。

数据来源为 data/contract_revenue_defaults.json（人工维护，不建爬虫）。
所有输出一律带 caveat：配置值为示例锚点，正式投标/容量年以官方结果为准。
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "contract_revenue_defaults.json",
)

_CIS_CAVEAT = (
    "CIS floor 为配置示例锚点（人工维护），实际中标 floor 以 CIS 投标结果为准；"
    "仅反映收入下限兜底，不含上行收益与投标竞争不确定性。"
)
_BRCP_CAVEAT = (
    "BRCP 为 ERA 官方口径的年度锚点（200MW/1200MWh 电池基准，人工年度更新）；"
    "容量收益还需折算认证容量信用（STEM 折减），不可直接当全额收入。"
)


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(f"contract_revenue_defaults.json unavailable: {exc}")
        return {}


def get_cis_floor_params(region: str) -> dict:
    """返回指定区域的 CIS floor 参数（区域覆盖 > 默认值）。"""
    cfg = _load_config().get("cis", {})
    if not cfg:
        return {"available": False, "caveat": "CIS 配置缺失"}
    overrides = cfg.get("region_overrides", {}) or {}
    floor = overrides.get(region, cfg.get("default_floor_aud_per_mw_year"))
    return {
        "available": floor is not None,
        "scheme": cfg.get("scheme"),
        "floor_aud_per_mw_year": floor,
        "term_years": cfg.get("term_years"),
        "caveat": _CIS_CAVEAT,
    }


def get_wem_brcp_anchor(capacity_year: str = "2026/27") -> dict:
    """返回 WEM BRCP 年度锚点。"""
    cfg = _load_config().get("wem_brcp", {})
    years = cfg.get("capacity_years", {}) or {}
    entry = years.get(capacity_year)
    if not cfg or entry is None:
        return {"available": False, "caveat": "BRCP 配置缺失或未覆盖该容量年"}
    return {
        "available": True,
        "capacity_year": capacity_year,
        "brcp_aud_per_mw_year": entry.get("brcp_aud_per_mw_year"),
        "status": entry.get("status"),
        "reference_battery": cfg.get("reference_battery"),
        "caveat": _BRCP_CAVEAT,
    }
