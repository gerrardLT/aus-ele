"""后端品牌一致性锁（R2.1/R2.6，2026-09-06）。

与 ``web/src/lib/brandConsistency.test.js`` 各锁一侧；``backend/brand.py`` 的 docstring 承诺了
这个文件的存在，所以它不能只是一份「顺手加的测试」—— 它是一条已被引用的契约。

为什么后端单独要一道锁（前端那道不够）：后端有**会发到用户收件箱**的字符串（密码重置主题、
邮箱验证正文、定时报告主题）。邮件主题里带着第三方数据机构的缩写，等于每一封外发邮件都在
替我们重复那个法务问题；而这类漏改在 CI 里不会让任何功能测试变红 —— 没有任何测试会去读
mailer 收到的 subject。

被禁字面量不写在本文件里，而是从前端常量层 ``FORMER_BRAND_NAMES`` 解析出来：单一数据源，
否则「加一个旧名」要改两个地方，而第二个地方一定会被忘记。
"""

import re
import unittest
from pathlib import Path

from tests.support import ensure_repo_import_paths

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
BRAND_PY = BACKEND / "brand.py"
BRAND_JS = REPO_ROOT / "web" / "src" / "lib" / "brand.js"

#: 常量层自身是唯一豁免：解释「为什么禁止写 X」的规则必须能说 X。
ALLOWED_FILES = {BRAND_PY}

ensure_repo_import_paths()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _former_names() -> list[str]:
    """从前端常量层解析旧品牌名（与前端那道锁共用同一数据源）。"""
    match = re.search(r"FORMER_BRAND_NAMES\s*=\s*Object\.freeze\(\[(.*?)\]\)", _read(BRAND_JS), re.S)
    if not match:
        raise AssertionError("web/src/lib/brand.js 必须导出 FORMER_BRAND_NAMES，否则两道锁同时失效")
    names = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
    assert names, "FORMER_BRAND_NAMES 解析为空 —— 扫描器会静默放行任何东西"
    return names


def _python_files():
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        yield path


class BackendBrandTests(unittest.TestCase):
    def test_no_former_product_name_survives_in_backend(self):
        hits = []
        for path in _python_files():
            if path in ALLOWED_FILES:
                continue
            body = _read(path)
            for former in _former_names():
                if former in body:
                    hits.append(f"{path.relative_to(REPO_ROOT)} :: {former}")
        self.assertEqual(hits, [], f"后端存在未接管的产品名硬编码：\n" + "\n".join(hits))

    def test_brand_layer_is_actually_imported(self):
        """只有常量、没有读者的品牌层是装饰：改名照样漏。"""
        consumers = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in _python_files()
            if path != BRAND_PY and re.search(r"^\s*(from brand import|import brand\b)", _read(path), re.M)
        ]
        # 三处「会发出去给用户看」的位点必须都在名单里（Spec R2.2）
        for expected in ("backend/app.py", "backend/services/report_scheduler.py", "backend/scripts/seed_admin.py"):
            self.assertIn(expected, consumers, f"{expected} 绕过品牌常量层")
        self.assertGreaterEqual(len(consumers), 4)

    def test_user_facing_email_strings_do_not_hardcode_the_prefix(self):
        """邮件主题前缀必须由 ``brand.subject()`` 生成。

        本轮真实漏在这：验证邮件把 ``[天枢]`` 写死在源码里，同时正文里还留着第二个英文名
        （``Dubhe`` —— 品牌候选 #2，从未被采纳）。前缀写死的后果不是报错，而是「改了
        brand.py 但用户邮箱里的名字没改」，即改名回滚开关是假的。
        """
        offenders = []
        for path in _python_files():
            if path in ALLOWED_FILES:
                continue
            body = _read(path)
            if re.search(r"[\[【]\s*天枢\s*[\]】]", body):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [], f"前缀必须走 brand.EMAIL_SUBJECT_PREFIX：{offenders}")

    def test_english_brand_name_is_single_valued(self):
        """英文名只允许一个值。两个英文名并存 = 用户在邮件和网页看到不同的产品。"""
        py = _read(BRAND_PY)
        en = re.search(r'BRAND_NAME_EN\s*=\s*["\']([^"\']+)["\']', py).group(1)
        js = _read(BRAND_JS)
        js_en = re.search(r"BRAND_NAME_EN\s*=\s*['\"]([^'\"]+)['\"]", js).group(1)
        self.assertEqual(en, js_en)
        for path in _python_files():
            if path in ALLOWED_FILES:
                continue
            body = _read(path)
            for rival in re.findall(r"[（(]\s*([A-Z][a-z]{3,12})\s*[）)]", body):
                if rival in {"Dubhe", "Gridlens", "Sparkspread", "Voltpath", "Ampereon", "Merivolt"}:
                    self.fail(f"{path.relative_to(REPO_ROOT)} 出现了未被采纳的品牌候选名 {rival}")

    def test_email_subject_prefix_is_byte_identical_across_layers(self):
        py = _read(BRAND_PY)
        prefix = re.search(r"EMAIL_SUBJECT_PREFIX\s*=\s*f?['\"](.+?)['\"]", py).group(1)
        resolved = prefix.replace("{BRAND_NAME_ZH}", "天枢").replace("{BRAND_NAME_EN}", "Tianshu")
        js_prefix = re.search(r"EMAIL_SUBJECT_PREFIX\s*=\s*['\"]([^'\"]+)['\"]", _read(BRAND_JS)).group(1)
        self.assertEqual(resolved, js_prefix)

    def test_data_source_name_stays_while_product_name_changes(self):
        """Spec R2.3 地雷 1：``agent/prompts.py`` 的 system prompt 必须同时含新品牌与 AEMO。

        ``tests/test_agent_orchestrator.py`` 硬断言 prompt 含 "AEMO"。把它当成「残留旧品牌」
        删掉会红一条测试，而正确的理解是：**AEMO 在这里是数据源名，不是产品名**。
        """
        prompt = _read(BACKEND / "agent" / "prompts.py")
        self.assertIn("天枢", prompt)
        self.assertIn("AEMO", prompt)

    def test_audit_action_names_are_brand_free_and_untouched(self):
        """Spec R2.7：审计 action 名与品牌零耦合，改名不得顺手改写它们。"""
        from access_control import ROLE_PERMISSIONS  # noqa: F401  —— 顺带确认模块可导入

        ac = _read(BACKEND / "access_control.py")
        actions = set(re.findall(r'action\s*=\s*["\']([a-z_.]+)["\']', ac))
        self.assertTrue(actions, "解析不到 audit action 名，这条断言已经空转")
        for action in actions:
            self.assertNotIn("天枢", action)
            self.assertNotIn("aemo", action.lower(), f"审计 action {action} 把数据源名写进了结构化标识")


if __name__ == "__main__":
    unittest.main()
