"""Last_Stable_Tag 状态文件的读写纯函数。

本模块负责持久化「上一次通过部署后验证的镜像 commit SHA」。状态文件内容为
单行 40 位 commit SHA，默认位于服务器侧 ``/opt/aus-ele/state/last_stable_tag``
（见 design.md "Last_Stable_Tag 状态文件"）。

为便于属性测试与单元测试以临时路径运行，读写函数均支持注入路径参数。

设计参见 design.md 的 Correctness Property 5「Last_Stable_Tag 持久化往返」：
对任意合法 commit SHA ``tag``，先 ``write_stable_tag(tag)`` 再 ``read_stable_tag()``
返回的值与 ``tag`` 相等（round-trip 恒等）。
"""

from __future__ import annotations

from pathlib import Path

from .validate import is_valid_sha

# 状态文件的权威默认路径（服务器侧，单机部署）。
DEFAULT_STABLE_TAG_PATH = Path("/www/wwwroot/aus-ele/state/last_stable_tag")


def write_stable_tag(tag: str, path: str | Path = DEFAULT_STABLE_TAG_PATH) -> None:
    """将稳定版本 commit SHA 写入状态文件。

    写入前确保父目录存在（不存在则创建），以单行形式写入 ``tag``。
    若文件已存在则覆盖为最新稳定标签。

    Args:
        tag: 待记录为 Last_Stable_Tag 的 commit SHA。
        path: 状态文件路径，默认 :data:`DEFAULT_STABLE_TAG_PATH`；
            测试可注入临时路径。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tag, encoding="utf-8")


def read_stable_tag(path: str | Path = DEFAULT_STABLE_TAG_PATH) -> str | None:
    """读取状态文件中记录的稳定版本 commit SHA。

    语义（对应 design.md "Last_Stable_Tag 状态文件" 与 Property 5）：

    - 文件不存在时返回 ``None``，表示尚无稳定版本（首次部署）。
    - 文件存在时返回其内容（去除首尾空白），以保证与 :func:`write_stable_tag`
      的往返恒等。

    Args:
        path: 状态文件路径，默认 :data:`DEFAULT_STABLE_TAG_PATH`；
            测试可注入临时路径。

    Returns:
        记录的 commit SHA；文件不存在时返回 ``None``。
    """
    source = Path(path)
    if not source.exists():
        return None
    return source.read_text(encoding="utf-8").strip()


def decide_rollback(last_stable: str | None) -> bool:
    """根据 Last_Stable_Tag 决定是否执行回滚。

    决策语义（对应 design.md Correctness Property 8「回滚目标决策」与 R7.3）：

    - 当且仅当 ``last_stable`` 为合法的 40 位小写十六进制 commit SHA 时，
      存在可回滚的稳定版本，决定执行回滚，返回 ``True``。
    - 其余情况一律决定跳过回滚并以失败收场，返回 ``False``，包括：

      - ``last_stable`` 为 ``None``（状态文件不存在，即首次部署无可回滚版本）；
      - 为空字符串或仅含空白；
      - 为非法 SHA（长度不为 40、含大写字母、含非十六进制字符等）。

    合法性判定复用 :func:`deploy.scripts.lib.validate.is_valid_sha`，保证与镜像
    标签校验口径一致。

    Args:
        last_stable: 由 :func:`read_stable_tag` 读取到的稳定版本 commit SHA，
            可能为 ``None``。

    Returns:
        当且仅当存在合法的 Last_Stable_Tag 时为 ``True``（执行回滚）；
        否则为 ``False``（跳过并以失败收场）。
    """
    # 复用与镜像标签一致的 SHA 校验口径；is_valid_sha 已处理非 str 与 None。
    return is_valid_sha(last_stable)
