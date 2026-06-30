"""校验相关的纯函数库。

本模块提供与发布安全相关的纯函数：

- ``is_valid_sha``: 判定字符串是否为合法的 40 位小写十六进制 commit SHA。
- ``build_image_tag``: 由合法 SHA 生成不可变的完整镜像引用字符串。
- ``validate_secrets``: 校验必需 Secret 是否均存在且非空，失败时仅报告名称、
  绝不包含 secret 的值。

设计参见 design.md 的 "Data Models / IMAGE_TAG 与镜像寻址" 与
Correctness Properties 1（Commit SHA 标签校验）、6（必需 Secret 校验）。
"""

from __future__ import annotations

import re
from typing import Mapping, NamedTuple, Sequence

# 合法 commit SHA：恰为 40 位小写十六进制字符（0-9、a-f）。
_SHA_PATTERN = re.compile(r"\A[0-9a-f]{40}\Z")


def is_valid_sha(s: str) -> bool:
    """判定 ``s`` 是否为合法的 40 位小写十六进制 commit SHA。

    当且仅当 ``s`` 恰为 40 位小写十六进制字符（``0-9`` 与 ``a-f``）时返回
    ``True``；其余情况（长度不为 40、含大写字母、含非十六进制字符、含空白等）
    一律返回 ``False``。

    Args:
        s: 待校验的字符串。

    Returns:
        当且仅当 ``s`` 为合法 40 位小写十六进制 SHA 时为 ``True``。
    """
    if not isinstance(s, str):
        return False
    return _SHA_PATTERN.match(s) is not None


def build_image_tag(registry: str, image_prefix: str, service: str, sha: str) -> str:
    """由合法 SHA 生成不可变的完整镜像引用字符串。

    镜像引用格式为 ``${REGISTRY}/${IMAGE_PREFIX}/<service>:${IMAGE_TAG}``，
    其中 ``IMAGE_TAG`` 即完整的 40 位 commit SHA。生成的标签完整包含该 40 位
    SHA，保证可追溯且不可变。

    Args:
        registry: 镜像仓库地址（如 ``ghcr.io``）。
        image_prefix: 镜像前缀（如 ``<owner>/<repo>``）。
        service: 服务名（如 ``backend``、``web``）。
        sha: 完整的 40 位小写十六进制 commit SHA。

    Returns:
        完整镜像引用字符串，例如
        ``ghcr.io/owner/repo/backend:<40位sha>``。

    Raises:
        ValueError: 当 ``sha`` 不是合法的 40 位小写十六进制 SHA 时抛出，
            遵循 Fail-Fast 原则尽早暴露非法标签。
    """
    if not is_valid_sha(sha):
        raise ValueError(f"非法的 commit SHA，必须为 40 位小写十六进制字符: {sha!r}")
    return f"{registry}/{image_prefix}/{service}:{sha}"


class SecretsValidationResult(NamedTuple):
    """``validate_secrets`` 的返回结构。

    Attributes:
        ok: 当且仅当所有必需 Secret 均存在且为非空字符串时为 ``True``。
        missing: 所有缺失或值为空字符串的必需 Secret 名称列表，按 ``required``
            中的出现顺序排列。**仅包含名称，绝不包含任何 secret 的值。**
            当 ``ok`` 为 ``True`` 时该列表为空。
    """

    ok: bool
    missing: list[str]


def validate_secrets(
    mapping: Mapping[str, object], required: Sequence[str]
) -> SecretsValidationResult:
    """校验 ``required`` 中每个必需 Secret 是否均存在且为非空字符串。

    当且仅当 ``required`` 中每个名称在 ``mapping`` 中都存在、且对应值为非空
    字符串时，校验通过（``ok=True`` 且 ``missing`` 为空）。否则校验失败，
    ``missing`` 恰好列出所有缺失或值为空字符串（``""``）的必需名称。

    本函数遵循 Fail-Fast 与最小信息泄露原则：返回报告**只含名称、绝不包含
    任何 secret 的值**，可安全地写入日志或作业输出（对应 design.md
    Property 6 与 R5.5）。

    判定为「缺失/为空」的情形包括：

    - 名称不在 ``mapping`` 中；
    - 名称存在但值为 ``None``；
    - 名称存在但值不是 ``str`` 类型；
    - 名称存在且为 ``str`` 但去除两端空白后为空字符串。

    Args:
        mapping: Secret 名称到值的映射（如环境变量字典）。
        required: 必需存在且非空的 Secret 名称序列。

    Returns:
        ``SecretsValidationResult(ok, missing)``。``ok`` 表示是否全部通过；
        ``missing`` 按 ``required`` 顺序列出所有缺失/为空的名称，不含重复
        （同一名称在 ``required`` 中重复时只报告一次）。
    """
    missing: list[str] = []
    seen: set[str] = set()
    for name in required:
        if name in seen:
            continue
        seen.add(name)
        value = mapping.get(name)
        if not isinstance(value, str) or value.strip() == "":
            missing.append(name)
    return SecretsValidationResult(ok=not missing, missing=missing)
