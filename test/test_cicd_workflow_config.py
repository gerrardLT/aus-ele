"""CI/CD 工作流配置检查（冒烟 / 配置检查，非属性测试）。

解析 `.github/workflows/ci.yml` 与 `Dockerfile.backend`，断言：
  1. Python 版本对齐（R1.5/R8.2）：workflow env.PYTHON_VERSION == "3.11"
     且 Dockerfile.backend 使用 `python:3.11-slim`，二者一致。
  2. 触发矩阵（R1.1/R1.2/R2.1/R2.2）：push 与 pull_request 均针对 main 与 develop。
  3. CD 门控（R4.6）：build-push 与 deploy 作业的 `if` 含
     `github.ref == 'refs/heads/main'` 且 `github.event_name == 'push'`。
  4. 前端测试修复（R8.1）：「Run frontend tests」步骤不含 `|| true`。

Validates: Requirements 1.1, 1.2, 2.1, 2.2, 4.6, 8.1, 8.2
"""

import re
import unittest
from pathlib import Path

import yaml

# 仓库根目录（test/ 的上一级）
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE_BACKEND_PATH = REPO_ROOT / "Dockerfile.backend"

EXPECTED_PYTHON_VERSION = "3.11"
EXPECTED_BRANCHES = {"main", "develop"}
CD_GATED_JOBS = ("build-push", "deploy")


def _load_workflow() -> dict:
    with WORKFLOW_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _workflow_on(workflow: dict) -> dict:
    """获取 `on:` 段。

    PyYAML 会把未加引号的 `on` 键解析为布尔 True（YAML 1.1），
    因此需同时兼容字符串键 "on" 与布尔键 True。
    """
    if "on" in workflow:
        return workflow["on"]
    if True in workflow:
        return workflow[True]
    raise AssertionError("工作流缺少 `on:` 触发段")


class TestPythonVersionAlignment(unittest.TestCase):
    """R1.5/R8.2：workflow Python 版本与 Dockerfile.backend 对齐。"""

    def test_workflow_python_version_is_311(self) -> None:
        workflow = _load_workflow()
        env = workflow.get("env", {})
        self.assertIn("PYTHON_VERSION", env, "workflow env 缺少 PYTHON_VERSION")
        self.assertEqual(
            str(env["PYTHON_VERSION"]),
            EXPECTED_PYTHON_VERSION,
            "workflow env.PYTHON_VERSION 必须为 3.11",
        )

    def test_dockerfile_backend_uses_python_311(self) -> None:
        content = DOCKERFILE_BACKEND_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            content,
            r"^FROM\s+python:3\.11-slim\b",
            "Dockerfile.backend 必须基于 python:3.11-slim",
        )

    def test_versions_match(self) -> None:
        workflow = _load_workflow()
        wf_version = str(workflow.get("env", {}).get("PYTHON_VERSION", ""))

        content = DOCKERFILE_BACKEND_PATH.read_text(encoding="utf-8")
        match = re.search(r"FROM\s+python:(\d+\.\d+)-slim", content)
        self.assertIsNotNone(match, "无法从 Dockerfile.backend 解析 python 版本")
        docker_version = match.group(1)

        self.assertEqual(
            wf_version,
            docker_version,
            "workflow PYTHON_VERSION 与 Dockerfile.backend 的 python 版本必须一致",
        )


class TestTriggerMatrix(unittest.TestCase):
    """R1.1/R1.2/R2.1/R2.2：push 与 pull_request 针对 main 与 develop。"""

    def test_push_triggers_main_and_develop(self) -> None:
        on = _workflow_on(_load_workflow())
        self.assertIn("push", on, "工作流必须监听 push 事件")
        branches = set(on["push"].get("branches", []))
        self.assertTrue(
            EXPECTED_BRANCHES.issubset(branches),
            f"push 必须覆盖 {EXPECTED_BRANCHES}，实际 {branches}",
        )

    def test_pull_request_triggers_main_and_develop(self) -> None:
        on = _workflow_on(_load_workflow())
        self.assertIn("pull_request", on, "工作流必须监听 pull_request 事件")
        branches = set(on["pull_request"].get("branches", []))
        self.assertTrue(
            EXPECTED_BRANCHES.issubset(branches),
            f"pull_request 必须覆盖 {EXPECTED_BRANCHES}，实际 {branches}",
        )


class TestCdGating(unittest.TestCase):
    """R4.6：CD 作业仅在 main 分支 push 时运行。"""

    def test_cd_jobs_gated_on_main_push(self) -> None:
        jobs = _load_workflow().get("jobs", {})
        for job_name in CD_GATED_JOBS:
            self.assertIn(job_name, jobs, f"工作流缺少 CD 作业 {job_name}")
            if_expr = jobs[job_name].get("if", "")
            self.assertIn(
                "github.ref == 'refs/heads/main'",
                if_expr,
                f"作业 {job_name} 的 if 必须限定 main 分支",
            )
            self.assertIn(
                "github.event_name == 'push'",
                if_expr,
                f"作业 {job_name} 的 if 必须限定 push 事件",
            )


class TestFrontendTestFix(unittest.TestCase):
    """R8.1：前端测试步骤不得用 `|| true` 吞掉失败。"""

    def test_run_frontend_tests_no_swallow(self) -> None:
        jobs = _load_workflow().get("jobs", {})
        self.assertIn("frontend", jobs, "工作流缺少 frontend 作业")
        steps = jobs["frontend"].get("steps", [])
        target = [s for s in steps if s.get("name") == "Run frontend tests"]
        self.assertTrue(target, "frontend 作业缺少 'Run frontend tests' 步骤")
        for step in target:
            run = step.get("run", "")
            self.assertNotIn(
                "|| true",
                run,
                "'Run frontend tests' 步骤不得包含 `|| true`（应真实传播失败）",
            )


if __name__ == "__main__":
    unittest.main()
