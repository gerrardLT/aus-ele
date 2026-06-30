"""Property 5（Last_Stable_Tag 持久化往返）的属性测试。

被测纯函数：``deploy/scripts/lib/stable_tag.py`` 的 ``write_stable_tag`` 与
``read_stable_tag``。

# Feature: cicd-pipeline, Property 5: Last_Stable_Tag 持久化往返 — For any 合法
# commit SHA tag，先 write_stable_tag(tag) 再 read_stable_tag() 返回的值与 tag
# 相等（round-trip 恒等）。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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

from lib.stable_tag import read_stable_tag, write_stable_tag  # noqa: E402

# 合法 commit SHA：恰为 40 位小写十六进制字符。
_valid_sha = st.text(alphabet="0123456789abcdef", min_size=40, max_size=40)


@settings(max_examples=100)
@given(_valid_sha)
def test_stable_tag_roundtrip_property_5(tag):
    # 使用临时目录中的状态文件，确保不触碰任何仓库内文件。
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 状态文件位于尚不存在的子目录下，顺带验证 write 会创建父目录。
        state_path = Path(tmp_dir) / "state" / "last_stable_tag"

        write_stable_tag(tag, state_path)
        result = read_stable_tag(state_path)

        # round-trip 恒等：先写后读返回值与写入值相等。
        assert result == tag
    # TemporaryDirectory 退出时自动清理临时文件。
