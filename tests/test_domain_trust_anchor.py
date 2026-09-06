"""P0.3 域名信任锚 + P0.4 domain-join 密码跳过分支修复（2026-09-05）。

被锁定的安全不变量：
  1. 「登记域名」≠「获得授权能力」—— 只有 ``verified_at`` 非空的域名才能用于
     ``domain_auto_join_org`` / OIDC 自动入组织；
  2. 公共邮箱域名（gmail.com/163.com/…）禁止登记为组织域名，含子域形式；
  3. 域名所有权只能通过 DNS TXT 或 postmaster 邮件二选一证明，且两条路都
     fail-closed（解析器不可用 → 501，不降级放行）；
  4. 已验证域名不得被改指到别的组织，也不得在换域名字符串时保留验证状态；
  5. ``join_organization_by_domain`` 不得对「已存在但没有密码」的 principal
     静默放行（原缺陷：任意 password 即可接管并重设密码）。
"""

import os
import sys
import tempfile
import unittest
import uuid

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from database import DatabaseManager
import access_control
import server


class DomainTrustAnchorTests(unittest.TestCase):
    def setUp(self):
        self._s = uuid.uuid4().hex[:8]
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_orchestrator_db = server.job_orchestrator.db
        server.db = self.db
        server.job_orchestrator.db = self.db
        self.organization = server.create_organization_route(name=f"Anchor-{self._s}")
        self.org_id = self.organization["organization_id"]

    def tearDown(self):
        server.db = self.original_db
        server.job_orchestrator.db = self.original_orchestrator_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    # ---- helpers ----
    def _domain(self, label: str = "corp") -> str:
        return f"{label}-{self._s}.com"

    def _register(self, domain: str, join_mode: str = "domain_auto_join_org") -> dict:
        return server.create_organization_domain_route(
            organization_id=self.org_id,
            domain=domain,
            join_mode=join_mode,
        )

    def _verify_dns(self, domain_row: dict, domain: str) -> dict:
        """走完整 DNS TXT 流程：begin → 用假 resolver 提交正确记录值 → verify。"""
        begun = access_control.begin_domain_verification(
            self.db, organization_id=self.org_id, domain_id=domain_row["domain_id"], method="dns_txt"
        )
        record_value = begun["dns"]["record_value"]
        return access_control.verify_organization_domain(
            self.db,
            organization_id=self.org_id,
            domain_id=domain_row["domain_id"],
            method="dns_txt",
            resolver=lambda name: [record_value],
        )

    def _join(self, email: str, password: str = "Welc0mePass!"):
        return server.domain_join_route(
            server.DomainJoinRequest(
                organization_id=self.org_id,
                email=email,
                display_name="Joiner",
                password=password,
            )
        )

    # ---- 1. 公共域名黑名单 ----
    def test_public_email_domains_cannot_be_registered(self):
        for domain in ("gmail.com", "outlook.com", "163.com", "qq.com", "proton.me"):
            with self.subTest(domain=domain), self.assertRaises(HTTPException) as ctx:
                self._register(domain)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_public_domain_subdomain_is_also_rejected(self):
        # 只看末两级标签，否则 mail.gmail.com 可绕过黑名单
        with self.assertRaises(HTTPException) as ctx:
            self._register("mail.gmail.com")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_case_and_whitespace_normalisation_before_blacklist(self):
        with self.assertRaises(HTTPException) as ctx:
            self._register("  GMail.COM  ")
        self.assertEqual(ctx.exception.status_code, 400)

    # ---- 2. 登记后默认未验证 ----
    def test_registered_domain_starts_unverified(self):
        row = self._register(self._domain())
        self.assertFalse(row["verified"])
        self.assertIsNone(row["verified_at"])

    # ---- 3. 未验证域名不得 auto-join ----
    def test_unverified_domain_rejects_auto_join(self):
        self._register(self._domain())
        with self.assertRaises(HTTPException) as ctx:
            self._join(self._email("joiner"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("verif", str(ctx.exception.detail).lower())

    def _email(self, name: str) -> str:
        return f"{name}-{self._s}@{self._domain()}"

    def test_oidc_auto_join_path_also_requires_verified_domain(self):
        # OIDC callback 与域名策略共用同一个门（ensure_organization_membership_from_domain_policy）
        self._register(self._domain())
        principal = server.create_principal_route(email=self._email("oidc"), display_name="OIDC")
        with self.assertRaises(HTTPException) as ctx:
            access_control.ensure_organization_membership_from_domain_policy(
                self.db,
                organization_id=self.org_id,
                principal_id=principal["principal_id"],
                email=self._email("oidc"),
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_rejected_join_does_not_create_junk_principal(self):
        # 域名校验必须先于 seed_principal，否则注册接口成为垃圾数据放大器
        self._register(self._domain())
        email = self._email("ghost")
        with self.assertRaises(HTTPException):
            self._join(email)
        self.assertIsNone(self.db.fetch_principal_by_email(email))

    # ---- 4. DNS TXT 验证 ----
    def test_dns_txt_verification_grants_join(self):
        domain = self._domain()
        row = self._register(domain)
        begun = access_control.begin_domain_verification(
            self.db, organization_id=self.org_id, domain_id=row["domain_id"], method="dns_txt"
        )
        self.assertEqual(begun["dns"]["record_name"], f"_aus-ele-verify.{domain}")
        self.assertTrue(begun["dns"]["record_value"])
        self.assertFalse(self.db.fetch_organization_domain(row["domain_id"])["verified"])

        # 解析结果为空 → 验证失败，状态不变
        with self.assertRaises(HTTPException) as ctx:
            access_control.verify_organization_domain(
                self.db,
                organization_id=self.org_id,
                domain_id=row["domain_id"],
                method="dns_txt",
                token=begun["dns"]["record_value"],
                resolver=lambda name: [],
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertFalse(self.db.fetch_organization_domain(row["domain_id"])["verified"])

        # 别人域名的记录值不得通过（防串用）
        with self.assertRaises(HTTPException) as ctx:
            access_control.verify_organization_domain(
                self.db,
                organization_id=self.org_id,
                domain_id=row["domain_id"],
                method="dns_txt",
                token=begun["dns"]["record_value"],
                resolver=lambda name: ["aus-ele-verify=someone-elses-token"],
            )
        self.assertEqual(ctx.exception.status_code, 403)

        verified = access_control.verify_organization_domain(
            self.db,
            organization_id=self.org_id,
            domain_id=row["domain_id"],
            method="dns_txt",
            token=begun["dns"]["record_value"],
            resolver=lambda name: [begun["dns"]["record_value"]],
        )
        self.assertTrue(verified["verified"])
        self.assertIsNotNone(verified["verified_at"])
        # 验证完成后一次性 token 必须作废，避免离线重放
        self.assertIsNone(verified["verification_token"])

        payload = self._join(self._email("joiner"))
        self.assertEqual(payload["organization_membership"]["status"], "active")
        self.assertTrue(payload["organization_membership"]["role"], "org_member")

    def test_dns_txt_record_name_is_checked_by_resolver(self):
        # resolver 收到的查询名必须是本域名的 TXT 记录，不能是硬编码的别处
        domain = self._domain()
        row = self._register(domain)
        begun = access_control.begin_domain_verification(
            self.db, organization_id=self.org_id, domain_id=row["domain_id"], method="dns_txt"
        )
        seen = []

        def resolver(name: str):
            seen.append(name)
            return [begun["dns"]["record_value"]]

        access_control.verify_organization_domain(
            self.db,
            organization_id=self.org_id,
            domain_id=row["domain_id"],
            method="dns_txt",
            token=begun["dns"]["record_value"],
            resolver=resolver,
        )
        self.assertEqual(seen, [f"_aus-ele-verify.{domain}"])

    def test_dns_resolver_unavailable_fails_closed_501(self):
        domain = self._domain()
        row = self._register(domain)
        begun = access_control.begin_domain_verification(
            self.db, organization_id=self.org_id, domain_id=row["domain_id"], method="dns_txt"
        )

        def broken(_name: str):
            raise access_control.DomainVerificationUnavailable("no resolver")

        with self.assertRaises(HTTPException) as ctx:
            access_control.verify_organization_domain(
                self.db,
                organization_id=self.org_id,
                domain_id=row["domain_id"],
                method="dns_txt",
                token=begun["dns"]["record_value"],
                resolver=broken,
            )
        self.assertEqual(ctx.exception.status_code, 501)
        self.assertFalse(self.db.fetch_organization_domain(row["domain_id"])["verified"])

    def test_default_dns_resolver_is_configurable_entrypoint(self):
        # 生产默认解析器必须存在（dnspython 缺失时抛 DomainVerificationUnavailable，而非静默通过）
        self.assertTrue(callable(access_control.resolve_txt_records))

    # ---- 5. postmaster 邮件验证 ----
    def test_email_verification_sends_token_only_to_mailbox_role_addresses(self):
        domain = self._domain()
        row = self._register(domain)
        delivered = []

        def mailer(*, to: str, subject: str, body: str):
            delivered.append({"to": to, "body": body})
            return {"delivered": True, "degraded": False}

        begun = access_control.begin_domain_verification(
            self.db,
            organization_id=self.org_id,
            domain_id=row["domain_id"],
            method="email",
            mailer=mailer,
        )
        self.assertEqual(begun["email"]["targets"][0], f"postmaster@{domain}")
        self.assertTrue(all(rec["to"].endswith(f"@{domain}") for rec in delivered))
        # token 不得出现在 API 响应里，否则登记即等于自证通过
        self.assertNotIn("verification_token", begun)
        self.assertNotIn("record_value", begun.get("email", {}))
        sent_token = self.db.fetch_organization_domain(row["domain_id"])["verification_token"]
        self.assertTrue(sent_token)
        self.assertIn(sent_token, delivered[0]["body"])

        with self.assertRaises(HTTPException) as ctx:
            access_control.verify_organization_domain(
                self.db,
                organization_id=self.org_id,
                domain_id=row["domain_id"],
                method="email",
                token="guessed-token",
            )
        self.assertEqual(ctx.exception.status_code, 403)

        verified = access_control.verify_organization_domain(
            self.db,
            organization_id=self.org_id,
            domain_id=row["domain_id"],
            method="email",
            token=sent_token,
        )
        self.assertTrue(verified["verified"])

    def test_email_verification_degrades_when_smtp_missing(self):
        domain = self._domain()
        row = self._register(domain)

        def degraded_mailer(**_kw):
            return {"delivered": False, "degraded": True, "reason": "smtp_not_configured"}

        with self.assertRaises(HTTPException) as ctx:
            access_control.begin_domain_verification(
                self.db,
                organization_id=self.org_id,
                domain_id=row["domain_id"],
                method="email",
                mailer=degraded_mailer,
            )
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertFalse(self.db.fetch_organization_domain(row["domain_id"])["verified"])

    def test_unknown_verification_method_is_rejected(self):
        row = self._register(self._domain())
        with self.assertRaises(HTTPException) as ctx:
            access_control.begin_domain_verification(
                self.db, organization_id=self.org_id, domain_id=row["domain_id"], method="telepathy"
            )
        self.assertEqual(ctx.exception.status_code, 422)

    # ---- 6. 域名指向保护 ----
    def test_domain_cannot_be_repointed_to_another_organization(self):
        domain = self._domain()
        self._register(domain)
        other = server.create_organization_route(name=f"Rival-{self._s}")
        with self.assertRaises(HTTPException) as ctx:
            server.create_organization_domain_route(
                organization_id=other["organization_id"],
                domain=domain,
                join_mode="domain_auto_join_org",
            )
        self.assertEqual(ctx.exception.status_code, 409)

    def test_changing_domain_string_resets_verification(self):
        # ON CONFLICT(domain_id) DO UPDATE SET domain=... 会把 verified_at 一起带过去，
        # 若不重置，则「验证 A 域 → 改成 B 域」可直接白拿 B 域的授权能力
        row = self._register(self._domain("first"))
        self._verify_dns(row, self._domain("first"))
        self.assertTrue(self.db.fetch_organization_domain(row["domain_id"])["verified"])

        renamed = self.db.upsert_organization_domain(
            {
                **self.db.fetch_organization_domain(row["domain_id"]),
                "domain": self._domain("second"),
                "updated_at": access_control._utc_now_iso(),
            }
        )
        self.assertFalse(renamed["verified"])
        self.assertIsNone(renamed["verified_at"])

    def test_verification_is_scoped_to_owning_organization(self):
        row = self._register(self._domain())
        other = server.create_organization_route(name=f"Nosy-{self._s}")
        with self.assertRaises(HTTPException) as ctx:
            access_control.begin_domain_verification(
                self.db,
                organization_id=other["organization_id"],
                domain_id=row["domain_id"],
                method="dns_txt",
            )
        self.assertEqual(ctx.exception.status_code, 404)

    # ---- 7. P0.4：无密码 principal 不得被接管 ----
    def test_passwordless_principal_cannot_be_taken_over_via_domain_join(self):
        domain = self._domain()
        row = self._register(domain)
        self._verify_dns(row, domain)

        # OAuth/邀请链路产生的 principal 常常没有 password_hash
        principal = server.create_principal_route(email=self._email("oauthish"), display_name="OAuthish")
        self.assertFalse(principal.get("password_hash"))

        with self.assertRaises(HTTPException) as ctx:
            self._join(self._email("oauthish"), password="AttackerChoosesThis!")
        self.assertEqual(ctx.exception.status_code, 403)

        after = self.db.fetch_principal_by_email(self._email("oauthish"))
        self.assertFalse(after.get("password_hash"), "接管尝试不得写入攻击者选择的密码")

    def test_domain_join_still_works_for_existing_password_principal(self):
        domain = self._domain()
        row = self._register(domain)
        self._verify_dns(row, domain)
        email = self._email("pwuser")

        first = self._join(email, password="FirstPass123")
        self.assertTrue(first["principal"].get("password_hash"))

        # 密码正确 → 正常登录式放行
        again = access_control.join_organization_by_domain(
            self.db,
            organization_id=self.org_id,
            email=email,
            display_name="PW User",
            password="FirstPass123",
        )
        self.assertEqual(again["principal"]["email"], email)

    def test_domain_join_rejects_wrong_password_for_existing_principal(self):
        domain = self._domain()
        row = self._register(domain)
        self._verify_dns(row, domain)
        email = self._email("pwuser2")
        self._join(email, password="GoodPass123")

        with self.assertRaises(HTTPException) as ctx:
            self._join(email, password="WrongPass456")
        self.assertEqual(ctx.exception.status_code, 401)


class PublicDomainBlacklistConsistencyTests(unittest.TestCase):
    """黑名单必须与 data/assumptions_registry.json 的登记保持同步。"""

    def test_blacklist_matches_assumptions_registry(self):
        import json

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(root, "data", "assumptions_registry.json"), encoding="utf-8") as fh:
            registry = json.load(fh)
        entry = next(
            item for item in registry["assumptions"]
            if item["id"] == "domain_verification_required_for_auto_join"
        )
        registered = {d.strip().lower() for d in entry["value"]["public_domain_blacklist"]}
        self.assertEqual(registered, set(access_control.PUBLIC_EMAIL_DOMAINS))


if __name__ == "__main__":
    unittest.main()
