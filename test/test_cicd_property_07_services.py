"""Property 7（服务运行状态确认）的属性测试。

被测纯函数：``deploy/scripts/lib/retry.py`` 的 ``services_all_running``。

# Feature: cicd-pipeline, Property 7: 服务运行状态确认 — For any 服务名到状态的映射 ps
# 与必需服务集合 required（backend、worker、web、redis），services_all_running(ps,
# required) 为真当且仅当 required 中每个服务在 ps 中的状态均为 running。
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

from lib.retry import services_all_running  # noqa: E402


# 候选服务名池：含设计要求的四个必需服务，外加若干无关服务名以覆盖
# 「ps 中存在非必需服务」与「required 取任意子集」的组合空间。
_SERVICE_NAMES = ["backend", "worker", "web", "redis", "nginx", "db", "scheduler"]


def _normalizes_to_running(status: str) -> bool:
    """复刻被测函数的规范化语义：去首尾空白 + 转小写后是否恰为 'running'。

    作为「期望值」的独立判定，仅依赖属性陈述（规范化后等于 running），
    不调用被测实现，从而构成对 services_all_running 的真实交叉校验。
    """
    return status.strip().lower() == "running"


# running 状态字符串：以多种大小写/空白包裹形式表达「运行中」，全部应判定为 running。
_running_status = st.sampled_from(
    [
        "running",
        "Running",
        "RUNNING",
        " running ",
        "\trunning\n",
        "  Running  ",
    ]
)

# 非 running 状态字符串：常见的 docker compose 状态，规范化后均不等于 'running'。
_non_running_status = st.sampled_from(
    [
        "exited",
        "restarting",
        "created",
        "paused",
        "dead",
        "removing",
        "Exited (1)",
        "",
        "   ",
        "run",
        "running ok",
        "not running",
    ]
)

_any_status = st.one_of(_running_status, _non_running_status)


@st.composite
def _scenario(draw):
    """生成 (ps, required)。

    - ps：服务名到任意状态字符串（running/非 running 混合）的映射。
    - required：服务名池的任意子集（可能为空，可能含 ps 中不存在的名称）。

    通过让 required 可包含 ps 中缺失的名称，覆盖「缺失即未运行」的语义；
    通过让 ps 含 required 之外的服务，验证多余服务不影响判定。
    """
    # ps：为服务名池中随机一部分名称分配随机状态。
    ps_names = draw(
        st.lists(st.sampled_from(_SERVICE_NAMES), max_size=len(_SERVICE_NAMES), unique=True)
    )
    ps = {name: draw(_any_status) for name in ps_names}

    # required：服务名池的任意子集（保持去重，可为空）。
    required = draw(
        st.lists(st.sampled_from(_SERVICE_NAMES), max_size=len(_SERVICE_NAMES), unique=True)
    )

    return ps, required


@settings(max_examples=100)
@given(_scenario())
def test_services_all_running_property_7(scenario):
    ps, required = scenario

    result = services_all_running(ps, required)

    # 期望值：当且仅当 required 中每个服务都在 ps 中存在且规范化后为 running。
    expected = all(
        name in ps and _normalizes_to_running(ps[name]) for name in required
    )

    assert result == expected
