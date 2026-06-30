"""阶段状态归类的纯函数。

本模块将 GitHub Actions Job/Step 的执行结果（result/outcome）确定性地归类为
``成功 / 失败 / 跳过`` 三态之一，供各 Job 末尾向 ``$GITHUB_STEP_SUMMARY``
写入阶段状态时复用（design.md "可观测性（R9）"）。

设计参见 design.md 的 Correctness Property 9 "阶段状态归类"。
"""

from __future__ import annotations

from typing import Final

# 三态归类结果常量（对应 R9.2 的「成功 / 失败 / 跳过」三种取值）。
SUCCESS: Final[str] = "成功"
FAILURE: Final[str] = "失败"
SKIPPED: Final[str] = "跳过"

# outcome 字符串到三态的显式映射。
# 取值对应 GitHub Actions job/step 的 result/outcome 概念：
# - "success"             → 成功
# - "skipped"             → 跳过
# - "failure"/"cancelled" → 失败
# 其余未知取值统一归为「失败」（遵循 Fail-Fast，见下方 classify_stage）。
_SUCCESS_OUTCOMES: Final[frozenset[str]] = frozenset({"success"})
_SKIPPED_OUTCOMES: Final[frozenset[str]] = frozenset({"skipped"})


def classify_stage(outcome: str) -> str:
    """将阶段执行结果 ``outcome`` 确定性地归类为三态之一。

    语义（对应 design.md Correctness Property 9 "阶段状态归类"）：

    - 恰好返回 ``成功 / 失败 / 跳过`` 三种取值之一。
    - 映射是确定的：相同 ``outcome`` 总得到相同分类。

    映射规则（``outcome`` 对应 GitHub Actions job 的 result/outcome 概念）：

    - ``success``           → ``成功``
    - ``skipped``           → ``跳过``
    - ``failure``/``cancelled`` 等其余取值 → ``失败``
    - 未知/无法识别的取值    → ``失败``（遵循 Fail-Fast：宁可报失败也不漏报问题）

    对输入做稳健处理：大小写不敏感，并忽略首尾空白。

    Args:
        outcome: 阶段执行结果字符串，典型取值为 ``success``、``failure``、
            ``cancelled``、``skipped`` 等。

    Returns:
        三态之一：``成功``、``失败`` 或 ``跳过``。
    """
    normalized = outcome.strip().lower()
    if normalized in _SUCCESS_OUTCOMES:
        return SUCCESS
    if normalized in _SKIPPED_OUTCOMES:
        return SKIPPED
    # failure、cancelled 及一切未知取值统一归为失败（Fail-Fast）。
    return FAILURE
