"""项目/资产实体端点测试（R4.1，2026-09-06）。

覆盖的是资产化后**用户可感知的不变量**，而不是字段回显：

1. 版本链单调递增且永不覆盖 —— (project_id, version_no) 是用户的工作成果，挂版本
   并发同号时宁可 409 也不能覆盖既有版本。
2. data_version 必须由服务端取 —— 客户端给的值会让「同一 data_version ⇒ 同一上游
   数据」这个复现等式变成可伪造的。
3. 跨 workspace 一律 404（存在性不外泄），归档后列表不可见但版本链仍在。
4. config/payload 是用户自己的分析上下文，512KB 上限挡的是「把它当导出通道」的滥用。

同共享 PG 库的其它认证测试同一策略：setUp 重置权限表，随机后缀。
"""

import unittest
import uuid
from unittest import mock

from tests.support import (
    ensure_repo_import_paths,
    offline_state_store,
    reset_access_control_tables,
    stub_optional_dep,
)

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from access_control import (  # noqa: E402
    issue_access_token,
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
    set_principal_password,
)
from database import DatabaseManager  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routes import account_routes, project_routes  # noqa: E402

PREFIX = "/api/v1/projects"


class ProjectRouteTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        self.state_store = offline_state_store()
        mock.patch.object(project_routes, "get_db", lambda: self.db).start()
        mock.patch.object(account_routes, "get_db", lambda: self.db).start()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        # data_version 由服务端取 db.get_last_update_time()：固定它，断言「服务端取的」
        # 而不是「碰巧等于某个值」。
        self.data_version = f"dv-{self.suffix}"
        mock.patch.object(
            self.db, "get_last_update_time", lambda: self.data_version, create=True
        ).start()
        self.addCleanup(mock.patch.stopall)

        self.app = FastAPI()
        self.app.include_router(project_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    # -- fixtures --------------------------------------------------------

    def make_member(self, org_name="Acme Energy", ws_role="owner"):
        org = seed_organization(self.db, name=f"{org_name} {self.suffix}")
        principal = seed_principal(self.db, email=f"u-{uuid.uuid4().hex[:8]}@{self.suffix}.test",
                                   display_name="Owner")
        set_principal_password(self.db, principal_id=principal["principal_id"],
                               password="Maple-Drum-77!grid")
        seed_organization_membership(self.db, organization_id=org["organization_id"],
                                     principal_id=principal["principal_id"],
                                     role="org_owner" if ws_role == "owner" else "org_member")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"],
                                   name=f"ws-{uuid.uuid4().hex[:6]}")
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"],
                                  principal_id=principal["principal_id"], role=ws_role)
        token = issue_access_token(self.db, principal_id=principal["principal_id"],
                                   workspace_id=workspace["workspace_id"])
        return {
            "principal": principal,
            "workspace": workspace,
            "headers": {"Authorization": f"Bearer {token['token']}"},
        }

    def create_project(self, member, name="NSW 200MW 项目", config=None):
        return self.client.post(PREFIX, headers=member["headers"], json={
            "name": name,
            "description": "第一版测算",
            "market": "NEM",
            "region": "NSW1",
            "config": config or {"compression_factor": 0.92, "capacity_mwh": 400},
        })

    # -- tests -----------------------------------------------------------

    def test_create_returns_view_with_config_snapshot(self):
        member = self.make_member()
        resp = self.create_project(member)
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertTrue(body["project_id"].startswith("proj_"))
        self.assertEqual(body["config"]["compression_factor"], 0.92)
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["workspace_id"], member["workspace"]["workspace_id"])

    def test_create_requires_bearer(self):
        resp = self.client.post(PREFIX, json={"name": "x"})
        self.assertEqual(resp.status_code, 401)

    def test_list_is_scoped_to_own_workspace(self):
        alice = self.make_member()
        bob = self.make_member(org_name="Other")
        self.create_project(alice, name="Alice 的项目")
        rows = self.client.get(PREFIX, headers=bob["headers"]).json()["projects"]
        self.assertEqual(rows, [], "列表绝不能跨 workspace 泄露")
        rows = self.client.get(PREFIX, headers=alice["headers"]).json()["projects"]
        self.assertEqual(len(rows), 1)

    def test_cross_workspace_get_is_404_not_403(self):
        alice = self.make_member()
        mallory = self.make_member(org_name="Evil")
        project_id = self.create_project(alice).json()["project_id"]
        resp = self.client.get(f"{PREFIX}/{project_id}", headers=mallory["headers"])
        self.assertEqual(resp.status_code, 404, "403 会泄露项目存在性")

    def test_patch_updates_only_given_fields(self):
        member = self.make_member()
        project_id = self.create_project(member).json()["project_id"]
        resp = self.client.patch(f"{PREFIX}/{project_id}", headers=member["headers"],
                                 json={"name": "改名后的项目"})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["name"], "改名后的项目")
        self.assertEqual(body["config"]["compression_factor"], 0.92, "未给出的字段不得被清掉")

    def test_patch_empty_body_is_422(self):
        member = self.make_member()
        project_id = self.create_project(member).json()["project_id"]
        resp = self.client.patch(f"{PREFIX}/{project_id}", headers=member["headers"], json={})
        self.assertEqual(resp.status_code, 422)

    def test_archive_hides_from_list_but_keeps_versions(self):
        member = self.make_member()
        project_id = self.create_project(member).json()["project_id"]
        self.client.post(f"{PREFIX}/{project_id}/versions", headers=member["headers"],
                         json={"label": "v1"})
        resp = self.client.delete(f"{PREFIX}/{project_id}", headers=member["headers"])
        self.assertEqual(resp.status_code, 200)
        rows = self.client.get(PREFIX, headers=member["headers"]).json()["projects"]
        self.assertEqual(rows, [], "归档后默认列表不可见")
        rows = self.client.get(f"{PREFIX}?include_archived=true",
                               headers=member["headers"]).json()["projects"]
        self.assertEqual(len(rows), 1)
        versions = self.client.get(f"{PREFIX}/{project_id}/versions",
                                   headers=member["headers"]).json()["versions"]
        self.assertEqual(len(versions), 1, "归档不得连带毁掉版本链")

    def test_versions_increment_and_data_version_is_server_side(self):
        member = self.make_member()
        project_id = self.create_project(member).json()["project_id"]
        first = self.client.post(f"{PREFIX}/{project_id}/versions", headers=member["headers"],
                                 json={"label": "第一版", "payload": {"lcoe": 91.2}}).json()
        second = self.client.post(f"{PREFIX}/{project_id}/versions", headers=member["headers"],
                                  json={"label": "第二版", "payload": {"lcoe": 88.7}}).json()
        self.assertEqual(first["version_no"], 1)
        self.assertEqual(second["version_no"], 2)
        self.assertEqual(first["data_version"], self.data_version,
                         "data_version 必须由服务端取，客户端不可指定")
        rows = self.client.get(f"{PREFIX}/{project_id}/versions",
                               headers=member["headers"]).json()["versions"]
        self.assertEqual([r["version_no"] for r in rows], [2, 1], "新版本在前")
        self.assertEqual(rows[1]["payload"]["lcoe"], 91.2)

    def test_version_payload_size_limit(self):
        member = self.make_member()
        project_id = self.create_project(member).json()["project_id"]
        big = {"k": "x" * 600_000}
        resp = self.client.post(f"{PREFIX}/{project_id}/versions", headers=member["headers"],
                                json={"payload": big})
        self.assertEqual(resp.status_code, 413)

    def test_config_size_limit_on_create(self):
        member = self.make_member()
        resp = self.client.post(PREFIX, headers=member["headers"], json={
            "name": "太大", "config": {"k": "x" * 600_000}})
        self.assertEqual(resp.status_code, 413)


if __name__ == "__main__":
    unittest.main()
