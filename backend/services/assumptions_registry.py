"""参数与假设登记库服务（Assumptions Registry，2026-08-12）。

读取 data/assumptions_registry.json——系统内关键假设的统一登记与审计入口。

设计约束：
- 登记表缺失/损坏时静默降级：消费方使用各自的代码默认值，绝不阻断
- 模块级缓存（文件低频变化；进程内改登记表需重启，符合"参数变更走评审"的纪律）

参考：docs/strategy/知识库缺口与资料沉淀规划.md §2.2
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "assumptions_registry.json",
)

_cache: Optional[dict] = None


def _load_registry() -> dict:
    """加载登记表（带缓存，失败返回空结构）。"""
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(f"assumptions_registry.json unavailable: {exc}")
        _cache = {}
    return _cache


def get_assumption(assumption_id: str) -> Optional[dict]:
    """按 id 返回完整登记条目（含来源/依据/边界），未登记返回 None。"""
    registry = _load_registry()
    for item in registry.get("assumptions", []) or []:
        if item.get("id") == assumption_id:
            return item
    return None


def get_assumption_value(assumption_id: str, *, default: Any = None) -> Any:
    """按 id 返回登记的 value 字段；缺失或登记表不可用时返回 default。

    消费方必须传入与代码默认值一致的 default，保证登记表故障时行为不变。
    """
    item = get_assumption(assumption_id)
    if item is None or "value" not in item:
        return default
    return item["value"]


def list_assumptions() -> list[dict]:
    """返回全部登记条目（审计/展示用）。"""
    return list(_load_registry().get("assumptions", []) or [])
