"""组织自助管理端点测试（R1.4，2026-09-06）。

覆盖的是**越权面**而不是 CRUD 表单：跨租户读取、匿名 bootstrap 写入、域名验证凭据外泄、
owner 移交所需权限位、邀请角色白名单、审计流水的组织隔离。

DatabaseManager 为 PG-only 且所有测试共享同一个库 → 邮箱带随机后缀，且 setUp 走
``reset_access_control_tables`` 清空认证/RBAC 表（本文件只碰这些表，绝不碰行情数据）。
"""

import datetime
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
    BOOTSTRAP_PRINCIPAL_ID,
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
from routes import account_routes, org_routes  # noqa: E402

PASSWORD = "Maple-Drum-77!grid"
ORGS_PREFIX = "/api/v1/organizations"


class OrgRoutesTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        # 一个测试一个 store 实例：生产里 get_state_store() 返回模块级单例，若每次调用
        # 都新建，限流窗口永远数不到第二次请求（限流测试假绿）。account_routes 的邀请接受
        # 限流是**函数内惰性 import**，所以桩必须打在 shared_state 模块本身，而不是
        # account_routes 的名字空间（那里根本没有 get_state_store 这个属性）。
        self.state_store = offline_state_store()
        mock.patch.object(org_routes, "get_db", lambda: self.db).start()
        mock.patch.object(account_routes, "get_db", lambda: self.db).start()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        self.addCleanup(mock.patch.stopall)

        self.app = FastAPI()
        self.app.include_router(org_routes.router)
        # account_routes 也挂上：组织邀请的「受邀者能不能登录」只能靠真实打一次登录端点
        # 来证明（见 test_org_invitee_can_actually_sign_in_after_accepting）。
        self.app.include_router(account_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    # -- fixtures --------------------------------------------------------

    def make_org(self, name="Acme Energy"):
        return seed_organization(self.db, name=name)

    def make_member(self, org, *, org_role, email=None):
        """建 principal + 组织成员身份，返回该成员（含真实 Bearer 头）。

        令牌走 ``issue_access_token`` 而非 ``dependency_overrides``：被测的是路由层，
        伪造 actor 字典等于自己给自己发通行证，守卫一旦写错这里也照样绿。
        """
        email = email or f"u-{uuid.uuid4().hex[:8]}@{self.suffix}.test"
        principal = seed_principal(self.db, email=email, display_name="Member")
        set_principal_password(self.db, principal_id=principal["principal_id"], password=PASSWORD)
        seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=principal["principal_id"],
            role=org_role,
        )
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Bind")
        seed_workspace_membership(
            self.db,
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )
        token = issue_access_token(
            self.db,
            principal_id=principal["principal_id"],
            workspace_id=workspace["workspace_id"],
        )
        return {
            "email": email,
            "principal": principal,
            "workspace": workspace,
            "headers": {"Authorization": f"Bearer {token['token']}"},
        }

    def org_path(self, org, suffix=""):
        return f"{ORGS_PREFIX}/{org['organization_id']}{suffix}"

    # -- 认证与租户隔离 --------------------------------------------------

    def test_missing_token_is_401_not_in_process_read(self):
        """无 Bearer 不能退化成「进程内直调即可读」（admin 端点的旧宽松语义）。"""
        org = self.make_org()

        res = self.client.get(self.org_path(org))

        self.assertEqual(res.status_code, 401)

    def test_foreign_organization_and_nonexistent_share_one_code(self):
        """陌生组织与不存在的组织返回同一个码，否则本端点沦为 organization_id 枚举探针。"""
        mine = self.make_org("Mine")
        theirs = self.make_org("Theirs")
        me = self.make_member(mine, org_role="org_owner")

        foreign = self.client.get(self.org_path(theirs), headers=me["headers"])
        missing = self.client.get(f"{ORGS_PREFIX}/org_nope_{self.suffix}", headers=me["headers"])

        self.assertEqual(foreign.status_code, 401)
        self.assertEqual(missing.status_code, foreign.status_code)

    def test_org_member_cannot_read_member_roster(self):
        """名册含同事邮箱 = 组织架构信息，org_member 无 member_manage。"""
        org = self.make_org()
        self.make_member(org, org_role="org_admin")
        member = self.make_member(org, org_role="org_member")

        res = self.client.get(self.org_path(org, "/members"), headers=member["headers"])

        self.assertEqual(res.status_code, 403)

    def test_org_admin_can_read_roster(self):
        org = self.make_org()
        admin = self.make_member(org, org_role="org_admin")
        invited = self.make_member(org, org_role="org_member")

        res = self.client.get(self.org_path(org, "/members"), headers=admin["headers"])

        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["total"], 2)
        emails = {item["principal"]["email"] for item in body["items"]}
        self.assertIn(invited["email"], emails)

    def test_overview_exposes_my_role_for_any_member(self):
        """前端 RBAC 入口门控依赖这个字段；缺了它真 org_owner 也看不到管理入口。"""
        org = self.make_org("North Grid")
        member = self.make_member(org, org_role="org_member")

        res = self.client.get(self.org_path(org), headers=member["headers"])

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "North Grid")
        self.assertEqual(res.json()["my_role"], "org_member")
        self.assertEqual(res.json()["member_count"], 1)

    def test_list_my_organizations_excludes_unaffiliated(self):
        mine = self.make_org("Mine")
        self.make_org("NotMine")
        member = self.make_member(mine, org_role="org_member")

        res = self.client.get(ORGS_PREFIX, headers=member["headers"])

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            [i["organization_id"] for i in res.json()["items"]], [mine["organization_id"]]
        )

    # -- 匿名 bootstrap 写守卫（P0.1） ----------------------------------

    def test_bootstrap_identity_cannot_write_org_endpoints(self):
        """web-session 引导身份即便持有真实令牌、即便在组织里是 org_owner，也不能写。

        这是 P0.1 的原始缺陷形状：ws_default 的匿名 owner。守卫按 principal_id 判定，
        与角色解耦，所以这里刻意给它最高角色 —— 若实现改回看 role，本测试立刻红。
        """
        org = self.make_org()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        self.db.upsert_principal(
            {
                "principal_id": BOOTSTRAP_PRINCIPAL_ID,
                "email": f"bootstrap-{self.suffix}@websession.local",
                "display_name": "Anonymous Browser",
                "created_at": now,
                "updated_at": now,
            }
        )
        seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=BOOTSTRAP_PRINCIPAL_ID,
            role="org_owner",
        )
        ws = seed_workspace(self.db, organization_id=org["organization_id"], name="AnonWS")
        seed_workspace_membership(
            self.db, workspace_id=ws["workspace_id"], principal_id=BOOTSTRAP_PRINCIPAL_ID, role="owner"
        )
        token = issue_access_token(
            self.db, principal_id=BOOTSTRAP_PRINCIPAL_ID, workspace_id=ws["workspace_id"]
        )
        headers = {"Authorization": f"Bearer {token['token']}"}

        writes = [
            (self.org_path(org, "/invites"), {"email": f"x-{self.suffix}@evil.test", "target_role": "org_admin"}),
            (self.org_path(org, "/domains"), {"domain": f"stolen-{self.suffix}.test"}),
            (self.org_path(org, "/owner-transfer"), {"new_owner_principal_id": BOOTSTRAP_PRINCIPAL_ID}),
        ]
        for path, body in writes:
            res = self.client.post(path, json=body, headers=headers)
            self.assertEqual(res.status_code, 403, f"{path} -> {res.status_code} {res.text}")

        self.assertEqual(self.db.list_membership_invites(org["organization_id"]), [])
        self.assertEqual(self.db.list_organization_domains(org["organization_id"]), [])

    # -- 域名：验证凭据绝不外泄（P0.3 信任锚） --------------------------

    def test_domain_listing_never_leaks_verification_token(self):
        """能列出域名的人若能看到 token，就能直接完成验证挑战 → auto_join 白送。"""
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")
        created = self.client.post(
            self.org_path(org, "/domains"),
            json={"domain": f"acme-{self.suffix}.test", "join_mode": "invite_only"},
            headers=owner["headers"],
        )
        self.assertEqual(created.status_code, 200, created.text)
        domain_id = created.json()["domain_id"]
        # 库里真的放一个挑战 token —— 断言的是「视图层剔除」，不是「列不存在」
        row = dict(self.db.fetch_organization_domain(domain_id))
        row["verification_token"] = "SECRET-TOKEN-XYZ"
        self.db.upsert_organization_domain(row)
        self.assertEqual(self.db.fetch_organization_domain(domain_id)["verification_token"], "SECRET-TOKEN-XYZ")

        res = self.client.get(self.org_path(org, "/domains"), headers=owner["headers"])

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("SECRET-TOKEN-XYZ", res.text)
        payload = res.json()["items"][0]
        self.assertNotIn("verification_token", payload)
        self.assertFalse(payload["verified"])

    def test_newly_registered_domain_starts_unverified(self):
        """登记 ≠ 授权：新域名一律未验证，未验证不会带来自动入组。"""
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")

        res = self.client.post(
            self.org_path(org, "/domains"),
            json={"domain": f"brand-new-{self.suffix}.test"},
            headers=owner["headers"],
        )

        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()["verified"])
        self.assertIsNone(res.json()["verified_at"])

    def test_org_admin_cannot_touch_domains(self):
        """域名声明的是「谁拥有这个邮箱域」，只有 org_owner 的 org_manage 持有该项。"""
        org = self.make_org()
        self.make_member(org, org_role="org_owner")
        admin = self.make_member(org, org_role="org_admin")

        read = self.client.get(self.org_path(org, "/domains"), headers=admin["headers"])
        write = self.client.post(
            self.org_path(org, "/domains"),
            json={"domain": f"sneaky-{self.suffix}.test"},
            headers=admin["headers"],
        )

        self.assertEqual(read.status_code, 403)
        self.assertEqual(write.status_code, 403)

    # -- owner 移交与邀请角色白名单 --------------------------------------

    def test_org_admin_cannot_transfer_owner(self):
        """org_admin 缺 org_manage；若它拿得到，admin 就能反夺 owner。"""
        org = self.make_org()
        self.make_member(org, org_role="org_owner")
        admin = self.make_member(org, org_role="org_admin")

        res = self.client.post(
            self.org_path(org, "/owner-transfer"),
            json={"new_owner_principal_id": admin["principal"]["principal_id"]},
            headers=admin["headers"],
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(
            self.db.fetch_organization_membership(
                org["organization_id"], admin["principal"]["principal_id"]
            )["role"],
            "org_admin",
        )

    def test_invite_role_whitelist_rejects_org_owner(self):
        """一封误发的邀请就能把组织送出去，是不可接受的操作面。"""
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")

        res = self.client.post(
            self.org_path(org, "/invites"),
            json={"email": f"pwn-{self.suffix}@acme.test", "target_role": "org_owner"},
            headers=owner["headers"],
        )

        self.assertEqual(res.status_code, 400, res.text)
        self.assertEqual(self.db.list_membership_invites(org["organization_id"]), [])

    def test_org_billing_viewer_cannot_create_invite(self):
        org = self.make_org()
        self.make_member(org, org_role="org_owner")
        billing = self.make_member(org, org_role="org_billing_viewer")

        res = self.client.post(
            self.org_path(org, "/invites"),
            json={"email": f"someone-{self.suffix}@acme.test", "target_role": "org_member"},
            headers=billing["headers"],
        )

        self.assertEqual(res.status_code, 403)

    def test_accept_org_invite_sets_password_and_active_membership(self):
        """R1.1 补齐的一致性缺口：经组织邀请进来的账户必须能登录。

        不设密码的话，这个人之后走注册会撞「邮箱已被注册」，又没有密码可登 —— 死胡同。
        """
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")
        invitee_email = f"inv-{self.suffix}@acme.test"
        created = self.client.post(
            self.org_path(org, "/invites"),
            json={"email": invitee_email, "target_role": "org_member"},
            headers=owner["headers"],
        )
        self.assertEqual(created.status_code, 200, created.text)

        res = self.client.post(
            f"{ORGS_PREFIX}/invites/accept",
            json={"invite_token": created.json()["invite_token"], "display_name": "Invited", "password": PASSWORD},
        )

        self.assertEqual(res.status_code, 200, res.text)
        principal = self.db.fetch_principal_by_email(invitee_email)
        self.assertTrue(principal.get("password_hash"))
        membership = self.db.fetch_organization_membership(org["organization_id"], principal["principal_id"])
        self.assertEqual(membership["role"], "org_member")
        self.assertEqual(membership["status"], "active")

    def test_org_invitee_can_actually_sign_in_after_accepting(self):
        """组织邀请的断头链修复（R1.4）：只建组织成员身份的账户**登不进来**。

        ``account_login`` 在缺省 workspace_id 时按 principal 的 workspace 成员身份取首个，
        空列表直接抛 401 ``Invalid email or password``。于是旧行为是：受邀者看到「邀请已
        接受」、密码确实写进了库，然后登录时被告知「密码错误」，并且没有任何 UI 能自救
        （选工作空间的前提是已登录）。

        这条测试刻意打**真实登录端点**而不是只查数据库行 —— 「有 workspace 成员身份」不等
        于「登录可用」（组织成员身份被 suspend 时同样会 403）。
        """
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")
        invitee_email = f"land-{self.suffix}@acme.test"
        created = self.client.post(
            self.org_path(org, "/invites"),
            json={"email": invitee_email, "target_role": "org_member"},
            headers=owner["headers"],
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertNotIn("workspace", created.json(), "缺省不该预先绑定某个空间")

        accepted = self.client.post(
            f"{ORGS_PREFIX}/invites/accept",
            json={"invite_token": created.json()["invite_token"], "display_name": "Landing", "password": PASSWORD},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        payload = accepted.json()
        self.assertTrue(payload.get("workspace"), "接受响应必须带落地工作空间，形状与工作空间级邀请一致")
        self.assertEqual(payload["workspace_membership"]["role"], "viewer",
                         "落地角色必须是最小权限；更高权限由管理员事后调整")

        login = self.client.post(
            "/api/v1/account/login",
            json={"email": invitee_email, "password": PASSWORD},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["workspace_id"], payload["workspace"]["workspace_id"])
        self.assertTrue(login.json().get("access_token"))

    def test_org_invite_landing_workspace_must_belong_to_that_organization(self):
        """指定落地空间必须校验归属，否则邀请行会把他组织的空间塞给受邀者。"""
        mine = self.make_org("Mine")
        theirs = self.make_org("Theirs")
        owner = self.make_member(mine, org_role="org_owner")
        foreign_ws = self.make_member(theirs, org_role="org_owner")["workspace"]

        res = self.client.post(
            self.org_path(mine, "/invites"),
            json={
                "email": f"cross-{self.suffix}@acme.test",
                "target_role": "org_member",
                "workspace_id": foreign_ws["workspace_id"],
            },
            headers=owner["headers"],
        )

        self.assertEqual(res.status_code, 400, res.text)
        self.assertEqual(self.db.list_membership_invites(mine["organization_id"]), [])

    def test_org_invite_lands_in_the_named_workspace_when_provided(self):
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")
        second = seed_workspace(self.db, organization_id=org["organization_id"], name="Second")

        created = self.client.post(
            self.org_path(org, "/invites"),
            json={
                "email": f"pick-{self.suffix}@acme.test",
                "target_role": "org_member",
                "workspace_id": second["workspace_id"],
            },
            headers=owner["headers"],
        )
        accepted = self.client.post(
            f"{ORGS_PREFIX}/invites/accept",
            json={"invite_token": created.json()["invite_token"], "display_name": "Pick", "password": PASSWORD},
        )

        self.assertEqual(accepted.json()["workspace"]["workspace_id"], second["workspace_id"])

    def test_accept_without_any_workspace_is_not_reported_as_ready(self):
        """组织下一个空间都没有时不能谎报可登录：必须显式回报 workspace_access_ready=False。

        缺了这个位，前端只能猜，而猜错的表现是「接受成功却登不进去」。
        """
        org = self.make_org("Empty")
        owner = self.make_member(org, org_role="org_owner")
        invite = self.client.post(
            self.org_path(org, "/invites"),
            json={"email": f"empty-{self.suffix}@acme.test", "target_role": "org_member"},
            headers=owner["headers"],
        )
        # 把工作空间挪到别的组织，制造「本组织零工作空间」：DatabaseManager 没有
        # delete_workspace，硬删行会留下指向已消失空间的孤儿成员关系，反而污染环境。
        elsewhere = self.make_org("Elsewhere")
        workspace = owner["workspace"]
        self.db.upsert_workspace({**workspace, "organization_id": elsewhere["organization_id"]})
        self.assertEqual(self.db.list_workspaces(organization_id=org["organization_id"]), [])

        res = self.client.post(
            f"{ORGS_PREFIX}/invites/accept",
            json={"invite_token": invite.json()["invite_token"], "display_name": "Empty", "password": PASSWORD},
        )

        self.assertEqual(res.status_code, 200, res.text)
        self.assertNotIn("workspace", res.json())
        self.assertIs(res.json().get("workspace_access_ready"), False)

    # -- 审计流水的组织隔离 ----------------------------------------------

    def test_audit_logs_exclude_other_organizations(self):
        """fetch_audit_logs 没有 organization 维度参数 → 视图层过滤必须真的生效。"""
        mine = self.make_org("Mine")
        theirs = self.make_org("Theirs")
        me = self.make_member(mine, org_role="org_owner")
        # 别的组织产生审计行：走真端点，而不是手搓 audit 记录
        them = self.make_member(theirs, org_role="org_owner")
        self.client.post(
            self.org_path(theirs, "/domains"),
            json={"domain": f"theirs-{self.suffix}.test"},
            headers=them["headers"],
        )

        res = self.client.get(self.org_path(mine, "/audit-logs?limit=100"), headers=me["headers"])

        self.assertEqual(res.status_code, 200, res.text)
        items = res.json()["items"]
        self.assertGreater(len(items), 0, "过滤后一条都不剩，可能是过滤条件写反了")
        for item in items:
            detail = item.get("detail_json") or {}
            self.assertTrue(
                detail.get("organization_id") == mine["organization_id"]
                or (item.get("target_type") == "organization" and item.get("target_id") == mine["organization_id"]),
                f"leaked audit row from another org: {item}",
            )

    def test_audit_logs_honour_limit(self):
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")
        for i in range(4):
            self.client.post(
                self.org_path(org, "/invites"),
                json={"email": f"a{i}-{self.suffix}@acme.test", "target_role": "org_member"},
                headers=owner["headers"],
            )

        res = self.client.get(self.org_path(org, "/audit-logs?limit=2"), headers=owner["headers"])

        self.assertEqual(res.status_code, 200)
        self.assertLessEqual(len(res.json()["items"]), 2)

    def test_audit_logs_require_read_audit(self):
        org = self.make_org()
        self.make_member(org, org_role="org_owner")
        member = self.make_member(org, org_role="org_member")

        res = self.client.get(self.org_path(org, "/audit-logs"), headers=member["headers"])

        self.assertEqual(res.status_code, 403)

    # -- 工作空间清单 -----------------------------------------------------

    def test_workspaces_listing_requires_workspace_manage(self):
        org = self.make_org()
        self.make_member(org, org_role="org_owner")
        member = self.make_member(org, org_role="org_member")
        denied = self.client.get(self.org_path(org, "/workspaces"), headers=member["headers"])
        self.assertEqual(denied.status_code, 403)

        admin = self.make_member(org, org_role="org_admin")
        ok = self.client.get(self.org_path(org, "/workspaces"), headers=admin["headers"])
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(len(ok.json()["items"]), 3)  # 三个成员各带一个绑定空间


if __name__ == "__main__":
    unittest.main()
