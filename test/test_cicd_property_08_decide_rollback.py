"""属性测试：Property 8 — 回滚目标决策。

被测纯函数位于 ``deploy/scripts/lib/stable_tag.py``：

- ``decide_rollback(last_stable)``：当且仅当 ``last_stable`` 为合法的 40 位
  小写十六进制 commit SHA 时返回真（执行回滚）；否则返回假（跳过并以失败收场）。

设计参见 cicd-pipeline/design.md 的 Correctness Properties → Property 8 与 R7.3。
"""

from __future__ import annotations

import os
import string
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# 将 deploy/scripts 加入 sys.path，使 `from lib.stable_tag import ...` 可解析。
# 本测试文件位于 <repo>/test/，lib 包位于 <repo>/deploy/scripts/lib/。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "deploy", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.stable_tag import decide_rollback  # noqa: E402
from lib.validate import is_valid_sha  # noqa: E402

# 合法 SHA：恰 40 位小写十六进制字符。
_HEX_LOWER = "0123456789abcdef"
_valid_sha = st.text(alphabet=_HEX_LOWER, min_size=40, max_size=40)

# 非法字符串：覆盖错误长度、大写、非十六进制、含空白等无效情形。
_invalid_string = st.one_of(
    st.text(),  # 任意文本，绝大多数非合法 SHA
    st.text(alphabet=string.hexdigits + string.ascii_uppercase),  # 含大写/混合
    st.text(alphabet=_HEX_LOWER, min_size=0, max_size=80),  # 长度错误（含 != 40）
    st.text(alphabet=_HEX_LOWER + " \t\n", min_size=39, max_size=41),  # 含空白/边界长度
)

# 空/纯空白字符串：状态文件存在但内容为空的边界场景。
_empty_or_whitespace = st.sampled_from(["", " ", "   ", "\t", "\n", "  \t\n "])

# Last_Stable_Tag 状态空间：
# - None：状态文件不存在（首次部署，无可回滚版本）；
# - 空/空白串；
# - 非法字符串；
# - 合法 40 位小写十六进制 SHA。
_last_stable = st.one_of(
    st.none(),
    _empty_or_whitespace,
    _invalid_string,
    _valid_sha,
)


# Feature: cicd-pipeline, Property 8: 回滚目标决策 — For any Last_Stable_Tag 状态
# （不存在/为空/为合法 SHA），decide_rollback(last_stable) 决定执行回滚当且仅当
# 存在合法的 Last_Stable_Tag；否则决定跳过并以失败收场。
# Validates: Requirements 7.3
@settings(max_examples=100)
@given(last_stable=_last_stable)
def test_property_08_decide_rollback(last_stable) -> None:
    result = decide_rollback(last_stable)

    # iff：决定执行回滚 当且仅当 last_stable 为合法的 40 位小写十六进制 SHA。
    # None 由 is_valid_sha 安全处理为非法（返回 False）。
    expected = is_valid_sha(last_stable) if last_stable is not None else False

    assert result == expected
    # 结果必为布尔值（执行回滚 / 跳过并以失败收场）。
    assert isinstance(result, bool)
