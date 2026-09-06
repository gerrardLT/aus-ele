"""注册密码策略单测（R1.1，2026-09-06）。

只测注册侧策略；既有三条设密入口（邀请接受/自助改密/密码重置）仍是 ``min_length=8``，
那是刻意保留的不一致（理由写在 services/password_policy.py 模块 docstring），
本文件不把它们一起断言成 12，以免测试变成「未来的期望」而不是「现在的契约」。
"""

import os
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fastapi import HTTPException  # noqa: E402

from services import password_policy  # noqa: E402


class PasswordPolicyTests(unittest.TestCase):
    def assertAccepts(self, password, **kw):
        self.assertEqual(password_policy.evaluate_password(password=password, **kw), [])

    def assertRejects(self, password, **kw):
        self.assertTrue(password_policy.evaluate_password(password=password, **kw),
                        f"expected rejection for {password!r}")

    def test_strong_passphrase_accepted(self):
        self.assertAccepts("correct-horse-battery-staple")
        self.assertAccepts("Ny7!maple syrup drum")

    def test_below_min_length_rejected(self):
        self.assertRejects("Abc123!x", email="u@example.com")  # 8 位：旧入口能过，注册不行

    def test_min_length_floor_ignores_weakening_env(self):
        """把策略配成 1 位等于关掉它 —— 下界必须钳在模块默认。"""
        with mock.patch.dict(os.environ, {"AUS_ELE_PASSWORD_MIN_LENGTH": "1"}):
            self.assertAccepts("correct-horse-battery")
            self.assertRejects("short1!")

    def test_max_length_bounds_pbkdf2_cost(self):
        long_pw = "Aa1!" + "x" * 300
        self.assertTrue(any("不能超过" in r for r in
                            password_policy.evaluate_password(password=long_pw)))

    def test_common_passwords_rejected_even_when_long_enough(self):
        for value in ("Password123!", "password123456", "1234567890123"):
            self.assertRejects(value)

    def test_email_and_name_substrings_rejected(self):
        self.assertRejects("AdaLovelace!2026", email="ada@analytical.co",
                           display_name="Ada Lovelace")
        self.assertRejects("Drum2026Analytical", email="ada.lovelace@analytical.co")

    def test_user_tokens_shorter_than_four_chars_are_ignored(self):
        """比对阈值 4 字符是刻意的：3 字符的本地段/名字会在大量正常口令里偶然命中。"""
        self.assertAccepts("Ada9Qz!x7Kd2r", email="ada@analytical.co", display_name="Ada")
        self.assertAccepts("Qz!7Kd2an99bb", email="an@analytical.co")

    def test_single_character_class_rejected(self):
        self.assertRejects("onlylowerwordletters")
        self.assertRejects("aaaaaaaaaaaaaa")
        # 纯数字没有「够长就豁免」这条路：两类字符规则把它一并覆盖
        self.assertRejects("123456789012")
        self.assertRejects("12345678901234567890")

    def test_keyboard_row_rejected_but_substring_ok(self):
        self.assertRejects("qwertyuiop12")
        self.assertRejects("poiuytrewq99")
        self.assertRejects("1234567890abc!")  # 数字行整行出现在前缀
        # 常见词 + 数字/符号的变体必须被拒：只做整串比对时这是最大的漏口
        self.assertRejects("Password123!")
        self.assertRejects("WELCOME@2026")
        # 20 位以上不再按词干判弱（攻击成本已不在同一量级）
        self.assertAccepts("password-orchard-vault-9f")

    def test_reasons_are_all_returned_not_just_first(self):
        reasons = password_policy.evaluate_password(password="short", email="bob@x.com", display_name="Bob")
        self.assertGreaterEqual(len(reasons), 2)

    def test_assert_raises_422_with_structured_errors(self):
        with self.assertRaises(HTTPException) as ctx:
            password_policy.assert_registration_password(password="weak", email="u@example.com")
        self.assertEqual(ctx.exception.status_code, 422)
        detail = ctx.exception.detail
        self.assertEqual(detail["code"], "weak_password")
        self.assertTrue(detail["errors"])

    def test_assert_returns_password_when_ok(self):
        self.assertEqual(
            password_policy.assert_registration_password(password="Maple-Drum-77!"),
            "Maple-Drum-77!",
        )

    def test_empty_password_rejected(self):
        self.assertRejects("")
        self.assertRejects(None)


if __name__ == "__main__":
    unittest.main()
