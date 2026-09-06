"""账户数据权利端点测试（R1.7，2026-09-06）。

这条链路上真正会伤到人的不是「能不能下载 JSON」，而是三件事，测试全部围绕它们：

1. **导出不得带走凭据**。库里 ``access_token.token`` / ``auth_session.session_token`` 是
   未过期即可用的活凭据，``*_token_hash`` 是可离线爆破的一次性令牌，``invite_token`` 拿
   上就能加入别人的组织。导出文件会落到用户磁盘上长期留存，泄一次是永久性的。所以这里
   不是「断言没有某个字段名」，而是**把库里真实的凭据值取出来，断言它没有出现在导出
   产物里** —— 字段名可以改（``token`` → ``tok``），值改不了。
2. **删除必须真的能撤销，且 owner 不能把组织删成孤儿**。
3. **受理删除后当前令牌必须失效**，而且要用真实请求证明（响应里说 revoked 不算）。

同共享 PG 库的其它认证测试一样：setUp 走 ``reset_access_control_tables``，邮箱带随机后缀。
"""

import datetime
import json
import tempfile
import unittest
import uuid
from pathlib import Path
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
    login_with_password,
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
from routes import account_routes, data_rights_routes  # noqa: E402
from services import data_rights  # noqa: E402

PASSWORD = "Maple-Drum-77!grid"
ACCOUNT_PREFIX = "/api/v1/account"


class _MemoryLake:
    """写 artifact 到临时目录，接口与 LocalArtifactLake 一致。

    不往仓库 ``data_lake/`` 里落含个人数据的文件：测试产物不该出现在开发机上。
    """

    def __init__(self, root: str):
        self.root_dir = Path(root)
        self.namespace = "account_data_export"

    def write_artifact(self, *, layer, namespace, partition, payload, metadata=None):
        artifact_id = uuid.uuid4().hex
        path = self.root_dir / layer / namespace / partition
        path.mkdir(parents=True, exist_ok=True)
        payload_path = path / f"{artifact_id}.json"
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "artifact_id": artifact_id,
            "payload_path": str(payload_path),
            "metadata_path": str(payload_path.with_suffix(".meta.json")),
            "layer": layer,
            "namespace": namespace,
            "partition": partition,
        }


class DataRightsRouteTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        self.state_store = offline_state_store()
        mock.patch.object(data_rights_routes, "get_db", lambda: self.db).start()
        mock.patch.object(account_routes, "get_db", lambda: self.db).start()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        self.addCleanup(mock.patch.stopall)

        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.lake = _MemoryLake(self.tmpdir.name)
        # 下载端点的越界校验读 lake_root_dir()，让它指向同一个临时目录，
        # 否则测试里生成的 artifact 会被判为「逃出 lake 根」而 500。
        mock.patch.object(
            data_rights, "lake_root_dir", lambda: str(Path(self.tmpdir.name).resolve())
        ).start()

        self.app = FastAPI()
        self.app.include_router(data_rights_routes.router)
        self.app.include_router(account_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    # -- fixtures --------------------------------------------------------

    def make_org(self, name="Acme Energy"):
        return seed_organization(self.db, name=name)

    def make_member(self, org, *, org_role="org_member", email=None, ws_role="owner"):
        email = email or f"u-{uuid.uuid4().hex[:8]}@{self.suffix}.test"
        principal = seed_principal(self.db, email=email, display_name="Rights")
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
            role=ws_role,
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
            "token": token,
            "headers": {"Authorization": f"Bearer {token['token']}"},
        }

    def seed_personal_traces(self, member) -> dict:
        """在该 principal 名下留下各类行，返回其中**不该**出现在导出里的凭据值。

        刻意造齐三种凭据形态：活令牌（可直用）、一次性令牌的哈希（可离线爆破）、
        邀请 token（可冒名入组）。
        """
        pid = member["principal"]["principal_id"]
        ws = member["workspace"]["workspace_id"]
        secret = {}

        session_token = f"sess_{uuid.uuid4().hex}"
        secret["session_token"] = session_token
        self.db.upsert_auth_session(
            {
                "session_id": f"se_{uuid.uuid4().hex[:12]}",
                "session_token": session_token,
                "principal_id": pid,
                "organization_id": None,
                "workspace_id": ws,
                "auth_method": "bootstrap",
                "created_at": "2026-09-06T00:00:00Z",
                "last_seen_at": "2026-09-06T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "revoked": 0,
            }
        )

        self.db.insert_email_verification(
            {
                "verification_id": f"ev_{uuid.uuid4().hex[:12]}",
                "principal_id": pid,
                "email": member["email"],
                "token_hash": "sha256$" + uuid.uuid4().hex + uuid.uuid4().hex,
                "requested_at": "2026-09-06T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "used_at": None,
            }
        )
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT token_hash FROM email_verification WHERE principal_id = ?", (pid,)
            ).fetchone()
        secret["token_hash"] = row[0]
        principal_row = self.db.fetch_principal(pid)
        secret["password_hash"] = principal_row["password_hash"]
        secret["access_token"] = member["token"]["token"]

        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE agent_execution_log SET principal_id = ? WHERE principal_id IS NULL",
                (pid,),
            )
            conn.commit()
        return secret

    # -- 认证与越权 ------------------------------------------------------

    def test_all_data_rights_endpoints_require_a_bearer_token(self):
        for method, path in [
            ("post", f"{ACCOUNT_PREFIX}/export"),
            ("get", f"{ACCOUNT_PREFIX}/export"),
            ("get", f"{ACCOUNT_PREFIX}/export/exp_missing/download"),
            ("post", f"{ACCOUNT_PREFIX}/delete"),
            ("get", f"{ACCOUNT_PREFIX}/delete"),
            ("post", f"{ACCOUNT_PREFIX}/delete/cancel"),
        ]:
            # 不能给 GET 传 json=None：本版 starlette TestClient 的 get() 没有 json 参数。
            res = getattr(self.client, method)(path, json={}) if method == "post" else getattr(self.client, method)(path)
            self.assertEqual(res.status_code, 401, f"{method.upper()} {path} 竟允许匿名：{res.text}")

    def test_export_scopes_to_the_caller_and_cannot_read_another_principal(self):
        """别人的 export_id 必须 404 —— 不能 403。

        403 会告诉调用方「这个 id 存在」，导出 id 于是成了可枚举的存在性 Oracle；
        404 与「不存在」同形，什么都探不出来。
        """
        org = self.make_org()
        mine = self.make_member(org)
        theirs = self.make_member(org)

        record = data_rights.create_export_record(self.db, principal_id=theirs["principal"]["principal_id"])
        res = self.client.get(
            f"{ACCOUNT_PREFIX}/export/{record['export_id']}/download", headers=mine["headers"]
        )
        self.assertEqual(res.status_code, 404, res.text)
        latest = self.client.get(f"{ACCOUNT_PREFIX}/export", headers=mine["headers"])
        self.assertEqual(latest.status_code, 200)
        self.assertIsNone(latest.json()["export_id"], "自己的视图里冒出了别人的导出")

    # -- 导出内容与脱敏 --------------------------------------------------

    def test_export_never_contains_live_credentials_or_password_material(self):
        org = self.make_org()
        member = self.make_member(org)
        secrets = self.seed_personal_traces(member)

        record = data_rights.create_export_record(
            self.db, principal_id=member["principal"]["principal_id"]
        )
        result = data_rights.run_export_job(
            self.db, export_id=record["export_id"], lake=self.lake
        )
        self.assertEqual(result["status"], "completed", result.get("error"))
        body = Path(result["artifact_path"]).read_text(encoding="utf-8")

        # 断言**值**不存在，而不是字段名不存在：改名绕不过值断言。
        for label, value in secrets.items():
            self.assertTrue(value, f"fixture 没造出 {label}，这条断言是假绿")
            self.assertNotIn(value, body, f"导出产物里出现了 {label}")

        payload = json.loads(body)
        # 列名这一层必须按结构判定，不能在整份 JSON 上做子串搜索：文件顶层的
        # ``columns_excluded`` 会逐字列出被剔除的凭据列名 —— 那是给权利主体看的透明性清单
        # （「你的数据里我们没带走这些」），不是泄漏。真正的判据是「任何一行数据里都不
        # 出现这些键」。
        self.assertTrue(payload["columns_excluded"], "透明性清单空了：剔除逻辑可能被整体绕过")
        excluded = set(data_rights.EXCLUDED_EXPORT_COLUMNS)
        for name, rows in payload["sections"].items():
            for row in rows:
                leaked = set(row) & excluded
                self.assertFalse(leaked, f"章节 {name} 的行里出现了被剔除列 {sorted(leaked)}")

        # 同时必须真的带上该带的：只验「没泄」不验「有货」会把空导出放过去。
        self.assertEqual(payload["subject"]["principal_id"], member["principal"]["principal_id"])
        self.assertGreater(payload["section_counts"]["account"], 0)
        self.assertGreater(payload["section_counts"]["workspace_memberships"], 0)
        self.assertIn("access_tokens", payload["section_source_tables"])

    def test_export_is_enqueued_and_downloadable_through_the_api(self):
        org = self.make_org()
        member = self.make_member(org)
        # ``submit_as_job`` 是路由函数内的惰性 import（避开模块级循环依赖），所以桩必须打在
        # 源模块上 —— patch 路由的名字空间会直接 AttributeError（本仓已为此付过学费）。
        with mock.patch(
            "cache_utils.submit_as_job", return_value={"job_id": "job_x", "status": "queued"}
        ) as enqueue:
            res = self.client.post(f"{ACCOUNT_PREFIX}/export", headers=member["headers"])
        self.assertEqual(res.status_code, 202, res.text)
        self.assertEqual(
            enqueue.call_args.args[0],
            "account_data_export",
            "作业名与 deps.get_job_registry 注册的不是同一个 → 永远停在 queued",
        )
        export_id = res.json()["export_id"]

        data_rights.run_export_job(self.db, export_id=export_id, lake=self.lake)
        status = self.client.get(f"{ACCOUNT_PREFIX}/export", headers=member["headers"])
        self.assertEqual(status.json()["status"], "completed")
        self.assertTrue(status.json()["download_ready"])

        download = self.client.get(
            f"{ACCOUNT_PREFIX}/export/{export_id}/download", headers=member["headers"]
        )
        self.assertEqual(download.status_code, 200, download.text)
        self.assertEqual(download.headers["content-type"].split(";")[0], "application/json")
        self.assertIn("attachment", download.headers.get("content-disposition", ""))

    def test_duplicate_export_is_reported_as_a_replay_and_starts_no_second_job(self):
        """在先的那次没做完时再点一次：必须说 already_queued，且**不能**再排一个作业。

        这一条原本是漏掉的，而它正好放过一个真实缺陷：路由里 ``{"status": "already_queued",
        **_export_view(...)}`` 的字典展开顺序会把 ``status`` 覆盖回 "queued"，于是重复提交
        与首次受理在响应上完全无法区分。顺序写反的代价只有断言能看见。
        """
        org = self.make_org()
        member = self.make_member(org)
        data_rights.create_export_record(self.db, principal_id=member["principal"]["principal_id"])
        with mock.patch("cache_utils.submit_as_job") as enqueue:
            res = self.client.post(f"{ACCOUNT_PREFIX}/export", headers=member["headers"])
        self.assertEqual(res.status_code, 202, res.text)
        self.assertEqual(res.json()["status"], "already_queued")
        enqueue.assert_not_called()

    def test_duplicate_deletion_is_reported_as_a_replay_and_keeps_the_original_deadline(self):
        """同一条字典展开纪律也要盖住 /delete：重复提交不能把排期往后推。"""
        org = self.make_org()
        member = self.make_member(org, org_role="org_owner")
        first = self.client.post(f"{ACCOUNT_PREFIX}/delete", headers=member["headers"])
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(first.json()["status"], "pending")
        self.assertTrue(first.json()["session_revoked"])

        relogin = self.client.post(
            f"{ACCOUNT_PREFIX}/login", json={"email": member["email"], "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
        second = self.client.post(f"{ACCOUNT_PREFIX}/delete", headers=headers)
        self.assertEqual(second.status_code, 202, second.text)
        self.assertEqual(second.json()["status"], "already_pending", "重放与首次受理必须可区分")
        self.assertNotIn(
            second.json().get("session_revoked"), (True,),
            "重放没有撤销会话，响应却声称撤销了",
        )
        self.assertEqual(
            second.json()["scheduled_delete_at"], first.json()["scheduled_delete_at"],
            "重复提交把排期往后推了 —— 用户可以无限拖延删除",
        )

    def test_download_reports_expired_file_as_gone_not_server_error(self):
        """行还在、文件没了时必须说「重新生成」，否则用户卡在一个无解界面上。"""
        org = self.make_org()
        member = self.make_member(org)
        record = data_rights.create_export_record(
            self.db, principal_id=member["principal"]["principal_id"]
        )
        result = data_rights.run_export_job(
            self.db, export_id=record["export_id"], lake=self.lake
        )
        Path(result["artifact_path"]).unlink()
        res = self.client.get(
            f"{ACCOUNT_PREFIX}/export/{record['export_id']}/download", headers=member["headers"]
        )
        self.assertEqual(res.status_code, 410, res.text)

    def test_download_refuses_artifact_path_outside_the_lake_root(self):
        """表里的路径被改到 lake 外 → 不能当文件读端点用。"""
        org = self.make_org()
        member = self.make_member(org)
        record = data_rights.create_export_record(
            self.db, principal_id=member["principal"]["principal_id"]
        )
        leaked = Path(self.tmpdir.name).parent / "outside.json"
        leaked.write_text('{"secret": 1}', encoding="utf-8")
        self.addCleanup(lambda: leaked.unlink(missing_ok=True))
        data_rights._update_export(  # noqa: SLF001 - 就是要造出这一行脏数据
            self.db,
            record["export_id"],
            status="completed",
            artifact_path=str(leaked.resolve()),
            completed_at="2026-09-06T00:00:00Z",
        )
        res = self.client.get(
            f"{ACCOUNT_PREFIX}/export/{record['export_id']}/download", headers=member["headers"]
        )
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secret", res.text)

    # -- 删除：宽限期、撤销、孤儿组织 -----------------------------------

    def test_owner_of_a_shared_organization_cannot_delete_self(self):
        org = self.make_org()
        owner = self.make_member(org, org_role="org_owner")
        self.make_member(org, org_role="org_admin")

        res = self.client.post(f"{ACCOUNT_PREFIX}/delete", headers=owner["headers"])
        self.assertEqual(res.status_code, 409, res.text)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "ownership_transfer_required")
        self.assertEqual(detail["organizations"][0]["organization_id"], org["organization_id"])
        self.assertIn("transfer-owner", detail["next_action"])
        # 被拦住的时候不许顺手撤销会话 —— 409 之后用户还要登录去移交。
        still = self.client.get(f"{ACCOUNT_PREFIX}/delete", headers=owner["headers"])
        self.assertEqual(still.status_code, 200)
        self.assertEqual(still.json()["status"], "none")

    def test_sole_owner_can_delete_and_his_tokens_stop_working_at_once(self):
        """受理成功 → 当前令牌立刻失效，且**密码登录仍然可用**（否则无人能撤销）。"""
        org = self.make_org()
        member = self.make_member(org, org_role="org_owner")

        res = self.client.post(f"{ACCOUNT_PREFIX}/delete", headers=member["headers"])
        self.assertEqual(res.status_code, 202, res.text)
        body = res.json()
        self.assertTrue(body["session_revoked"])
        self.assertEqual(body["status"], "pending")
        self.assertGreaterEqual(body["grace_days"], 1)

        after = self.client.get(f"{ACCOUNT_PREFIX}/export", headers=member["headers"])
        self.assertEqual(after.status_code, 401, "删除受理后旧令牌仍然可用")

        login = self.client.post(
            f"{ACCOUNT_PREFIX}/login",
            json={"email": member["email"], "password": PASSWORD},
        )
        self.assertEqual(login.status_code, 200, f"宽限期内无法登录 → 撤销请求形同虚设：{login.text}")

    def test_deletion_can_be_cancelled_within_the_grace_period(self):
        org = self.make_org()
        member = self.make_member(org, org_role="org_owner")
        self.client.post(f"{ACCOUNT_PREFIX}/delete", headers=member["headers"])

        relogin = self.client.post(
            f"{ACCOUNT_PREFIX}/login", json={"email": member["email"], "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
        cancel = self.client.post(
            f"{ACCOUNT_PREFIX}/delete/cancel", json={"reason": "changed my mind"}, headers=headers
        )
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(cancel.json()["status"], "cancelled")
        self.assertIsNotNone(cancel.json()["cancelled_at"])

        again = self.client.post(f"{ACCOUNT_PREFIX}/delete/cancel", json={}, headers=headers)
        self.assertEqual(again.status_code, 409, "重复撤销不能算成功")


class DataRightsServiceTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        self.state_store = offline_state_store()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        self.addCleanup(mock.patch.stopall)

    def test_purge_leaves_no_row_in_any_exported_section(self):
        """导出范围与清除范围必须是同一份清单 —— 这条断言把它们钉在一起。

        逐表比对而不是抽查：漏一张表就是一个「已删除但数据还在」的账户，而那正是这一整项
        要消除的法律责任。
        """
        principal = seed_principal(
            self.db, email=f"p-{self.suffix}@{self.suffix}.test", display_name="Purge Target"
        )
        pid = principal["principal_id"]
        org = seed_organization(self.db, name="Solo")
        ws = seed_workspace(self.db, organization_id=org["organization_id"], name="Only")
        seed_organization_membership(
            self.db, organization_id=org["organization_id"], principal_id=pid, role="org_owner"
        )
        seed_workspace_membership(
            self.db, workspace_id=ws["workspace_id"], principal_id=pid, role="owner"
        )
        issue_access_token(self.db, principal_id=pid, workspace_id=ws["workspace_id"])
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO notification (notification_id, workspace_id, principal_id, title,"
                " body_json, link, read, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"n_{uuid.uuid4().hex[:8]}", ws["workspace_id"], pid, "hi", "{}", None, 0, "2026-09-06T00:00:00Z"),
            )
            conn.commit()

        sections, _ = data_rights.fetch_account_rows(self.db, pid)
        non_empty = {name for name, rows in sections.items() if rows}
        self.assertIn("notifications", non_empty)
        self.assertIn("workspace_memberships", non_empty)

        deleted = data_rights.purge_account(self.db, principal_id=pid)
        self.assertIsNone(self.db.fetch_principal(pid))

        remaining, _ = data_rights.fetch_account_rows(self.db, pid)
        leftovers = {name for name, rows in remaining.items() if rows}
        self.assertEqual(leftovers, set(), f"清除后仍留有数据：{sorted(leftovers)}")
        for table in ("organization_membership", "workspace_membership", "access_token"):
            self.assertIn(table, deleted, f"{table} 不在清除清单里")

    def test_grace_period_shorter_than_a_day_is_refused(self):
        """宽限期 <1 天等于纸面可撤销：配错要在部署期炸出来，而不是静默按 0 处理。"""
        principal = seed_principal(
            self.db, email=f"g-{self.suffix}@{self.suffix}.test", display_name="Grace Probe"
        )
        with self.assertRaises(ValueError):
            data_rights.request_account_deletion(
                self.db, principal_id=principal["principal_id"], grace_days=0
            )

    def test_export_scope_covers_every_principal_bearing_table(self):
        """新表带了 principal 归属列却没进导出清单 → 这条变红。

        这是「导出完整性」唯一可执行的守卫：靠人记得改常量迟早会漏，而漏掉的那一段用户在
        自己的下载文件里看不见，也就永远不会来报。
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name IN "
                "('principal_id', 'actor_principal_id', 'accepted_by_principal_id', "
                "'invited_by_principal_id', 'created_by') "
                "GROUP BY table_name, column_name"
            ).fetchall()
        covered = {(t, c) for t, c in data_rights.PURGE_TARGETS}
        # 已知的例外必须逐个写明理由，否则这个集合会悄悄长大变成一个不解释的白名单。
        known_exceptions = {
            # membership_invite.email 指向的是受邀人（可能还不存在），accepted/invited_by
            # 两列已单独覆盖，整行不按 principal_id 取。
            # principal_identity 本身由 account 章节覆盖。
            # workspace_invite.accepted_at 不带 principal 列。
            ("feedback", "created_by"),  # 该表用 email 归属，无 principal_id
        }
        uncovered = {
            (t, c) for t, c in rows if (t, c) not in covered and (t, c) not in known_exceptions
        }
        self.assertEqual(uncovered, set(), f"这些 principal 归属列既不在导出清单也无豁免理由：{uncovered}")


class DataRightsBootstrapGuardTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        self.state_store = offline_state_store()
        mock.patch.object(data_rights_routes, "get_db", lambda: self.db).start()
        mock.patch.object(account_routes, "get_db", lambda: self.db).start()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        self.addCleanup(mock.patch.stopall)
        self.app = FastAPI()
        self.app.include_router(data_rights_routes.router)
        self.app.include_router(account_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_anonymous_bootstrap_identity_cannot_exercise_data_rights(self):
        """P0.1 的守卫必须在 R1.7 上同样成立。

        引导身份在 ``ws_default`` 上历史持有 owner，只看角色的实现会直接放行 —— 那等于
        任意同源浏览器都能批量导出账户数据、提交删除。
        """
        # 真实 PG 上 workspace.organization_id 有外键（SQLite 时期没有），裸写一个
        # "org_x" 会直接 ForeignKeyViolation —— 这条得先建组织。
        organization = seed_organization(self.db, name="Default Org")
        workspace = seed_workspace(self.db, organization_id=organization["organization_id"], name="Default")
        # 引导身份是系统预置行，seed_principal 会另生成 id、给不出 pr_websession，
        # 所以这里直接 upsert 那一行（PG 上 workspace_membership.principal_id 有外键）。
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        self.db.upsert_principal(
            {
                "principal_id": BOOTSTRAP_PRINCIPAL_ID,
                "email": f"bootstrap-{self.suffix}@{self.suffix}.test",
                "display_name": "Anonymous bootstrap",
                "password_hash": None,
                "password_salt": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        seed_workspace_membership(
            self.db,
            workspace_id=workspace["workspace_id"],
            principal_id=BOOTSTRAP_PRINCIPAL_ID,
            role="owner",
        )
        token = issue_access_token(
            self.db, principal_id=BOOTSTRAP_PRINCIPAL_ID, workspace_id=workspace["workspace_id"]
        )
        headers = {"Authorization": f"Bearer {token['token']}"}
        for method, path in [
            ("post", f"{ACCOUNT_PREFIX}/export"),
            ("get", f"{ACCOUNT_PREFIX}/export"),
            ("post", f"{ACCOUNT_PREFIX}/delete"),
            ("get", f"{ACCOUNT_PREFIX}/delete"),
        ]:
            res = getattr(self.client, method)(path, json={}) if method == "post" else getattr(self.client, method)(path)
            self.assertIn(
                res.status_code, (401, 403), f"{method.upper()} {path} 放行了匿名引导身份"
            )


if __name__ == "__main__":
    unittest.main()
