"""shell 脚本与 lib 纯函数库的集成/烟测（task 8.4）。

目标（对应 design.md Testing Strategy 与 R4.3 / R6.5 / R7.1）：

本测试在**不依赖真实 docker / SSH**的前提下，验证 deploy/verify/rollback 三个
服务器侧 shell 脚本与 ``deploy/scripts/lib`` 纯函数之间的「集成契约」：

1. 三个脚本均存在且通过 ``bash -n`` 语法检查（定位 bash：优先 PATH 中的
   ``bash``，Windows 回退到 Git 自带 ``C:\\Program Files\\Git\\bin\\bash.exe``；
   若环境确实没有任何 bash，则以 ``unittest.skip`` 优雅跳过该部分）。

2. 通过 ``subprocess`` 以 ``PYTHONPATH=deploy/scripts`` 调用 python，复刻脚本中
   内嵌的 ``python3 -c`` 决策片段，验证脚本所依赖的 lib 决策与退出码传播确实
   成立（这部分在本环境一定会运行并通过）：

   - ``services_all_running``（deploy.sh 阶段 5）：四服务全部 running -> 退出 0；
     缺任一服务 -> 非零退出。
   - ``retry_succeeds`` + ``RetryConfig(5, 10, 10, 60)``（rollback.sh 回滚后健康
     检查）：全部 False -> 非零退出；窗口内出现 True -> 退出 0。
   - ``decide_rollback``（rollback.sh 回滚目标判定）：合法 SHA -> 退出 0；
     None/空 -> 非零退出。
   - ``write_stable_tag`` / ``read_stable_tag``（verify.sh 记录稳定标签）：经临时
     路径往返一致。

这些片段与 shell 脚本中实际使用的 ``python3 -c`` 决策片段一一对应，从而校验
集成契约而无需真实的 docker / SSH 环境。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径与环境定位
# ---------------------------------------------------------------------------
# 仓库根目录（test/ 的上一级）。
_REPO_ROOT = Path(__file__).resolve().parent.parent
# 脚本目录即 lib 包的父目录；脚本通过 PYTHONPATH=<此目录> 以 `lib.<module>` 导入。
_SCRIPTS_DIR = _REPO_ROOT / "deploy" / "scripts"

_DEPLOY_SH = _SCRIPTS_DIR / "deploy.sh"
_VERIFY_SH = _SCRIPTS_DIR / "verify.sh"
_ROLLBACK_SH = _SCRIPTS_DIR / "rollback.sh"


def _find_bash() -> str | None:
    """定位一个能读取 Windows 路径脚本的 bash 解释器。

    在 Windows 上优先使用 Git 自带 bash（msys，可正确解析 ``g:\\...`` 路径）；
    刻意跳过 ``C:\\Windows\\System32\\bash.exe``（WSL 启动器）——它无法读取
    Windows 风格路径且常因未安装发行版而不可靠。其余平台直接使用 PATH 中的
    ``bash``。若都不可用返回 ``None``，调用方据此优雅跳过语法检查部分。
    """
    # Windows 常见的 Git Bash 安装路径优先。
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if Path(candidate).is_file():
            return candidate

    bash = shutil.which("bash")
    if bash:
        # 跳过 WSL 启动器（system32\bash.exe）：无法读取 Windows 风格路径。
        if Path(bash).parent.name.lower() == "system32":
            return None
        return bash
    return None


def _run_lib_snippet(code: str, *args: str, stdin: str | None = None,
                     extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """以 ``PYTHONPATH=deploy/scripts`` 运行内嵌 python 决策片段。

    复刻 shell 脚本中 ``PYTHONPATH=${SCRIPT_DIR} python3 -c '<code>' args...``
    的调用方式。使用当前解释器（``sys.executable``）以保证在本环境可运行。

    Args:
        code: 要执行的 python 源码（对应脚本中的 ``python3 -c`` 内容）。
        *args: 透传给脚本的位置参数（对应 ``sys.argv[1:]``）。
        stdin: 可选的标准输入内容（services_all_running 片段经 stdin 读取 JSON）。
        extra_env: 需要额外注入的环境变量（如 REQUIRED_SERVICES）。

    Returns:
        ``subprocess.CompletedProcess``，其 ``returncode`` 即脚本依赖的退出码。
    """
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SCRIPTS_DIR)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, "-c", code, *args],
        input=stdin,
        env=env,
        capture_output=True,
        text=True,
    )


# 复刻 deploy.sh 阶段 5 的 services_all_running 决策片段（经 stdin 读取 ps JSON）。
_SERVICES_SNIPPET = """
import json
import os
import sys

from lib.retry import services_all_running

raw = sys.stdin.read().strip()
status = {}
if raw:
    try:
        parsed = json.loads(raw)
        records = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    for rec in records:
        name = rec.get("Service") or rec.get("Name")
        state = rec.get("State") or rec.get("Status") or ""
        if name:
            status[name] = state

required = os.environ.get("REQUIRED_SERVICES", "").split()
sys.exit(0 if services_all_running(status, required) else 1)
"""

# 复刻 rollback.sh 回滚后健康检查的 retry_succeeds 决策片段（outcomes 经 argv 传入）。
_RETRY_SNIPPET = """
import sys
from lib.retry import RetryConfig, retry_succeeds
outcomes = [token == "true" for token in sys.argv[1:]]
cfg = RetryConfig(max_retries=5, interval_s=10, timeout_s=10, window_s=60)
sys.exit(0 if retry_succeeds(outcomes, cfg) else 1)
"""

# 复刻 rollback.sh 的 decide_rollback 决策片段（last 经 argv[1] 传入，空串视为 None）。
_DECIDE_ROLLBACK_SNIPPET = """
import sys
from lib.stable_tag import decide_rollback
last = sys.argv[1] if sys.argv[1] else None
sys.exit(0 if decide_rollback(last) else 1)
"""

# 复刻 verify.sh 阶段 3 的 stable_tag 写入片段（APP_DIR/IMAGE_TAG 经环境注入）。
_WRITE_STABLE_TAG_SNIPPET = """
import os
from lib.stable_tag import write_stable_tag

tag = os.environ.get("IMAGE_TAG", "").strip()
if not tag:
    raise SystemExit("IMAGE_TAG is empty; cannot record Last_Stable_Tag")

state_path = os.path.join(os.environ["APP_DIR"], "state", "last_stable_tag")
write_stable_tag(tag, state_path)
"""

# 复刻 rollback.sh 读取 Last_Stable_Tag 的片段（path 经 argv[1] 传入）。
_READ_STABLE_TAG_SNIPPET = """
import sys
from lib.stable_tag import read_stable_tag
value = read_stable_tag(sys.argv[1])
sys.stdout.write("" if value is None else value)
"""

# 一个合法的 40 位小写十六进制 commit SHA，用于决策与往返测试。
_VALID_SHA = "0123456789abcdef0123456789abcdef01234567"


class ShellScriptSyntaxTest(unittest.TestCase):
    """三个 shell 脚本存在且通过 ``bash -n`` 语法检查。"""

    def test_scripts_exist(self):
        for script in (_DEPLOY_SH, _VERIFY_SH, _ROLLBACK_SH):
            self.assertTrue(script.is_file(), f"脚本缺失: {script}")

    def test_scripts_pass_bash_syntax_check(self):
        bash = _find_bash()
        if bash is None:
            self.skipTest("当前环境未找到 bash，跳过 shell 语法检查（python 集成断言仍执行）")

        for script in (_DEPLOY_SH, _VERIFY_SH, _ROLLBACK_SH):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [bash, "-n", str(script)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{script.name} 未通过 bash -n 语法检查:\n{result.stderr}",
                )


class ServicesAllRunningIntegrationTest(unittest.TestCase):
    """deploy.sh 的 services_all_running 决策与退出码传播（R4.3）。"""

    def _ps_json(self, mapping: dict[str, str]) -> str:
        # 模拟 `docker compose ps --format json` 的逐行 JSON 输出。
        return "\n".join(
            json.dumps({"Service": name, "State": state})
            for name, state in mapping.items()
        )

    def test_all_four_services_running_exit_zero(self):
        ps = self._ps_json(
            {
                "backend": "running",
                "worker": "running",
                "web": "running",
                "redis": "running",
            }
        )
        result = _run_lib_snippet(
            _SERVICES_SNIPPET,
            stdin=ps,
            extra_env={"REQUIRED_SERVICES": "backend worker web redis"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_one_service_missing_exit_nonzero(self):
        # 缺少 redis -> 视为未全部 running -> 非零退出。
        ps = self._ps_json(
            {
                "backend": "running",
                "worker": "running",
                "web": "running",
            }
        )
        result = _run_lib_snippet(
            _SERVICES_SNIPPET,
            stdin=ps,
            extra_env={"REQUIRED_SERVICES": "backend worker web redis"},
        )
        self.assertNotEqual(result.returncode, 0, result.stderr)

    def test_one_service_not_running_exit_nonzero(self):
        # redis 状态非 running（exited）-> 非零退出。
        ps = self._ps_json(
            {
                "backend": "running",
                "worker": "running",
                "web": "running",
                "redis": "exited",
            }
        )
        result = _run_lib_snippet(
            _SERVICES_SNIPPET,
            stdin=ps,
            extra_env={"REQUIRED_SERVICES": "backend worker web redis"},
        )
        self.assertNotEqual(result.returncode, 0, result.stderr)


class RetrySucceedsIntegrationTest(unittest.TestCase):
    """rollback.sh 的 retry_succeeds + RetryConfig(5,10,10,60) 决策（R7.2）。"""

    def test_all_false_outcomes_exit_nonzero(self):
        # 5 次全部失败（max_retries=5）-> 非零退出。
        result = _run_lib_snippet(
            _RETRY_SNIPPET, "false", "false", "false", "false", "false"
        )
        self.assertNotEqual(result.returncode, 0, result.stderr)

    def test_true_within_window_exit_zero(self):
        # 第 3 次成功（仍在 max_retries=5 窗口内）-> 退出 0。
        result = _run_lib_snippet(
            _RETRY_SNIPPET, "false", "false", "true", "false"
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class DecideRollbackIntegrationTest(unittest.TestCase):
    """rollback.sh 的 decide_rollback 决策与退出码传播（R7.3）。"""

    def test_valid_sha_exit_zero(self):
        # 合法 Last_Stable_Tag -> 决定回滚 -> 退出 0。
        result = _run_lib_snippet(_DECIDE_ROLLBACK_SNIPPET, _VALID_SHA)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_exit_nonzero(self):
        # 空字符串（rollback.sh 中映射为 None）-> 跳过回滚 -> 非零退出。
        result = _run_lib_snippet(_DECIDE_ROLLBACK_SNIPPET, "")
        self.assertNotEqual(result.returncode, 0, result.stderr)

    def test_invalid_sha_exit_nonzero(self):
        # 非法 SHA（大写 + 过短）-> 跳过回滚 -> 非零退出。
        result = _run_lib_snippet(_DECIDE_ROLLBACK_SNIPPET, "NOTASHA")
        self.assertNotEqual(result.returncode, 0, result.stderr)


class StableTagRoundTripIntegrationTest(unittest.TestCase):
    """verify.sh 写入 + rollback.sh 读取 Last_Stable_Tag 的往返一致（R6.5 / R7.1）。"""

    def test_write_then_read_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # verify.sh 片段以 APP_DIR/state/last_stable_tag 为目标写入 IMAGE_TAG。
            write_result = _run_lib_snippet(
                _WRITE_STABLE_TAG_SNIPPET,
                extra_env={"APP_DIR": tmp_dir, "IMAGE_TAG": _VALID_SHA},
            )
            self.assertEqual(write_result.returncode, 0, write_result.stderr)

            state_path = os.path.join(tmp_dir, "state", "last_stable_tag")
            self.assertTrue(os.path.isfile(state_path), "状态文件未被写入")

            # rollback.sh 片段读取同一路径，应得到写入的 SHA（往返一致）。
            read_result = _run_lib_snippet(_READ_STABLE_TAG_SNIPPET, state_path)
            self.assertEqual(read_result.returncode, 0, read_result.stderr)
            self.assertEqual(read_result.stdout, _VALID_SHA)

    def test_read_missing_file_returns_empty(self):
        # 状态文件不存在（首次部署）-> read_stable_tag 返回 None -> 输出空串。
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_path = os.path.join(tmp_dir, "state", "last_stable_tag")
            read_result = _run_lib_snippet(_READ_STABLE_TAG_SNIPPET, missing_path)
            self.assertEqual(read_result.returncode, 0, read_result.stderr)
            self.assertEqual(read_result.stdout, "")


if __name__ == "__main__":
    unittest.main()
