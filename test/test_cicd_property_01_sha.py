"""属性测试：Property 1 — Commit SHA 标签校验。

被测纯函数位于 ``deploy/scripts/lib/validate.py``：

- ``is_valid_sha(s)``：当且仅当 ``s`` 恰为 40 位小写十六进制字符时返回真。
- ``build_image_tag(...)``：对任意合法 SHA 生成的不可变镜像标签都完整包含
  该 40 位 SHA。

设计参见 cicd-pipeline/design.md 的 Correctness Properties → Property 1。
"""

from __future__ import annotations

import os
import string
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# 将 deploy/scripts 加入 sys.path，使 `from lib.validate import ...` 可解析。
# 本测试文件位于 <repo>/test/，lib 包位于 <repo>/deploy/scripts/lib/。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "deploy", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.validate import build_image_tag, is_valid_sha  # noqa: E402

# 合法 SHA：恰 40 位小写十六进制字符。
_HEX_LOWER = "0123456789abcdef"
valid_sha = st.text(alphabet=_HEX_LOWER, min_size=40, max_size=40)


def _is_canonical_sha(s: str) -> bool:
    """独立于被测正则的参考实现，用于断言 iff 关系。"""
    return len(s) == 40 and all(c in _HEX_LOWER for c in s)


# 任意字符串生成器：混入十六进制字符、字母、数字、空白与符号，
# 覆盖错误长度、大写、非十六进制、含空白等无效情形。
arbitrary_string = st.one_of(
    st.text(),
    st.text(alphabet=string.hexdigits + string.ascii_uppercase),
    st.text(alphabet=_HEX_LOWER, min_size=0, max_size=80),
    st.text(alphabet=_HEX_LOWER + " \t\n", min_size=39, max_size=41),
)


# Feature: cicd-pipeline, Property 1: For any 字符串 s，is_valid_sha(s) 返回真
# 当且仅当 s 恰为 40 位小写十六进制字符；并且对任意合法 SHA，所生成的不可变
# 镜像标签都完整包含该 40 位 SHA。
@settings(max_examples=100)
@given(s=st.one_of(arbitrary_string, valid_sha))
def test_property_01_sha_validation_and_tag_contains_sha(s: str) -> None:
    # iff：is_valid_sha 为真 当且仅当 s 恰为 40 位小写十六进制字符。
    assert is_valid_sha(s) == _is_canonical_sha(s)

    # 对任意合法 SHA，build_image_tag 生成的标签完整包含该 40 位 SHA。
    if is_valid_sha(s):
        tag = build_image_tag("ghcr.io", "owner/repo", "backend", s)
        assert s in tag
        # 不可变标签以完整 40 位 SHA 结尾，确保按 SHA 寻址。
        assert tag.endswith(f":{s}")
