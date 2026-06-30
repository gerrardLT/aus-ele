"""Property 9（阶段状态归类）的属性测试。

被测纯函数：``deploy/scripts/lib/status.py`` 的 ``classify_stage``。

# Feature: cicd-pipeline, Property 9: 阶段状态归类 — For any 阶段执行结果 outcome，
# classify_stage(outcome) 恰好返回 成功/失败/跳过 三种取值之一，且该映射是确定的
# （相同 outcome 总得到相同分类）。
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# 使 ``deploy/scripts/lib`` 可被导入（lib 是带 __init__.py 的包）。
_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "deploy",
    "scripts",
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.status import SUCCESS, FAILURE, SKIPPED, classify_stage  # noqa: E402

# 三态取值集合：classify_stage 的返回值必须恰好落在此集合中。
_ALLOWED = {SUCCESS, FAILURE, SKIPPED}

# GitHub Actions job/step 的已知 outcome 取值及其期望分类。
# success -> 成功；skipped -> 跳过；failure/cancelled 及未知取值 -> 失败。
_KNOWN_EXPECTED = {
    "success": SUCCESS,
    "skipped": SKIPPED,
    "failure": FAILURE,
    "cancelled": FAILURE,
}


def _vary_case_and_space(draw, word: str) -> str:
    """对已知取值随机改变大小写并加首尾空白，验证「大小写不敏感、忽略空白」。"""
    cased = "".join(
        c.upper() if draw(st.booleans()) else c.lower() for c in word
    )
    lead = draw(st.sampled_from(["", " ", "\t", "  ", "\n", " \t "]))
    trail = draw(st.sampled_from(["", " ", "\t", "  ", "\n", " \t "]))
    return lead + cased + trail


@st.composite
def _outcomes(draw):
    """生成 (outcome, expected)。

    - 一半概率从已知取值（success/failure/cancelled/skipped）中选取，并随机
      变换大小写与首尾空白，期望分类按 _KNOWN_EXPECTED 推导。
    - 另一半概率生成任意字符串；其规范化后若恰好命中已知映射则按映射，否则
      归为「失败」（Fail-Fast，未知取值统一失败）。
    """
    if draw(st.booleans()):
        word = draw(st.sampled_from(list(_KNOWN_EXPECTED)))
        outcome = _vary_case_and_space(draw, word)
        normalized = word  # 变换前的规范取值
        expected = _KNOWN_EXPECTED[normalized]
        return outcome, expected

    outcome = draw(st.text())
    normalized = outcome.strip().lower()
    expected = _KNOWN_EXPECTED.get(normalized, FAILURE)
    return outcome, expected


@settings(max_examples=100)
@given(_outcomes())
def test_classify_stage_property_9(case):
    outcome, expected = case

    result = classify_stage(outcome)

    # 1) 恰好返回三态之一。
    assert result in _ALLOWED

    # 2) 映射确定：相同 outcome 多次调用得到相同分类。
    assert classify_stage(outcome) == result

    # 3) 已知映射成立（含任意字符串规范化后命中已知取值的情况）。
    assert result == expected
