"""属性测试：Property 4 — Smoke_Test 结果评估。

被测纯函数位于 ``deploy/scripts/lib/smoke.py``：

- ``evaluate_smoke(results)``：当且仅当 ``results`` 中不存在任何返回 500 的端点、
  且不存在任何连接失败的端点时返回 ``True``（通过）；否则返回 ``False``（失败）。

结果元组结构（见 design.md）::

    (desc, method, path, status_code, elapsed, result, error)

失败信号（与 smoke.py 的解释保持一致）：
1. 服务端错误：``status_code == 500``。
2. 连接失败：无有效 HTTP 状态码（``status_code`` 为 None，或不是 100-599
   范围内的合法整数，例如 ``"ERR"`` 占位），或 ``error`` 为非空字符串。

设计参见 cicd-pipeline/design.md 的 Correctness Properties → Property 4。
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

from lib.smoke import evaluate_smoke  # noqa: E402

# ---------------------------------------------------------------------------
# 生成器：构造三类端点结果元组（healthy / server-error / connection-failure），
# 每类显式携带其预期分类，便于独立参考断言 iff 关系。
# ---------------------------------------------------------------------------

# 健康端点：HTTP 状态码为在线且非 500（如 200/404/422），error 为空字符串。
_HEALTHY_STATUS = st.sampled_from([200, 201, 204, 301, 302, 400, 401, 403, 404, 422])

# 服务端错误：状态码恰为 500，error 可空可非空——无论如何都应判失败。
_server_error_tuple = st.tuples(
    st.text(max_size=8),                 # desc
    st.sampled_from(["GET", "POST"]),    # method
    st.text(max_size=8),                 # path
    st.just(500),                        # status_code
    st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False),
    st.sampled_from(["PASS", "FAIL"]),   # result
    st.sampled_from(["", "boom", "500 Internal Server Error"]),  # error
)

# 连接失败：无有效状态码（None / "ERR" 占位 / 越界整数），或携带非空 error。
_no_status_value = st.sampled_from([None, "ERR", 0, 99, 600, 1000])
_conn_fail_no_status = st.tuples(
    st.text(max_size=8),
    st.sampled_from(["GET", "POST"]),
    st.text(max_size=8),
    _no_status_value,
    st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False),
    st.sampled_from(["PASS", "FAIL"]),
    st.sampled_from(["", "timeout", "connection refused"]),
)
# 有有效非 500 状态码，但 error 非空 —— 仍属连接/请求失败信号。
_conn_fail_with_error = st.tuples(
    st.text(max_size=8),
    st.sampled_from(["GET", "POST"]),
    st.text(max_size=8),
    _HEALTHY_STATUS,
    st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False),
    st.sampled_from(["PASS", "FAIL"]),
    st.sampled_from(["timeout", "connection refused", "  spaced  "]),
)
_failure_tuple = st.one_of(
    _server_error_tuple, _conn_fail_no_status, _conn_fail_with_error
)

# 健康端点：有效非 500 状态码 且 error 为空（含纯空白，strip 后为空）。
_healthy_tuple = st.tuples(
    st.text(max_size=8),
    st.sampled_from(["GET", "POST"]),
    st.text(max_size=8),
    _HEALTHY_STATUS,
    st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False),
    st.sampled_from(["PASS"]),
    st.sampled_from(["", "   ", "\t"]),  # 空或纯空白 -> 非失败
)

_result_tuple = st.one_of(_healthy_tuple, _failure_tuple)


def _reference_endpoint_failed(result) -> bool:
    """独立于被测实现的参考判定：单个端点是否失败。

    镜像 smoke.py 的失败解释，但用直接的条件表达，避免复用被测内部逻辑。
    """
    status_code = result[3]
    error = result[6]

    # 规整状态码：仅 100-599 的非 bool 整数视为有效 HTTP 状态码。
    valid_status = None
    if not isinstance(status_code, bool):
        try:
            code = int(status_code)
        except (TypeError, ValueError):
            code = None
        if code is not None and 100 <= code <= 599:
            valid_status = code

    # 服务端错误。
    if valid_status == 500:
        return True
    # 连接失败：无有效状态码。
    if valid_status is None:
        return True
    # 连接失败：携带非空错误信息。
    if isinstance(error, str):
        if error.strip():
            return True
    elif error is not None and bool(error):
        return True
    return False


# Feature: cicd-pipeline, Property 4: For any 端点结果集合 results，
# evaluate_smoke(results) 判定为通过当且仅当其中不存在任何返回 500 的端点且
# 不存在任何连接失败的端点；否则判定为失败。
@settings(max_examples=100)
@given(results=st.lists(_result_tuple, max_size=12))
def test_property_04_evaluate_smoke(results) -> None:
    expected_pass = not any(_reference_endpoint_failed(r) for r in results)
    assert evaluate_smoke(results) == expected_pass
