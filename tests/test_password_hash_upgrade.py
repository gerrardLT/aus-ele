"""P0.6：PBKDF2 迭代数上调（120k → 600k）+ 登录成功后透明重哈希。

锁定的不是「跑得快」，而是四条不可回退的性质：
1. 新写入的哈希按当前迭代数，并把迭代数持久化（否则无法区分新旧）；
2. 存量 120k 哈希在升级后**仍能登录**（写死常量会把另一半账户永久锁在门外）；
3. 重哈希只在密码被验证正确之后发生（否则未认证请求就能写入攻击者选择的哈希）；
4. 重哈希失败不得打断已认证的登录（可用性边界）。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import uuid
from unittest import mock

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths, reset_access_control_tables

ensure_repo_import_paths()

import access_control
from access_control import (
    PBKDF2_LEGACY_ITERATIONS,
    PBKDF2_TARGET_ITERATIONS,
    _hash_password,
    _pbkdf2_iterations,
    _stored_iterations,
    login_with_password,
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
    set_principal_password,
)
from database import DatabaseManager


def _legacy_hash(password: str, salt: str) -> str:
    """迁移前的哈希：独立算一遍，而不是复用被测函数（避免自证）。"""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_LEGACY_ITERATIONS
    ).hex()


class Pbkdf2IterationConfigTests(unittest.TestCase):
    def _iters_with(self, raw):
        with mock.patch.dict(os.environ, {}, clear=False):
            if raw is None:
                os.environ.pop("AUS_ELE_PBKDF2_ITERATIONS", None)
            else:
                os.environ["AUS_ELE_PBKDF2_ITERATIONS"] = raw
            return _pbkdf2_iterations()

    def test_default_is_600k(self):
        self.assertEqual(self._iters_with(None), PBKDF2_TARGET_ITERATIONS)
        self.assertEqual(PBKDF2_TARGET_ITERATIONS, 600_000)

    def test_env_override_respected(self):
        self.assertEqual(self._iters_with("1000000"), 1_000_000)

    def test_downgrade_below_legacy_baseline_is_clamped(self):
        # 少写几个 0 是不可逆的降级：已按弱值写库的哈希之后无法退回强值验证
        self.assertEqual(self._iters_with("1000"), PBKDF2_LEGACY_ITERATIONS)
        self.assertEqual(self._iters_with("0"), PBKDF2_LEGACY_ITERATIONS)

    def test_non_numeric_and_blank_fall_back_to_default(self):
        self.assertEqual(self._iters_with("many"), PBKDF2_TARGET_ITERATIONS)
        self.assertEqual(self._iters_with(""), PBKDF2_TARGET_ITERATIONS)

    def test_stored_iterations_treats_dirty_values_as_legacy(self):
        for raw in (None, "", "abc", 0, 1000, -1):
            with self.subTest(pw_iters=raw):
                self.assertEqual(_stored_iterations({"pw_iters": raw}), PBKDF2_LEGACY_ITERATIONS)


class PasswordHashingTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        reset_access_control_tables(self.db)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("AUS_ELE_PBKDF2_ITERATIONS", None)
        self.addCleanup(self._env.stop)
        self.email = f"pw-{uuid.uuid4().hex[:8]}@example.test"

    def _principal(self):
        return seed_principal(self.db, email=self.email, display_name="PW")

    def test_hash_is_iteration_count_dependent(self):
        salt = "ab" * 16
        self.assertNotEqual(
            _hash_password("hunter2", salt, PBKDF2_LEGACY_ITERATIONS),
            _hash_password("hunter2", salt, PBKDF2_TARGET_ITERATIONS),
        )

    def test_set_password_persists_iterations_and_verifies(self):
        principal = set_principal_password(
            self.db, principal_id=self._principal()["principal_id"], password="hunter2-hunter2"
        )
        self.assertEqual(principal["pw_iters"], PBKDF2_TARGET_ITERATIONS)
        self.assertTrue(
            access_control._verify_password("hunter2-hunter2", principal),
            "自己设置的密码必须验得过",
        )
        self.assertFalse(access_control._verify_password("wrong-password", principal))


class LegacyHashUpgradeTests(unittest.TestCase):
    """存量 120k 账户的登录 + 透明升级全链路。"""

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        reset_access_control_tables(self.db)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("AUS_ELE_PBKDF2_ITERATIONS", None)
        self.addCleanup(self._env.stop)

        suffix = uuid.uuid4().hex[:8]
        self.email = f"legacy-{suffix}@example.test"
        self.password = "legacy-secret-1"
        self.organization = seed_organization(self.db, name=f"Legacy {suffix}")
        self.workspace = seed_workspace(
            self.db, organization_id=self.organization["organization_id"], name="Primary"
        )
        principal = seed_principal(self.db, email=self.email, display_name="Legacy")
        seed_organization_membership(
            self.db, organization_id=self.organization["organization_id"],
            principal_id=principal["principal_id"], role="member",
        )
        seed_workspace_membership(
            self.db, workspace_id=self.workspace["workspace_id"],
            principal_id=principal["principal_id"], role="owner",
        )
        # 手工铸一个迁移前状态的行：120k 哈希 + pw_iters 为 NULL
        self.salt = "cd" * 16
        self.db.upsert_principal(
            {
                **principal,
                "password_salt": self.salt,
                "password_hash": _legacy_hash(self.password, self.salt),
                "pw_iters": None,
            }
        )
        self.legacy_hash = self.db.fetch_principal(principal["principal_id"])["password_hash"]
        self.principal_id = principal["principal_id"]

    def test_legacy_row_can_still_log_in(self):
        result = login_with_password(
            self.db, email=self.email, password=self.password,
            workspace_id=self.workspace["workspace_id"],
        )
        self.assertIn("session_token", result)

    def test_login_upgrades_stored_iterations_and_hash(self):
        login_with_password(
            self.db, email=self.email, password=self.password,
            workspace_id=self.workspace["workspace_id"],
        )
        row = self.db.fetch_principal(self.principal_id)
        self.assertEqual(row["pw_iters"], PBKDF2_TARGET_ITERATIONS)
        self.assertNotEqual(row["password_hash"], self.legacy_hash, "哈希必须真的被重算过")
        self.assertEqual(
            row["password_hash"],
            _hash_password(self.password, self.salt, PBKDF2_TARGET_ITERATIONS),
        )

    def test_second_login_still_works_after_upgrade(self):
        for _ in range(2):
            login_with_password(
                self.db, email=self.email, password=self.password,
                workspace_id=self.workspace["workspace_id"],
            )
        row = self.db.fetch_principal(self.principal_id)
        self.assertEqual(row["pw_iters"], PBKDF2_TARGET_ITERATIONS)

    def test_upgrade_is_idempotent_once_at_target(self):
        login_with_password(
            self.db, email=self.email, password=self.password,
            workspace_id=self.workspace["workspace_id"],
        )
        upgraded = self.db.fetch_principal(self.principal_id)
        result = login_with_password(
            self.db, email=self.email, password=self.password,
            workspace_id=self.workspace["workspace_id"],
        )
        self.assertIn("session_token", result)
        self.assertEqual(self.db.fetch_principal(self.principal_id)["password_hash"], upgraded["password_hash"])
        upgrades = [
            item for item in self.db.fetch_audit_logs(limit=100)
            if item["action"] == "principal.password_hash_upgraded"
        ]
        self.assertEqual(len(upgrades), 1, "已到目标迭代数后不得每次登录都重哈希")

    def test_upgrade_writes_audit_with_iteration_span(self):
        login_with_password(
            self.db, email=self.email, password=self.password,
            workspace_id=self.workspace["workspace_id"],
        )
        upgrades = [
            item for item in self.db.fetch_audit_logs(limit=100)
            if item["action"] == "principal.password_hash_upgraded"
        ]
        self.assertEqual(len(upgrades), 1)
        detail = upgrades[0]["detail_json"]
        self.assertEqual(detail["from_iters"], PBKDF2_LEGACY_ITERATIONS)
        self.assertEqual(detail["to_iters"], PBKDF2_TARGET_ITERATIONS)

    def test_wrong_password_does_not_rewrite_hash(self):
        # 关键性质：未认证的凭据不得获得改写哈希的能力，否则该分支退化成账户接管
        with self.assertRaises(HTTPException) as ctx:
            login_with_password(
                self.db, email=self.email, password="attacker-choice",
                workspace_id=self.workspace["workspace_id"],
            )
        self.assertEqual(ctx.exception.status_code, 401)
        row = self.db.fetch_principal(self.principal_id)
        self.assertEqual(row["password_hash"], self.legacy_hash)
        self.assertIsNone(row["pw_iters"])

    def test_rehash_failure_does_not_break_authenticated_login(self):
        # 用户已认证：写侧故障只能降级为 warning，不能把合法会话踢回门外
        boom = mock.Mock(side_effect=RuntimeError("pg down"))
        original = self.db.upsert_principal
        self.db.upsert_principal = boom
        try:
            result = login_with_password(
                self.db, email=self.email, password=self.password,
                workspace_id=self.workspace["workspace_id"],
            )
        finally:
            self.db.upsert_principal = original
        self.assertIn("session_token", result)
        # 未升级成功 → 下次登录仍会尝试（幂等，不丢状态）
        self.assertIsNone(self.db.fetch_principal(self.principal_id)["pw_iters"])
        self.assertIsNotNone(original)


if __name__ == "__main__":
    unittest.main()
