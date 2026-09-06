"""环境配置读取（布尔开关 + 整数参数），2026-09-06 新增。

为什么需要这个模块：``server.py:1669`` 与 ``app.py:49`` 各有一份逐字相同的
``_env_flag``，语义（尤其空串）必须完全一致 —— 安全开关的解释规则一旦分叉，
「同一个 FLAG= 在这台 worker 打开、在那台 worker 关闭」这种问题几乎无法归因。
新代码一律从这里导入，不要再抄第三份；两处旧副本行为与本模块一致，收敛它们
需要同时动两个热文件，登记为技术债（见 docs/tasks 的任务记录）。

空串必须回落到 ``default``：``docker-compose`` 里 ``FLAG=`` 是「声明变量但留空」的
常见写法，若把空串当真值，所有 ``default=False`` 的安全开关（CORS credentials、
legacy OIDC callback）都会被一次空赋值打开。
"""

from __future__ import annotations

import os

_FALSY = {"0", "false", "no", "off"}


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in _FALSY


def env_int(name: str, default: int, floor: int | None = None) -> int:
    """读整数型配置；非数字/缺失一律回 ``default``，可选下界钳制。

    ``floor`` 的必要性：安全参数的「配错方向」通常不是变大而是变小 —— 限流阈值写成 1、
    密码长度写成 1 位，等于把开关关掉还留了个看起来在生效的假象。写库后不可逆的参数
    （如 PBKDF2 迭代数）必须有下界。
    """
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None and raw.strip() else default
    except ValueError:
        return default
    if floor is not None:
        return max(floor, value)
    return value


def env_float(name: str, default: float, floor: float | None = None) -> float:
    """读浮点型配置（超时、系数一类）。语义与 ``env_int`` 严格一致。

    单独立一个函数是为了消灭另一类缺陷：``float(os.environ.get(NAME, "8"))`` 写在模块
    顶层时，一个拼错的值（``8s``）会在 **import 阶段** 抛 ValueError —— 表现是整个进程
    起不来，而不是这一项配置失效。调用时读 + 兜底才是可运维的配置。
    """
    raw = os.environ.get(name)
    try:
        value = float(raw) if raw is not None and raw.strip() else default
    except ValueError:
        return default
    if floor is not None:
        return max(floor, value)
    return value
