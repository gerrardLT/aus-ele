"""Property 6（必需 Secret 校验）的属性测试。

被测纯函数：``deploy/scripts/lib/validate.py`` 的 ``validate_secrets``。

# Feature: cicd-pipeline, Property 6: 必需 Secret 校验 — For any secret 名称到值的
# 映射 m 与必需名称集合 required，validate_secrets(m, required) 通过当且仅当 required
# 中每个名称在 m 中都存在且对应值为非空字符串；当校验失败时，返回的报告恰好列出所有
# 缺失/为空的名称，且报告中不包含任何 secret 的值。
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

from lib.validate import validate_secrets  # noqa: E402


# 必需 Secret 名称的候选池：固定一组合法标识符名称，便于在「存在/缺失」之间组合。
_NAMES = [
    "AUS_ELE_JWT_SECRET",
    "FINGRID_API_KEY",
    "SSH_HOST",
    "SSH_USER",
    "SSH_KEY",
    "REGISTRY",
]

# 三种取值类别：
#  - "present_nonempty": 名称存在且为非空字符串（去空白后非空）-> 合格
#  - "present_empty":    名称存在但值为空/纯空白字符串       -> 缺失
#  - "present_nonstr":   名称存在但值不是字符串（None / 数字）-> 缺失
#  - "absent":           名称不在映射中                       -> 缺失
# 非空值统一加 "val::" 前缀，保证其永远不等于任何必需名称（_NAMES 均无此前缀），
# 从而让「报告不含 secret 值」的断言不会因值与名称偶然相等而误报。
_nonempty_value = st.text(min_size=1).map(lambda s: "val::" + s)
_empty_value = st.sampled_from(["", " ", "   ", "\t", "\n", " \t \n "])
_nonstr_value = st.sampled_from([None, 0, 123, True, [], {}])

# 每个名称随机分配一种类别。
_category = st.sampled_from(
    ["present_nonempty", "present_empty", "present_nonstr", "absent"]
)


@st.composite
def _scenario(draw):
    """生成 (mapping, required, expected_missing_set, all_secret_values)。

    - required 为 _NAMES 的一个非空子集（保留顺序、去重）。
    - 为 required 中每个名称随机分配一种类别，据此构造 mapping 条目并计算期望缺失集合。
    - 额外注入若干「非必需」的存在项（含敏感值），以验证它们既不影响判定、其值也
      不会出现在报告中。
    """
    # required：从 _NAMES 中按顺序选取一个非空子集。
    flags = draw(
        st.lists(st.booleans(), min_size=len(_NAMES), max_size=len(_NAMES))
    )
    required = [name for name, keep in zip(_NAMES, flags) if keep]
    if not required:
        required = [draw(st.sampled_from(_NAMES))]

    mapping: dict[str, object] = {}
    expected_missing: set[str] = set()
    secret_values: list[str] = []

    for name in required:
        cat = draw(_category)
        if cat == "present_nonempty":
            val = draw(_nonempty_value)
            mapping[name] = val
            secret_values.append(val)
        elif cat == "present_empty":
            val = draw(_empty_value)
            mapping[name] = val
            secret_values.append(val)
            expected_missing.add(name)
        elif cat == "present_nonstr":
            mapping[name] = draw(_nonstr_value)
            expected_missing.add(name)
        else:  # absent
            expected_missing.add(name)

    # 注入非必需的敏感项：其名称不在 required 中，值是真实 secret 风格的非空串。
    extra_pool = [n for n in _NAMES if n not in required] + [
        "UNRELATED_TOKEN",
        "EXTRA_PASSWORD",
    ]
    for extra in draw(st.lists(st.sampled_from(extra_pool), max_size=4, unique=True)):
        val = draw(_nonempty_value)
        mapping[extra] = val
        secret_values.append(val)

    return mapping, required, expected_missing, secret_values


@settings(max_examples=100)
@given(_scenario())
def test_validate_secrets_property_6(scenario):
    mapping, required, expected_missing, secret_values = scenario

    result = validate_secrets(mapping, required)

    # ok 当且仅当不存在任何缺失/为空的必需名称。
    assert result.ok == (len(expected_missing) == 0)

    # missing 恰好等于所有缺失/为空的必需名称集合（去重后比较，函数保证不含重复）。
    assert set(result.missing) == expected_missing
    assert len(result.missing) == len(set(result.missing))  # 无重复

    # 报告中仅包含名称：每个 missing 项必须来自 required 集合，且不得是任何 secret 值。
    for name in result.missing:
        assert name in required

    # 报告中绝不包含任何 secret 的值（最小信息泄露）。
    for value in secret_values:
        if isinstance(value, str) and value != "":
            assert value not in result.missing
