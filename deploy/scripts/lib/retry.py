"""重试与服务状态相关的共享数据结构与纯函数。

本模块定义跨多个验证场景复用的重试配置 ``RetryConfig``，供后续的
``retry_succeeds`` 重试判定（部署后健康检查、回滚后健康检查、推送重试）
与 ``services_all_running`` 服务状态确认等纯函数复用。

设计参见 design.md 的 "Health 重试配置模型" 与 Correctness Properties 3/7。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryConfig:
    """统一的重试配置。

    属性说明（语义对应 design.md "Health 重试配置模型"）：

    - ``max_retries``: 最大尝试次数；实际执行的尝试次数恒 ``<= max_retries``。
    - ``interval_s``: 相邻两次尝试之间的间隔秒数。
    - ``timeout_s``: 单次探测/尝试的超时秒数。
    - ``window_s``: 整个重试过程的总超时窗口秒数。

    典型取值：
    - 部署后验证（Health_Check）：``RetryConfig(10, 5, 10, 60)``（R6.1）。
    - 回滚后验证（Health_Check）：``RetryConfig(5, 10, 10, 60)``（R7.2）。

    该数据结构为不可变（frozen）的值对象，便于在纯函数间安全传递与比较。
    """

    max_retries: int
    interval_s: float
    timeout_s: float
    window_s: float


def retry_succeeds(outcomes: Iterable[bool], cfg: RetryConfig) -> bool:
    """判定一组探测结果在重试约束下是否最终成功。

    语义（对应 design.md Correctness Property 3 "通用重试判定语义"）：

    - 按顺序消费 ``outcomes`` 中的探测结果，每消费一个视为一次尝试。
    - 当且仅当在前 ``cfg.max_retries`` 次尝试内至少出现一次成功（``True``）时
      返回 ``True``。
    - 实际"消费"的尝试次数恒 ``<= cfg.max_retries``：一旦达到尝试上限仍未成功
      即停止，不再检查后续 ``outcomes``。
    - 首次成功后立即停止（短路），不再检查后续 ``outcomes``。

    以不同 ``RetryConfig`` 复用于部署后健康检查（10/5）、回滚后健康检查（5/10）
    与推送重试（3 次）等场景。

    Args:
        outcomes: 探测结果布尔序列，按尝试顺序排列。``True`` 表示该次尝试成功。
        cfg: 重试配置；本判定仅使用其 ``max_retries`` 字段约束尝试次数。

    Returns:
        在前 ``cfg.max_retries`` 次尝试内出现成功则为 ``True``，否则为 ``False``。
    """
    if cfg.max_retries <= 0:
        return False

    attempts = 0
    for outcome in outcomes:
        attempts += 1
        if outcome:
            return True
        if attempts >= cfg.max_retries:
            break
    return False


def services_all_running(ps: Mapping[str, str], required: Iterable[str]) -> bool:
    """判定一组必需服务是否全部处于 running 状态。

    语义（对应 design.md Correctness Property 7 "服务运行状态确认"，R4.3）：

    - 当且仅当 ``required`` 中的**每个**服务在 ``ps`` 中存在，且其状态规范化后
      恰为 ``"running"`` 时返回 ``True``。
    - ``required`` 通常为部署所需的四个服务：backend、worker、web、redis。

    稳健处理：

    - 状态字符串在比较前做规范化：去除首尾空白并转为小写，从而容忍诸如
      ``"Running"``、``" running "``、``"RUNNING"`` 等大小写/空白差异。
    - ``required`` 中的服务若在 ``ps`` 中缺失，视为未运行，返回 ``False``
      （即缺失等价于未达成 running，符合 Fail-Fast 语义）。
    - 空的 ``required`` 表示无任何必需服务，按"全部满足"约定返回 ``True``。

    Args:
        ps: 服务名到状态字符串的映射（如 ``docker compose ps`` 解析结果）。
        required: 必需进入 running 的服务名集合/序列。

    Returns:
        ``required`` 中每个服务在 ``ps`` 中均为 running 时返回 ``True``，否则 ``False``。
    """
    for service in required:
        status = ps.get(service)
        if status is None:
            return False
        if status.strip().lower() != "running":
            return False
    return True
