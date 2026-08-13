"""数值引用溯源校验器（A1，2026-08-08）。

校验综合回答的数值可溯源性：回答中出现的数字必须能在工具结果中找到
（允许四舍五入/千分位/百分比换算差异）。无法溯源的数字记入 report
metadata，占比过高时追加风险标记。

背景：扩样本 A/B 中 G07 基线组在缺成本数据时编造精确 NPV（judge 判
grounding=1）——本模块是该教训的程序化护栏，与提示词层的"标注来源"
要求互补。启发式定位：宁可漏报（trivial 数字豁免），误报只降级不阻断。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# 匹配整数/小数/千分位（如 -1,234.5、103.32、26）
_NUMBER_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")

# 回答中豁免的琐碎数字（步数/个数/年份等），不参与溯源判定
_TRIVIAL_INT_MAX = 20
_YEAR_RANGE = (1990, 2110)

# 溯源匹配容差：绝对 0.51 或相对 1%（覆盖四舍五入到整数的情形）
_ABS_TOL = 0.51
_REL_TOL = 0.01


def _iter_numbers(value: Any) -> Set[float]:
    """递归收集 dict/list 中的数值（工具结果全量数字池）。"""
    found: Set[float] = set()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        found.add(float(value))
    elif isinstance(value, dict):
        for v in value.values():
            found |= _iter_numbers(v)
    elif isinstance(value, list):
        for v in value:
            found |= _iter_numbers(v)
    return found


def _collect_tool_numbers(tool_results: List[Any]) -> Set[float]:
    """所有成功工具结果中的数字池（含常见换算变体）。"""
    pool: Set[float] = set()
    for r in tool_results:
        status = getattr(r, "status", None)
        if getattr(status, "value", status) != "success":
            continue
        data = getattr(r, "data", None)
        if not isinstance(data, dict):
            continue
        nums = _iter_numbers(data)
        for n in nums:
            pool.add(n)
            pool.add(round(n))            # 四舍五入到整数
            pool.add(round(n, 1))         # 一位小数
            pool.add(round(n * 100, 4))   # 比例→百分比（0.2575→25.75）
    return pool


def _match(num: float, pool: Set[float]) -> bool:
    for base in pool:
        if num == base:
            return True
        if abs(num - base) <= max(_ABS_TOL, _REL_TOL * abs(base)):
            return True
    return False


def check_numeric_grounding(answer: str, tool_results: List[Any]) -> Dict[str, Any]:
    """检查回答中数字在工具结果中的可溯源性。

    Returns:
        {"checked": 参与判定的数字数, "grounded": 可溯源数,
         "ungrounded_ratio": 不可溯源占比, "ungrounded_samples": [...]}
        checked=0 时（无数值回答）ratio 为 0，不触发任何标记。
    """
    if not answer:
        return {"checked": 0, "grounded": 0, "ungrounded_ratio": 0.0,
                "ungrounded_samples": []}

    pool = _collect_tool_numbers(tool_results)

    candidates: List[float] = []
    for raw in _NUMBER_RE.findall(answer):
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        # 豁免：小整数（个数/步数）与年份
        if n == int(n) and abs(n) <= _TRIVIAL_INT_MAX:
            continue
        if _YEAR_RANGE[0] <= n <= _YEAR_RANGE[1] and n == int(n):
            continue
        candidates.append(n)

    if not candidates:
        return {"checked": 0, "grounded": 0, "ungrounded_ratio": 0.0,
                "ungrounded_samples": []}

    ungrounded = [n for n in candidates if not _match(n, pool)]
    return {
        "checked": len(candidates),
        "grounded": len(candidates) - len(ungrounded),
        "ungrounded_ratio": round(len(ungrounded) / len(candidates), 3),
        "ungrounded_samples": ungrounded[:10],
    }


# =============================================================================
# Repair Loop（Generate → Verify → Repair，2026-08-13）
# =============================================================================

# 与 orchestrator 风险标记同阈值：至少 4 个受检数字且超半数不可溯源
REPAIR_MIN_CHECKED = 4
REPAIR_RATIO_THRESHOLD = 0.5


def should_repair(check: Dict[str, Any],
                  min_checked: int = REPAIR_MIN_CHECKED,
                  ratio_threshold: float = REPAIR_RATIO_THRESHOLD) -> bool:
    """判断是否触发一次溯源修复重生成（确定性规则，无 LLM）。"""
    if not isinstance(check, dict):
        return False
    return (
        int(check.get("checked", 0)) >= min_checked
        and float(check.get("ungrounded_ratio", 0.0)) > ratio_threshold
    )


def build_repair_feedback(samples: List[float]) -> str:
    """构造修复指令：要求删除/替换不可溯源数字，禁止编造。"""
    sample_text = "、".join(str(s) for s in samples[:10])
    return (
        "【数值溯源修复要求】\n"
        f"上一版报告中的以下数字无法追溯到任何工具结果：{sample_text}。\n"
        "请重写报告：删除这些数字，或替换为工具结果中真实存在的数值"
        "（允许四舍五入与百分比换算）；严禁编造、估算或外推任何数值。\n"
        "保持原有结构与结论不变，只处理数字问题。"
    )
