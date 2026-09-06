"""自助注册与邮箱验证端点测试（R1.1，2026-09-06）。

覆盖的是**安全不变量**而不是表单字段：token 不外泄、链接一次性、重发作废旧挑战、
发信失败不留有效凭据、未验证是软限制（账户当场可用）、以及验证状态列的单调性。
DatabaseManager 为 PG-only 且所有测试共享同一个库 → 邮箱一律带随机后缀（与
test_account_routes.py 同一策略），因此本文件不做 TRUNCATE，不清别人的数据。
"""

import datetime
import os
import re
import unittest
import uuid
from unittest import mock

from tests.support import ensure_repo_import_paths, offline_state_store, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from access_control import authenticate_access_token  # noqa: E402
from database import DatabaseManager  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routes import account_routes, registration_routes  # noqa: E402
from services import email_verification  # noqa: E402

STRONG = "Maple-Drum-77!grid"
_TOKEN_RE = re.compile(r"token=([A-Za-z0-9_\-]+)")


def _utc_iso(moment: datetime.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


class RegistrationRoutesTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.email = f"user-{self.suffix}@analytical.test"
        self.db = DatabaseManager(None)
        self.mails = []
        self._start = [
            mock.patch.object(registration_routes, "get_db", lambda: self.db),
            mock.patch.object(account_routes, "get_db", lambda: self.db),
            # 一个测试一个 store 实例：生产里 get_state_store() 返回的是模块级单例，
            # 若在这里每次调用都新建，限流窗口永远数不到第二次请求（= 限流测试假绿）。
            mock.patch.object(registration_routes, "get_state_store",
                              lambda: self.state_store),
        ]
        self.state_store = offline_state_store()
        for patcher in self._start:
            patcher.start()
        self.addCleanup(mock.patch.stopall)
        self.app = FastAPI()
        self.app.include_router(registration_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    # -- helpers ---------------------------------------------------------

    def enable_smtp(self, *, delivered=True):
        def _send(to, subject, body, **kwargs):
            self.mails.append({"to": to, "subject": subject, "body": body})
            return {"delivered": bool(delivered), "degraded": not delivered,
                    "reason": None if delivered else "test refused"}

        self._mail_patchers = [
            mock.patch("services.email_sender.smtp_configured", lambda: True),
            mock.patch("services.email_sender.send_email", _send),
        ]
        for patcher in self._mail_patchers:
            patcher.start()

    def disable_smtp(self):
        self._mail_patchers = [mock.patch("services.email_sender.smtp_configured", lambda: False)]
        for patcher in self._mail_patchers:
            patcher.start()

    def register(self, email=None, password=STRONG, display_name="Ada Lovelace"):
        return self.client.post("/api/v1/register", json={
            "email": email or self.email, "password": password, "display_name": display_name})

    def mail_token(self, index=-1) -> str:
        return _TOKEN_RE.search(self.mails[index]["body"]).group(1)

    def seed_challenge(self, principal_id, email, *, token=None, expires_delta_seconds=3600):
        """直接落一条挑战（用于过期/邮箱变更这类无法通过公开端点构造的状态）。"""
        token = token or "tok_" + uuid.uuid4().hex
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.insert_email_verification({
            "verification_id": f"emv_{uuid.uuid4().hex[:12]}",
            "principal_id": principal_id,
            "email": email,
            "token_hash": email_verification.hash_token(token),
            "requested_at": _utc_iso(now),
            "expires_at": _utc_iso(now + datetime.timedelta(seconds=expires_delta_seconds)),
            "used_at": None,
        })
        return token

    # -- 注册主链路 ------------------------------------------------------

    def test_register_returns_session_that_really_authenticates(self):
        self.enable_smtp()
        response = self.register()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["email"], self.email)
        self.assertFalse(body["email_verified"])
        self.assertEqual(body["verification_status"], "sent")
        self.assertEqual(len(self.mails), 1)
        # 签出的是与普通登录同形的会话：未验证不削弱可用性（软限制）
        actor = authenticate_access_token(self.db, body["access_token"])
        self.assertEqual(actor["principal"]["email"], self.email)
        self.assertEqual(actor["membership"]["role"], "owner")
        self.assertEqual(actor["organization_membership"]["role"], "org_owner")

    def test_response_never_leaks_verification_token(self):
        self.enable_smtp()
        response = self.register()
        token = self.mail_token()
        # 只断言「验证 token 不在响应里」：响应本身合法携带 access_token/session_token，
        # 用宽泛的 "token" 子串做断言会永远为假，等于没测。
        body = response.json()
        self.assertNotIn(token, response.text)
        self.assertNotIn(token, str(body.values()))
        # 库里只存摘要
        record = self.db.fetch_email_verification_by_token_hash(
            email_verification.hash_token(token))
        self.assertIsNotNone(record)
        self.assertNotIn(token, str(record))
        self.assertNotIn(record["token_hash"], response.text)

    def test_verification_link_is_absolute_url(self):
        self.enable_smtp()
        with mock.patch.dict(os.environ, {"AUS_ELE_PUBLIC_BASE_URL": "https://app.example.test/"}):
            self.register()
        self.assertIn("https://app.example.test/verify-email?token=", self.mails[-1]["body"])

    def test_weak_password_rejected_before_any_account_is_created(self):
        self.enable_smtp()
        response = self.register(password="Password123!")
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "weak_password")
        self.assertTrue(detail["errors"])
        self.assertIsNone(self.db.fetch_principal_by_email(self.email))
        self.assertEqual(self.mails, [])

    def test_email_availability_checked_after_password_policy(self):
        """先拒弱密码再报占用：否则弱密码请求变成免费的邮箱枚举探针。"""
        self.enable_smtp()
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.register(password="short").status_code, 422)
        dup = self.register()
        self.assertEqual(dup.status_code, 409)

    def test_email_without_at_rejected(self):
        self.enable_smtp()
        self.assertEqual(self.register(email="no-at-sign").status_code, 422)

    def test_feature_flag_closed_blocks_register_and_resend_but_not_verify(self):
        self.enable_smtp()
        self.assertEqual(self.register().status_code, 201)
        principal = self.db.fetch_principal_by_email(self.email)
        live = self.seed_challenge(principal["principal_id"], self.email)
        with mock.patch.dict(os.environ, {"AUS_ELE_ENABLE_SELF_SERVICE_REGISTER": "false"}):
            self.assertEqual(self.client.post("/api/v1/register", json={
                "email": f"new-{self.suffix}@analytical.test",
                "password": STRONG, "display_name": "New User"}).status_code, 403)
            self.assertEqual(self.client.post("/api/v1/register/resend",
                                              json={"email": self.email}).status_code, 403)
            # 已发出的链接必须仍可消费：回滚开关不能把用户推进死路
            ok = self.client.post("/api/v1/register/verify", json={"token": live})
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertTrue(ok.json()["email_verified_at"])

    # -- 验证链接的四种结局 ---------------------------------------------

    def test_verify_sets_timestamp_and_link_is_single_use(self):
        self.enable_smtp()
        self.register()
        token = self.mail_token()
        ok = self.client.post("/api/v1/register/verify", json={"token": token})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["email"], self.email)
        self.assertTrue(ok.json()["email_verified_at"])
        self.assertTrue(self.db.fetch_principal_by_email(self.email)["email_verified_at"])
        replay = self.client.post("/api/v1/register/verify", json={"token": token})
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.json()["detail"],
                         self.client.post("/api/v1/register/verify",
                                          json={"token": "nonexistent-token-x"}).json()["detail"])

    def test_verify_rejects_expired_link(self):
        self.enable_smtp()
        self.register()
        principal = self.db.fetch_principal_by_email(self.email)
        expired = self.seed_challenge(principal["principal_id"], self.email,
                                      expires_delta_seconds=-60)
        self.assertEqual(self.client.post("/api/v1/register/verify",
                                          json={"token": expired}).status_code, 400)
        self.assertIsNone(principal["email_verified_at"])

    def test_verify_rejects_challenge_bound_to_previous_email(self):
        """改过邮箱后旧链接必须失效：否则「验 a」给改成 b 的账户盖了已验证章。"""
        self.enable_smtp()
        self.register()
        principal = self.db.fetch_principal_by_email(self.email)
        stale = self.seed_challenge(principal["principal_id"], f"old-{self.suffix}@analytical.test")
        self.assertEqual(self.client.post("/api/v1/register/verify",
                                          json={"token": stale}).status_code, 400)
        self.assertIsNone(self.db.fetch_principal(principal["principal_id"])["email_verified_at"])

    def test_verify_rejects_unreadable_expiry_fail_closed(self):
        self.enable_smtp()
        self.register()
        principal = self.db.fetch_principal_by_email(self.email)
        token = self.seed_challenge(principal["principal_id"], self.email)
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE email_verification SET expires_at = 'not-a-date' WHERE principal_id = ?",
                (principal["principal_id"],))
            conn.commit()
        self.assertEqual(self.client.post("/api/v1/register/verify",
                                          json={"token": token}).status_code, 400)

    # -- 重发 -----------------------------------------------------------

    def test_resend_invalidates_previous_challenge(self):
        self.enable_smtp()
        self.register()
        first = self.mail_token()
        r = self.client.post("/api/v1/register/resend", json={"email": self.email})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(len(self.mails), 2)
        self.assertEqual(self.client.post("/api/v1/register/verify",
                                          json={"token": first}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/register/verify",
                                          json={"token": self.mail_token()}).status_code, 200)

    def test_resend_is_enumeration_safe_then_rate_limited(self):
        self.enable_smtp()
        ghost = f"ghost-{self.suffix}@analytical.test"
        seen = set()
        for _ in range(3):
            r = self.client.post("/api/v1/register/resend", json={"email": ghost})
            self.assertEqual(r.status_code, 202)
            seen.add(r.text)
        self.assertEqual(seen, {"{\"accepted\":true}"})
        self.assertEqual(self.mails, [])  # 不存在的邮箱不会发信
        limited = self.client.post("/api/v1/register/resend", json={"email": ghost})
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited.headers)

    def test_register_ip_rate_limit_is_configurable(self):
        self.enable_smtp()
        with mock.patch.dict(os.environ, {"AUS_ELE_REGISTER_IP_LIMIT": "2"}):
            codes = [self.register(email=f"u{i}-{self.suffix}@analytical.test").status_code
                     for i in range(3)]
        self.assertEqual(codes, [201, 201, 429])

    # -- SMTP 降级 ------------------------------------------------------

    def test_smtp_missing_auto_verifies_when_flag_true(self):
        self.disable_smtp()
        with self.assertLogs("services.email_verification", level="WARNING"):
            body = self.register().json()
        self.assertEqual(body["verification_status"], "auto_verified")
        self.assertTrue(body["email_verified"])

    def test_smtp_missing_without_auto_verify_keeps_account_usable(self):
        self.disable_smtp()
        with mock.patch.dict(os.environ, {"AUS_ELE_AUTO_VERIFY_WHEN_NO_SMTP": "false"}):
            with self.assertLogs("services.email_verification", level="WARNING"):
                response = self.register()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["verification_status"], "not_configured")
        self.assertFalse(body["email_verified"])
        self.assertTrue(authenticate_access_token(self.db, body["access_token"]))

    def test_send_failure_leaves_no_live_challenge(self):
        self.enable_smtp(delivered=False)
        body = self.register().json()
        self.assertEqual(body["verification_status"], "send_failed")
        self.assertEqual(len(self.mails), 1)
        token = self.mail_token()
        record = self.db.fetch_email_verification_by_token_hash(
            email_verification.hash_token(token))
        self.assertIsNotNone(record["used_at"])
        self.assertEqual(self.client.post("/api/v1/register/verify",
                                          json={"token": token}).status_code, 400)

    # -- 状态查询与列单调性 ---------------------------------------------

    def test_status_requires_bearer_and_reports_verification(self):
        self.enable_smtp()
        self.assertEqual(self.client.get("/api/v1/register/status").status_code, 401)
        token = self.register().json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        body = self.client.get("/api/v1/register/status", headers=headers).json()
        self.assertEqual(body["email"], self.email)
        self.assertFalse(body["email_verified"])
        self.assertTrue(body["workspace_id"])
        self.assertTrue(self.client.post("/api/v1/register/verify",
                                         json={"token": self.mail_token()}).status_code == 200)
        self.assertTrue(self.client.get("/api/v1/register/status", headers=headers)
                        .json()["email_verified"])

    def test_upsert_principal_cannot_unverify(self):
        """不带 email_verified_at 的 upsert（seed_principal 一类构造）不得把已验证打回未验证。"""
        self.enable_smtp()
        self.assertEqual(self.register().status_code, 201)
        principal_id = self.db.fetch_principal_by_email(self.email)["principal_id"]
        verified_at = _utc_iso(datetime.datetime.now(datetime.timezone.utc))
        self.db.mark_principal_email_verified(principal_id, verified_at)
        row = self.db.fetch_principal(principal_id)
        self.db.upsert_principal({k: v for k, v in row.items() if k != "email_verified_at"})
        self.assertEqual(self.db.fetch_principal(principal_id)["email_verified_at"], verified_at)
        # 反向也不可行：mark 的 WHERE 已排除非 NULL
        self.db.mark_principal_email_verified(principal_id, "2000-01-01T00:00:00Z")
        self.assertEqual(self.db.fetch_principal(principal_id)["email_verified_at"], verified_at)


if __name__ == "__main__":
    unittest.main()
