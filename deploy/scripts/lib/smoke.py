"""Smoke_Test 结果评估纯函数库。

对应设计文档 Correctness Properties 中的 Property 4（Smoke_Test 结果评估）。

`smoke_test_api.py` 为每个被测端点产出一个结果元组，结构（见 design.md）为::

    (desc, method, path, status_code, elapsed, result, error)

各字段索引及含义：

==== =============== =================================================
索引 字段            含义
==== =============== =================================================
0    desc            端点描述
1    method          HTTP 方法
2    path            请求路径
3    status_code     HTTP 状态码；成功为整数（如 200/404/422），
                     连接失败时无有效状态码（None 或非状态码占位）
4    elapsed         耗时
5    result          "PASS" / "FAIL" 文本结论（仅供展示）
6    error           错误摘要；正常或非 500 路由命中时为空字符串
==== =============== =================================================

失败信号判定（稳健处理两类失败）：

1. 服务端错误：``status_code`` 等于 500。
2. 连接失败：无有效 HTTP 状态码（``status_code`` 为 None，或不是 100-599
   范围内的合法状态码，例如脚本在异常时填入的 ``"ERR"`` 占位），或者
   ``error`` 字段为非空字符串。

注意：非 500 的 HTTP 响应（如 404/422）表示路由存在且服务在线，``error``
为空，因此判定为通过——与 `smoke_test_api.py` 将其标记为 PASS 的语义一致。
"""

from __future__ import annotations

# 结果元组中各字段的固定位置（见上文表格与 design.md）。
_STATUS_CODE_INDEX = 3
_ERROR_INDEX = 6

# 合法 HTTP 状态码范围。
_HTTP_STATUS_MIN = 100
_HTTP_STATUS_MAX = 599

# 表示服务端错误的状态码。
_SERVER_ERROR_STATUS = 500


def _as_http_status(status_code):
    """将 ``status_code`` 规整为合法 HTTP 状态码整数。

    若无法解释为 100-599 范围内的整数（例如 None、``"ERR"`` 占位、空串），
    返回 ``None`` 表示「无有效 HTTP 状态码」。
    """
    if isinstance(status_code, bool):
        # bool 是 int 的子类，单独排除以免被当作 0/1 状态码。
        return None
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return None
    if _HTTP_STATUS_MIN <= code <= _HTTP_STATUS_MAX:
        return code
    return None


def _is_server_error(status_code) -> bool:
    """端点是否返回了 500 服务端错误。"""
    return _as_http_status(status_code) == _SERVER_ERROR_STATUS


def _is_connection_failure(status_code, error) -> bool:
    """端点是否表现为连接失败。

    连接失败的两个信号：无有效 HTTP 状态码，或携带非空错误信息。
    """
    if _as_http_status(status_code) is None:
        return True
    if isinstance(error, str):
        return bool(error.strip())
    # 非字符串但为真值（如异常对象）同样视为错误信号。
    return error is not None and bool(error)


def _endpoint_failed(result) -> bool:
    """单个端点结果是否判定为失败。"""
    status_code = result[_STATUS_CODE_INDEX]
    error = result[_ERROR_INDEX]
    return _is_server_error(status_code) or _is_connection_failure(status_code, error)


def evaluate_smoke(results) -> bool:
    """评估冒烟测试整体结论。

    当且仅当 ``results`` 中不存在任何返回 500 的端点、且不存在任何连接失败
    的端点时返回 ``True``（通过）；否则返回 ``False``（失败）。

    空结果集合视为通过（无任何失败端点）。

    Args:
        results: 端点结果元组的可迭代集合，每个元组结构为
            ``(desc, method, path, status_code, elapsed, result, error)``。

    Returns:
        bool: 通过为 ``True``，失败为 ``False``。
    """
    return not any(_endpoint_failed(result) for result in results)


def decide_push(existing, tag) -> bool:
    """决定是否允许推送某个不可变镜像标签（覆盖保护）。

    对应设计文档 Correctness Properties 中的 Property 2（不可变标签覆盖保护，
    R3.6）。不可变标签语义要求：同一 commit SHA 标签一经推送便不可被覆盖。

    当且仅当目标标签 ``tag`` 不在已存在标签集合 ``existing`` 中时允许推送
    （返回 ``True``）；只要 ``tag`` 已存在，便一律拒绝推送（返回 ``False``），
    以避免覆盖既有镜像。

    Args:
        existing: 已存在标签的可迭代集合（list/set/tuple 等）。
        tag: 目标 commit SHA 标签。

    Returns:
        bool: 允许推送为 ``True``，拒绝（已存在，不覆盖）为 ``False``。
    """
    return tag not in set(existing)
