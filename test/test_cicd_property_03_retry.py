"""属性测试：Property 3 — 通用重试判定语义。

被测纯函数位于 ``deploy/scripts/lib/retry.py``：

- ``retry_succeeds(outcomes, cfg)``：当且仅当在前 ``cfg.max_retries`` 次尝试内
  至少出现一次成功（``True``）时返回 ``True``；实际消费的尝试次数恒
  ``<= cfg.max_retries``，并在首次成功后停止。

本测试以不同 ``RetryConfig`` 覆盖部署后健康检查（10/5）、回滚后健康检查（5/10）
与推送重试（3 次）。

设计参见 cicd-pipeline/design.md 的 Correctness Properties → Property 3。
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# 将 deploy/scripts 加入 sys.path，使 `from lib.retry import ...` 可解析。
# 本测试文件位于 <repo>/test/，lib 包位于 <repo>/deploy/scripts/lib/。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "deploy", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.retry import RetryConfig, retry_succeeds  # noqa: E402


class _CountingIterable:
    """包装布尔序列的可计数迭代器。

    记录被实际消费（迭代取出）的元素个数，用于断言 ``retry_succeeds``：
    - 实际消费的尝试次数恒 ``<= max_retries``；
    - 首次成功后立即停止（不再消费后续元素）。
    """

    def __init__(self, outcomes: list[bool]) -> None:
        self._outcomes = outcomes
        self.consumed = 0

    def __iter__(self):
        for outcome in self._outcomes:
            self.consumed += 1
            yield outcome


def _reference_first_window_has_success(outcomes: list[bool], max_retries: int) -> bool:
    """独立参考实现：前 max_retries 个元素中是否存在 True。"""
    if max_retries <= 0:
        return False
    return any(outcomes[:max_retries])


# 探测结果布尔序列：覆盖空序列、全失败、全成功与混合情形。
outcomes_strategy = st.lists(st.booleans(), min_size=0, max_size=30)

# RetryConfig 生成器：max_retries 覆盖 0/边界与典型值，并显式纳入
# 部署后健康检查(10)、回滚后健康检查(5) 与推送重试(3) 三种权威配置。
retry_config_strategy = st.one_of(
    st.builds(
        RetryConfig,
        max_retries=st.integers(min_value=0, max_value=15),
        interval_s=st.floats(min_value=0.0, max_value=60.0, allow_nan=False),
        timeout_s=st.floats(min_value=0.0, max_value=60.0, allow_nan=False),
        window_s=st.floats(min_value=0.0, max_value=120.0, allow_nan=False),
    ),
    st.just(RetryConfig(10, 5, 10, 60)),  # 部署后健康检查
    st.just(RetryConfig(5, 10, 10, 60)),  # 回滚后健康检查
    st.just(RetryConfig(3, 10, 10, 30)),  # 推送重试
)


# Feature: cicd-pipeline, Property 3: For any 探测结果布尔序列 outcomes 与重试
# 配置 RetryConfig{max_retries, interval_s, ...}，retry_succeeds(outcomes, cfg)
# 返回成功当且仅当在前 max_retries 次尝试内至少出现一次成功；且实际执行的尝试
# 次数恒 <= max_retries，并在首次成功后停止。该属性以不同配置覆盖部署后健康检查
# （10/5）、回滚后健康检查（5/10）与推送重试（3 次）。
@settings(max_examples=100)
@given(outcomes=outcomes_strategy, cfg=retry_config_strategy)
def test_property_03_retry_succeeds_semantics(
    outcomes: list[bool], cfg: RetryConfig
) -> None:
    counting = _CountingIterable(outcomes)
    result = retry_succeeds(counting, cfg)

    # iff：成功 当且仅当 前 max_retries 个结果中存在成功。
    assert result == _reference_first_window_has_success(outcomes, cfg.max_retries)

    # 实际消费的尝试次数恒 <= max_retries（且不超过序列长度）。
    effective_cap = max(cfg.max_retries, 0)
    assert counting.consumed <= effective_cap
    assert counting.consumed <= len(outcomes)

    # 首次成功后停止：若返回成功，则停在窗口内首个 True 处，
    # 已消费数恰等于该首个 True 的位置（1-based）。
    if result:
        window = outcomes[: cfg.max_retries]
        first_success_index = window.index(True)
        assert counting.consumed == first_success_index + 1
    else:
        # 未成功：要么窗口耗尽（消费达上限），要么序列先耗尽。
        assert counting.consumed == min(effective_cap, len(outcomes))
