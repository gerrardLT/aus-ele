"""属性测试：Property 2 — 不可变标签覆盖保护。

被测纯函数位于 ``deploy/scripts/lib/smoke.py``：

- ``decide_push(existing, tag)``：当且仅当目标标签 ``tag`` 不在已存在标签集合
  ``existing`` 中时允许推送（返回 ``True``）；只要 ``tag`` 已存在，便一律拒绝
  推送（返回 ``False``），以避免覆盖既有不可变镜像标签。

设计参见 cicd-pipeline/design.md 的 Correctness Properties → Property 2。
对应需求 R3.6（不可变标签覆盖保护）。
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# 将 deploy/scripts 加入 sys.path，使 `from lib.smoke import ...` 可解析。
# 本测试文件位于 <repo>/test/，lib 包位于 <repo>/deploy/scripts/lib/。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "deploy", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.smoke import decide_push  # noqa: E402

# ---------------------------------------------------------------------------
# 生成器：构造类 SHA 标签与任意字符串标签，覆盖「允许推送」与「拒绝覆盖」两类场景。
# ---------------------------------------------------------------------------

# 类 commit SHA 标签：40 位十六进制；同时混入任意短字符串以扩大输入空间。
_sha_like = st.text(alphabet="0123456789abcdef", min_size=7, max_size=40)
_arbitrary = st.text(max_size=12)
_tag_strategy = st.one_of(_sha_like, _arbitrary)

# 已存在标签集合：list 或 set 形式，元素来自相同标签空间。
_existing_strategy = st.one_of(
    st.lists(_tag_strategy, max_size=12),
    st.sets(_tag_strategy, max_size=12),
)


# Feature: cicd-pipeline, Property 2: For any 已存在标签集合 existing 与目标 commit
# SHA 标签 tag，decide_push(existing, tag) 允许推送当且仅当 tag 不在 existing 中；
# 当 tag 已存在时一律拒绝（不覆盖）。
@settings(max_examples=100)
@given(existing=_existing_strategy, tag=_tag_strategy, draw_from_existing=st.booleans())
def test_property_02_decide_push(existing, tag, draw_from_existing) -> None:
    existing_list = list(existing)
    # 有时从 existing 中抽取 tag，以确保「已存在 -> 拒绝」分支被充分覆盖。
    if draw_from_existing and existing_list:
        tag = existing_list[len(existing_list) // 2]

    assert decide_push(existing, tag) == (tag not in existing)
