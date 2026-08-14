"""Tests for P2 retention routes（通知/报告/偏好/反馈/审计/告警分发，2026-08-14）.

DatabaseManager 为 PG-only，测试直连开发库：随机后缀隔离 + tearDown 清理。
"""

import sys
import types
import unittest
import uuid

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import DatabaseManager
from routes import p2_routes
from access_control import (
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
)


def _build_client(db, actor):
    app = FastAPI()
    app.include_router(p2_routes.router)
    app.dependency_overrides[p2_routes._get_actor] = lambda: actor
    return TestClient(app)


class P2RoutesTests(unittest.TestCase):
    def setUp(self):
        self._suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        self._orig_get_db = p2_routes.get_db
        p2_routes.get_db = lambda: self.db

        self.org = seed_organization(self.db, name=f"P2org-{self._suffix}")
        self.ws = seed_workspace(self.db, organization_id=self.org["organization_id"], name="main")
        self.owner = seed_principal(self.db, email=f"p2owner-{self._suffix}@acme.test", display_name="Owner")
        self.viewer = seed_principal(self.db, email=f"p2viewer-{self._suffix}@acme.test", display_name="Viewer")
        seed_workspace_membership(self.db, workspace_id=self.ws["workspace_id"],
                                  principal_id=self.owner["principal_id"], role="owner")
        seed_workspace_membership(self.db, workspace_id=self.ws["workspace_id"],
                                  principal_id=self.viewer["principal_id"], role="viewer")
        seed_organization_membership(self.db, organization_id=self.org["organization_id"],
                                     principal_id=self.owner["principal_id"], role="org_owner")
        seed_organization_membership(self.db, organization_id=self.org["organization_id"],
                                     principal_id=self.viewer["principal_id"], role="org_member")

        self.owner_actor = {
            "principal": self.owner,
            "workspace": self.ws,
            "membership": self.db.fetch_workspace_membership(self.ws["workspace_id"], self.owner["principal_id"]),
        }
        self.viewer_actor = {
            "principal": self.viewer,
            "workspace": self.ws,
            "membership": self.db.fetch_workspace_membership(self.ws["workspace_id"], self.viewer["principal_id"]),
        }

    def tearDown(self):
        p2_routes.get_db = self._orig_get_db
        ws = self.ws["workspace_id"]
        try:
            with self.db.get_connection() as conn:
                self.db.ensure_p2_tables(conn)
                conn.execute("DELETE FROM notification WHERE workspace_id = ?", (ws,))
                conn.execute("DELETE FROM saved_report WHERE workspace_id = ?", (ws,))
                conn.execute("DELETE FROM user_preference WHERE workspace_id = ?", (ws,))
                conn.execute("DELETE FROM feedback WHERE workspace_id = ?", (ws,))
                conn.execute("DELETE FROM alert_rule WHERE workspace_id = ?", (ws,))
                conn.execute("DELETE FROM report_subscription WHERE workspace_id = ?", (ws,))
                conn.commit()
        except Exception:
            pass

    # ── notifications ───────────────────────────────────────────────────

    def test_notification_lifecycle_and_unread(self):
        ws = self.ws["workspace_id"]
        self.db.insert_notification({
            "notification_id": f"ntf_{self._suffix}",
            "workspace_id": ws,
            "principal_id": None,
            "title": "测试告警",
            "body": {"value": 42},
            "link": None,
            "created_at": "2026-08-14T00:00:00Z",
        })
        client = _build_client(self.db, self.viewer_actor)
        # 未读数
        resp = client.get(f"/api/v1/notify/unread-count?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["unread"], 1)
        # 列表
        resp = client.get(f"/api/v1/notify?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["body"]["value"], 42)
        # 标记已读
        resp = client.post(f"/api/v1/notify/ntf_{self._suffix}/read?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        resp = client.get(f"/api/v1/notify/unread-count?workspace_id={ws}")
        self.assertEqual(resp.json()["unread"], 0)

    def test_notification_workspace_isolation(self):
        """他 workspace 的通知不可见、不可标记。"""
        self.db.insert_notification({
            "notification_id": f"ntf_other_{self._suffix}",
            "workspace_id": f"ws-other-{self._suffix}",
            "principal_id": None,
            "title": "其他租户",
            "body": {},
            "link": None,
            "created_at": "2026-08-14T00:00:00Z",
        })
        client = _build_client(self.db, self.viewer_actor)
        ws = self.ws["workspace_id"]
        resp = client.get(f"/api/v1/notify?workspace_id={ws}")
        self.assertEqual(resp.json()["items"], [])
        # 跨 workspace 标记：路径 ws 与令牌不一致 → 403
        resp = client.post(f"/api/v1/notify/ntf_other_{self._suffix}/read?workspace_id=ws-other-{self._suffix}")
        self.assertEqual(resp.status_code, 403)

    # ── saved reports ───────────────────────────────────────────────────

    def test_report_save_list_fetch_delete_permissions(self):
        ws = self.ws["workspace_id"]
        owner = _build_client(self.db, self.owner_actor)
        resp = owner.post("/api/v1/reports/save", json={
            "workspace_id": ws, "title": f"报告-{self._suffix}",
            "market": "NEM", "region": "NSW1", "year": 2025,
        })
        self.assertEqual(resp.status_code, 200)
        report_id = resp.json()["report_id"]

        # 列表（viewer 可读）
        viewer = _build_client(self.db, self.viewer_actor)
        resp = viewer.get(f"/api/v1/reports/saved?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["items"]), 1)
        # 详情
        resp = viewer.get(f"/api/v1/reports/saved/{report_id}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("payload", resp.json())
        # viewer 删除 → 403
        resp = viewer.delete(f"/api/v1/reports/saved/{report_id}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 403)
        # owner 删除 → 200
        resp = owner.delete(f"/api/v1/reports/saved/{report_id}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)

    # ── preferences ─────────────────────────────────────────────────────

    def test_preferences_roundtrip_and_key_whitelist(self):
        ws = self.ws["workspace_id"]
        client = _build_client(self.db, self.owner_actor)
        resp = client.put("/api/v1/preferences/saved_views", json={
            "workspace_id": ws,
            "value": {"views": [{"name": "v1", "market": "NEM", "filters": {"region": "NSW1"}}]},
        })
        self.assertEqual(resp.status_code, 200)
        resp = client.get(f"/api/v1/preferences/saved_views?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["value"]["views"][0]["name"], "v1")
        # 非法 key → 422
        resp = client.get(f"/api/v1/preferences/evil_key?workspace_id={ws}")
        self.assertEqual(resp.status_code, 422)

    # ── feedback ────────────────────────────────────────────────────────

    def test_feedback_persisted(self):
        client = _build_client(self.db, self.viewer_actor)
        resp = client.post("/api/v1/feedback", json={
            "message": f"测试反馈 {self._suffix}",
            "workspace_id": self.ws["workspace_id"],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["received"])
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE workspace_id = ?",
                (self.ws["workspace_id"],),
            ).fetchone()
        self.assertEqual(row[0], 1)

    # ── audit ───────────────────────────────────────────────────────────

    def test_audit_permission_matrix(self):
        ws = self.ws["workspace_id"]
        # viewer → 403
        viewer = _build_client(self.db, self.viewer_actor)
        resp = viewer.get(f"/api/v1/audit?workspace_id={ws}")
        self.assertEqual(resp.status_code, 403)
        # owner → 200（结构正确，摘要字段不含 detail）
        owner = _build_client(self.db, self.owner_actor)
        resp = owner.get(f"/api/v1/audit?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json()["items"], list)

    # ── alert rule toggle ───────────────────────────────────────────────

    def test_alert_rule_toggle_permissions(self):
        ws = self.ws["workspace_id"]
        rule_id = f"al_{self._suffix}"
        self.db.upsert_alert_rule({
            "rule_id": rule_id, "name": "t", "rule_type": "price_threshold",
            "market": "NEM", "region_or_zone": "NSW1",
            "config": {"operator": "gt", "threshold": 300},
            "channel_type": "inapp", "channel_target": "",
            "enabled": True, "organization_id": self.org["organization_id"],
            "workspace_id": ws,
            "created_at": "2026-08-14T00:00:00Z", "updated_at": "2026-08-14T00:00:00Z",
        })
        viewer = _build_client(self.db, self.viewer_actor)
        resp = viewer.post(f"/api/v1/alerts/rules/{rule_id}/toggle",
                           json={"workspace_id": ws, "enabled": False})
        self.assertEqual(resp.status_code, 403)

        owner = _build_client(self.db, self.owner_actor)
        resp = owner.post(f"/api/v1/alerts/rules/{rule_id}/toggle",
                          json={"workspace_id": ws, "enabled": False})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.db.fetch_alert_rule(rule_id)["enabled"])
        # 跨 workspace 规则 → 404
        resp = owner.post(f"/api/v1/alerts/rules/al_not_exist/toggle",
                          json={"workspace_id": ws, "enabled": False})
        self.assertEqual(resp.status_code, 404)

    # ── alerts dispatch（inapp 直投 + email 降级） ─────────────────────

    def test_deliver_alert_inapp_writes_notification(self):
        import alerts

        ws = self.ws["workspace_id"]
        rule = {
            "rule_id": f"al_{self._suffix}", "name": "价格告警",
            "rule_type": "price_threshold", "market": "NEM",
            "region_or_zone": "NSW1", "channel_type": "inapp",
            "channel_target": "", "workspace_id": ws,
        }
        result = alerts._deliver_alert(self.db, rule, {"result": {"value": 999}}, None)
        self.assertEqual(result["delivery_status"], "sent")
        self.assertEqual(self.db.count_unread_notifications(ws), 1)

    # ── 审计修复补充用例（2026-08-14） ────────────────────────────────

    def test_notification_read_all(self):
        ws = self.ws["workspace_id"]
        for i in range(2):
            self.db.insert_notification({
                "notification_id": f"ntf_all_{self._suffix}_{i}",
                "workspace_id": ws, "principal_id": None,
                "title": f"t{i}", "body": {}, "link": None,
                "created_at": "2026-08-14T00:00:00Z",
            })
        client = _build_client(self.db, self.viewer_actor)
        resp = client.post(f"/api/v1/notify/read-all?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["marked"], 2)
        resp = client.get(f"/api/v1/notify/unread-count?workspace_id={ws}")
        self.assertEqual(resp.json()["unread"], 0)

    def test_report_cross_workspace_isolation(self):
        """他 workspace 的报告不可读取/删除。"""
        ws = self.ws["workspace_id"]
        other_ws = f"ws-other-{self._suffix}"
        self.db.insert_saved_report({
            "report_id": f"rpt_x_{self._suffix}", "workspace_id": other_ws,
            "title": "other", "market": "NEM", "region": "NSW1", "year": 2025,
            "payload": {}, "created_by": "pr_x", "created_at": "2026-08-14T00:00:00Z",
        })
        owner = _build_client(self.db, self.owner_actor)
        resp = owner.get(f"/api/v1/reports/saved/rpt_x_{self._suffix}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 404)
        resp = owner.delete(f"/api/v1/reports/saved/rpt_x_{self._suffix}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 404)

    def test_preference_put_invalid_key_and_upsert(self):
        ws = self.ws["workspace_id"]
        client = _build_client(self.db, self.owner_actor)
        resp = client.put("/api/v1/preferences/evil", json={"workspace_id": ws, "value": {}})
        self.assertEqual(resp.status_code, 422)
        # upsert 覆盖语义：同 key 二次写入覆盖
        for v in ({"n": 1}, {"n": 2}):
            resp = client.put("/api/v1/preferences/favorite_regions",
                              json={"workspace_id": ws, "value": v})
            self.assertEqual(resp.status_code, 200)
        resp = client.get(f"/api/v1/preferences/favorite_regions?workspace_id={ws}")
        self.assertEqual(resp.json()["value"]["n"], 2)

    def test_feedback_cross_workspace_rejected(self):
        client = _build_client(self.db, self.viewer_actor)
        resp = client.post("/api/v1/feedback", json={
            "message": "x", "workspace_id": f"ws-evil-{self._suffix}",
        })
        self.assertEqual(resp.status_code, 403)

    def test_alert_rule_create_v1_permissions_and_validation(self):
        ws = self.ws["workspace_id"]
        viewer = _build_client(self.db, self.viewer_actor)
        resp = viewer.post("/api/v1/alerts/rules", json={
            "workspace_id": ws, "name": "n", "rule_type": "price_threshold",
            "channel_type": "inapp",
        })
        self.assertEqual(resp.status_code, 403)

        owner = _build_client(self.db, self.owner_actor)
        # 非法 rule_type → 422
        resp = owner.post("/api/v1/alerts/rules", json={
            "workspace_id": ws, "name": "n", "rule_type": "evil",
            "channel_type": "inapp",
        })
        self.assertEqual(resp.status_code, 422)
        # 正常创建 → 200 且归属本 workspace
        resp = owner.post("/api/v1/alerts/rules", json={
            "workspace_id": ws, "name": f"规则-{self._suffix}",
            "rule_type": "price_threshold", "channel_type": "inapp",
            "config": {"operator": "gt", "threshold": 300},
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["workspace_id"], ws)

    def test_report_save_invalid_type_rejected(self):
        client = _build_client(self.db, self.owner_actor)
        resp = client.post("/api/v1/reports/save", json={
            "workspace_id": self.ws["workspace_id"], "title": "t",
            "report_type": "evil_type", "region": "NSW1", "year": 2025,
        })
        self.assertEqual(resp.status_code, 422)

    def test_deliver_alert_webhook_branch_regression(self):
        """webhook 分支既有行为回归保护。"""
        import alerts

        calls = []

        def fake_sender(target, payload):
            calls.append((target, payload))
            return {"status_code": 200, "response_text": "ok"}

        rule = {
            "rule_id": f"al_{self._suffix}", "name": "w",
            "rule_type": "price_threshold", "market": "NEM",
            "region_or_zone": "NSW1", "channel_type": "webhook",
            "channel_target": "https://example.com/hook",
            "workspace_id": self.ws["workspace_id"],
        }
        result = alerts._deliver_alert(self.db, rule, {"result": {"value": 1}}, fake_sender)
        self.assertEqual(result["delivery_status"], "sent")
        self.assertEqual(result["response_code"], 200)
        self.assertEqual(len(calls), 1)

    def test_deliver_alert_inapp_unknown_workspace_skipped(self):
        """inapp 投递到不存在 workspace 时静默跳过（审计加固）。"""
        import alerts

        rule = {
            "rule_id": f"al_{self._suffix}", "name": "w",
            "rule_type": "price_threshold", "market": "NEM",
            "channel_type": "inapp", "channel_target": "",
            "workspace_id": f"ws-ghost-{self._suffix}",
        }
        result = alerts._deliver_alert(self.db, rule, {"result": {"value": 1}}, None)
        self.assertEqual(result["delivery_status"], "sent")
        self.assertEqual(self.db.count_unread_notifications(f"ws-ghost-{self._suffix}"), 0)

    # ── 报告定时订阅（2026-08-14） ──────────────────────────────────

    def test_report_subscription_lifecycle(self):
        ws = self.ws["workspace_id"]
        owner = _build_client(self.db, self.owner_actor)
        # monthly 缺 day_of_month → 422
        resp = owner.post("/api/v1/reports/subscriptions", json={
            "workspace_id": ws, "title": "t", "region": "NSW1", "frequency": "monthly",
        })
        self.assertEqual(resp.status_code, 422)
        # 正常创建
        resp = owner.post("/api/v1/reports/subscriptions", json={
            "workspace_id": ws, "title": f"月报-{self._suffix}", "region": "NSW1",
            "frequency": "monthly", "day_of_month": 15,
        })
        self.assertEqual(resp.status_code, 200)
        sub_id = resp.json()["subscription_id"]
        # 列表可见
        resp = owner.get(f"/api/v1/reports/subscriptions?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(s["subscription_id"] == sub_id for s in resp.json()["items"]))
        # viewer 不能删他人订阅
        viewer = _build_client(self.db, self.viewer_actor)
        resp = viewer.delete(f"/api/v1/reports/subscriptions/{sub_id}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 403)
        # 本人可删
        resp = owner.delete(f"/api/v1/reports/subscriptions/{sub_id}?workspace_id={ws}")
        self.assertEqual(resp.status_code, 200)

    def test_report_dispatch_monthly_due_and_same_day_skip(self):
        """到期投递 + 同日不重发；email=None 强制走站内降级路径（不发真实邮件）。"""
        import datetime
        from services.report_scheduler import dispatch_due_report_subscriptions

        ws = self.ws["workspace_id"]
        now = datetime.datetime.now(datetime.timezone.utc)
        sub = self.db.upsert_report_subscription({
            "subscription_id": f"rsub_{self._suffix}",
            "workspace_id": ws,
            "principal_id": self.owner["principal_id"],
            "title": f"调度测试-{self._suffix}",
            "market": "NEM",
            "region": "NSW1",
            "frequency": "monthly",
            "day_of_month": now.day,
            "day_of_week": None,
            "email": None,
            "enabled": True,
            "last_sent_at": None,
            "created_at": "2026-08-14T00:00:00Z",
        })
        stats = dispatch_due_report_subscriptions(self.db, now=now)
        self.assertEqual(stats["due"], 1)
        self.assertEqual(stats["degraded_inapp"], 1)  # email=None → 站内通知
        self.assertEqual(stats["sent_email"], 0)
        # 已写站内通知与保存报告
        self.assertGreaterEqual(self.db.count_unread_notifications(ws), 1)
        reports = self.db.list_saved_reports(ws)
        self.assertTrue(any("自动" in r["title"] for r in reports))
        # 同日再跑：last_sent_at 保护，不重发
        stats2 = dispatch_due_report_subscriptions(self.db, now=now)
        self.assertEqual(stats2["due"], 0)
        # 清理
        self.db.delete_report_subscription(sub["subscription_id"], ws)

    def test_notification_purge_expired(self):
        ws = self.ws["workspace_id"]
        self.db.insert_notification({
            "notification_id": f"ntf_old_{self._suffix}",
            "workspace_id": ws, "principal_id": None,
            "title": "旧通知", "body": {}, "link": None,
            "created_at": "2020-01-01T00:00:00Z",
        })
        removed = self.db.purge_expired_notifications()
        self.assertGreaterEqual(removed, 1)
        items = self.db.list_notifications_by_workspace(ws)
        self.assertFalse(any(n["notification_id"] == f"ntf_old_{self._suffix}" for n in items))

    def test_deliver_alert_email_degrades_to_inapp(self):
        """SMTP 未配置时 email 渠道降级写站内通知（degraded）。"""
        import os
        from unittest import mock
        import alerts

        ws = self.ws["workspace_id"]
        rule = {
            "rule_id": f"al_{self._suffix}", "name": "邮件告警",
            "rule_type": "price_threshold", "market": "NEM",
            "region_or_zone": "NSW1", "channel_type": "email",
            "channel_target": f"user-{self._suffix}@acme.test", "workspace_id": ws,
        }
        # 强制未配置 SMTP，避免测试环境误发真实邮件
        env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("SMTP_") and not k.startswith("AGENT_ALERT_SMTP_")
        }
        with mock.patch.dict(os.environ, env, clear=True):
            result = alerts._deliver_alert(self.db, rule, {"result": {"value": 999}}, None)
        self.assertEqual(result["delivery_status"], "degraded")
        self.assertEqual(self.db.count_unread_notifications(ws), 1)


if __name__ == "__main__":
    unittest.main()
