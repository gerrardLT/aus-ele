"""P0.2 匿名 bootstrap 角色降级（2026-09-05 公测产品化改造）。

验证两件事：
1. 默认角色由 ``owner`` 降为 ``viewer``，且可用 ``AUS_ELE_BOOTSTRAP_ROLE`` 零代码回滚；
2. **不需要「一次性降权 UPDATE」**——``upsert_workspace_membership`` 的
   ``ON CONFLICT ... DO UPDATE SET role=excluded.role`` 会让既有 owner 行在下一次
   bootstrap 请求时自动对齐。本测试用「先植入 owner 行 → 跑 identity 确保 → 断言变
   viewer」把这条推理变成证据（规划原文假设需要手写 UPDATE，此为对规划的实证修正）。
"""

import os
import sys
import unittest

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from access_control import ROLE_PERMISSIONS, BOOTSTRAP_PRINCIPAL_ID
from database import DatabaseManager
from routes import auth_routes


class BootstrapRoleResolutionTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("AUS_ELE_BOOTSTRAP_ROLE", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("AUS_ELE_BOOTSTRAP_ROLE", None)
        else:
            os.environ["AUS_ELE_BOOTSTRAP_ROLE"] = self._saved

    def test_default_is_viewer(self):
        self.assertEqual(auth_routes._bootstrap_role(), "viewer")

    def test_env_override_is_respected(self):
        os.environ["AUS_ELE_BOOTSTRAP_ROLE"] = "OWNER"
        self.assertEqual(auth_routes._bootstrap_role(), "owner", "回滚路径 C 必须可用（零代码）")

    def test_invalid_value_fails_closed_to_viewer(self):
        os.environ["AUS_ELE_BOOTSTRAP_ROLE"] = "superuser"
        self.assertEqual(auth_routes._bootstrap_role(), "viewer", "配错不得意外提权")

    def test_viewer_carries_no_permission_bits(self):
        self.assertEqual(ROLE_PERMISSIONS["viewer"], set(), "viewer 若被加入权限位，本降级即失效")

    def test_bootstrap_principal_id_constant_is_shared(self):
        self.assertEqual(auth_routes._BOOTSTRAP_PR, BOOTSTRAP_PRINCIPAL_ID)


class BootstrapRoleRealignmentTests(unittest.TestCase):
    """既有 owner 行的自动对齐（PG-only，直连开发库；用固定 ID 无需清理额外数据）。"""

    def setUp(self):
        self._saved = os.environ.pop("AUS_ELE_BOOTSTRAP_ROLE", None)
        self.db = DatabaseManager(None)
        # 前置条件自证（2026-09-05 R0b）：本类用固定的 ws_default / m_webbootstrap，
        # 而其他认证测试的 reset_access_control_tables 会清掉这两行 → 直接插
        # workspace_membership 会撞 FK。_ensure_bootstrap_identity 是幂等的，
        # 让每个用例都能独立起跑，不再依赖执行顺序。
        auth_routes._ensure_bootstrap_identity(self.db)
        self._prior = self.db.fetch_workspace_membership(auth_routes._BOOTSTRAP_WS, BOOTSTRAP_PRINCIPAL_ID)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("AUS_ELE_BOOTSTRAP_ROLE", None)
        else:
            os.environ["AUS_ELE_BOOTSTRAP_ROLE"] = self._saved
        # 还原测试前的角色，避免影响其它用例对 ws_default 的期望
        if self._prior is not None:
            self.db.upsert_workspace_membership(self._prior)

    def test_existing_owner_row_is_realigned_without_manual_update(self):
        # 植入历史行为：owner（模拟已部署库中的 m_webbootstrap 行）
        self.db.upsert_workspace_membership(
            {
                "membership_id": "m_webbootstrap",
                "workspace_id": auth_routes._BOOTSTRAP_WS,
                "principal_id": BOOTSTRAP_PRINCIPAL_ID,
                "role": "owner",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
        self.assertEqual(
            self.db.fetch_workspace_membership(auth_routes._BOOTSTRAP_WS, BOOTSTRAP_PRINCIPAL_ID)["role"],
            "owner",
        )

        auth_routes._ensure_bootstrap_identity(self.db)

        row = self.db.fetch_workspace_membership(auth_routes._BOOTSTRAP_WS, BOOTSTRAP_PRINCIPAL_ID)
        self.assertEqual(row["role"], "viewer", "既有 owner 行未对齐 → 规划假设的「一次性 UPDATE」确实必要")
        self.assertEqual(row["membership_id"], "m_webbootstrap", "对齐不得新建行（幂等）")

    def test_rollback_env_restores_owner(self):
        os.environ["AUS_ELE_BOOTSTRAP_ROLE"] = "owner"
        auth_routes._ensure_bootstrap_identity(self.db)
        row = self.db.fetch_workspace_membership(auth_routes._BOOTSTRAP_WS, BOOTSTRAP_PRINCIPAL_ID)
        self.assertEqual(row["role"], "owner")

        os.environ["AUS_ELE_BOOTSTRAP_ROLE"] = "viewer"
        auth_routes._ensure_bootstrap_identity(self.db)
        row = self.db.fetch_workspace_membership(auth_routes._BOOTSTRAP_WS, BOOTSTRAP_PRINCIPAL_ID)
        self.assertEqual(row["role"], "viewer", "双向幂等：来回切 env 都能对齐")


if __name__ == "__main__":
    unittest.main()
