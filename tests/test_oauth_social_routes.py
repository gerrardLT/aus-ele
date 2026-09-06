"""社交登录端点测试（R1.2，2026-09-06）。

锁的是四条不安全就白做的不变量：

1. **state 是服务端一次性凭据**（重放第二次必须失败、跨 provider 必须失败）；
2. **回调地址与落地地址不可被调用方影响**（redirect_uri / next 是攻击者的常规入手点）；
3. **只有提供方担保已验证的邮箱才能落地**，且社交登录**永不自动加入别人的组织**；
4. **签发出的令牌真的可用**（用 ``authenticate_access_token`` 回读，而不是只看响应里有
   一个像 token 的字符串）。

所有对外 HTTP 都被替换成假 IdP（``FakeTransport``）：测试既不打 Google/GitHub，也不受
网络影响；同时假 IdP 是**唯一**能构造「返回了未验证邮箱」「/user/emails 为空」这类
上游异常态的手段。

DatabaseManager 为 PG-only 且全部测试共享同一个库 → 本文件在 setUp 里 TRUNCATE 认证/RBAC
表（``reset_access_control_tables``）。只清认证链路，不动行情与分析数据；理由是身份匹配
优先按 ``auth_identity`` 的 (provider_type, provider_key, subject) 命中，固定的 subject
（``g-100``）在不清库时会让后一个测试登录进前一个测试留下的 principal，报出
``no_workspace`` 这种与被测逻辑无关的红项。
"""

import os
import unittest
import uuid
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlparse

from tests.support import (
    ensure_repo_import_paths,
    offline_state_store,
    reset_access_control_tables,
    stub_optional_dep,
)

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from access_control import authenticate_access_token  # noqa: E402
from database import DatabaseManager  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402  (FakeTransport 需要真实的 HTTPStatusError 异常类)
from oauth_providers import OAuthRejected, OAuthUpstreamError  # noqa: E402
from routes import oauth_routes  # noqa: E402

BASE_URL = "https://app.test"
GOOGLE_ENV = {
    "AUS_ELE_OAUTH_GOOGLE_CLIENT_ID": "google-client",
    "AUS_ELE_OAUTH_GOOGLE_CLIENT_SECRET": "google-secret",
}
GITHUB_ENV = {
    "AUS_ELE_OAUTH_GITHUB_CLIENT_ID": "gh-client",
    "AUS_ELE_OAUTH_GITHUB_CLIENT_SECRET": "gh-secret",
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "" if status_code < 400 else "upstream boom"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=self)


class FakeTransport:
    """替换 ``oauth_providers.httpx``：按 URL 尾缀路由到预置响应。"""

    # 被测代码在 ``except httpx.HTTPStatusError`` 里按属性取异常类，而 except 子句是
    # **运行时**求值的：桩里没有这个名字，AttributeError 会把 500 冒充成上游异常。
    HTTPStatusError = httpx.HTTPStatusError

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _dispatch(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        for key, payload in self.routes.items():
            if key in url:
                if isinstance(payload, tuple):
                    body, status = payload
                    return FakeResponse(body, status)
                return FakeResponse(payload)
        return FakeResponse({"error": "unrouted"}, 500)

    def get(self, url, **kwargs):
        return self._dispatch("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._dispatch("POST", url, **kwargs)


def google_profile(subject="g-100", email=None, verified=True, name="Ada Lovelace"):
    return {
        "sub": subject,
        "email": email or "ada@analytical.test",
        "email_verified": verified,
        "name": name,
    }


def github_profile(user_id="42", login="adal", email=None, name="Ada Lovelace"):
    return {"id": user_id, "login": login, "name": name, "email": email}


def github_emails(*entries):
    return list(entries)


class OAuthSocialRouteTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        self.state_store = offline_state_store()
        patchers = [
            mock.patch.object(oauth_routes, "get_state_store", lambda: self.state_store),
            mock.patch.dict(os.environ, {"AUS_ELE_PUBLIC_BASE_URL": BASE_URL,
                                         "AUS_ELE_ENABLE_SOCIAL_LOGIN": "true"}),
        ]
        patchers.append(mock.patch.object(oauth_routes, "_get_db", lambda: self.db))
        # 发现文档默认打网络且结果随 Google 变更而变 → 一律换成内置常量；这本身也要测
        # （见 DiscoveryTests），所以是注入 transport 而不是删掉 _fetch_discovery。
        # 而 _fetch_discovery 的缓存走 shared_state 单例：不一起换掉的话每个用例都要付
        # 一次「本机没起 Redis → 连接超时」的时间税（实测 37 例 45s）。
        patchers.append(mock.patch("shared_state.get_state_store", lambda: self.state_store))
        for patcher in patchers:
            patcher.start()
        self.addCleanup(mock.patch.stopall)

        self.app = FastAPI()
        self.app.include_router(oauth_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False, follow_redirects=False)

    # -- helpers ---------------------------------------------------------

    def use_env(self, extra: dict):
        patcher = mock.patch.dict(os.environ, extra)
        patcher.start()
        self.addCleanup(patcher.stop)

    def configure_google(self):
        self.use_env(GOOGLE_ENV)

    def configure_github(self):
        self.use_env(GITHUB_ENV)

    def fake_idp(self, routes):
        transport = FakeTransport(routes)
        patcher = mock.patch("oauth_providers.httpx", transport)
        patcher.start()
        self.addCleanup(patcher.stop)
        return transport

    def start(self, provider="google", **query):
        url = f"/api/v1/auth/oauth/{provider}/start"
        if query:
            url = f"{url}?{urlencode(query)}"
        return self.client.get(url)

    def start_state(self, provider="google", **query):
        response = self.start(provider, **query)
        self.assertEqual(response.status_code, 302, response.text)
        return parse_qs(urlparse(response.headers["location"]).query)["state"][0]

    def start_state_url(self, provider="google", **query):
        """授权 URL 本身（不只是 state）：验证端点主机、PKCE、redirect_uri 都要用它。"""
        response = self.start(provider, **query)
        self.assertEqual(response.status_code, 302, response.text)
        return response.headers["location"]

    def callback(self, provider="google", **query):
        return self.client.get(f"/api/v1/auth/oauth/{provider}/callback", params=query)

    @staticmethod
    def fragment_params(response):
        self_loc = response.headers.get("location", "")
        return parse_qs(urlparse(self_loc).fragment)

    @staticmethod
    def error_code(response):
        return OAuthSocialRouteTests.fragment_params(response).get("oauth_error", [""])[0]

    def principal_count(self, email):
        return self.db.fetch_principal_by_email(email)


# ---------------------------------------------------------------- 入口发现 --


class ProviderListingTests(OAuthSocialRouteTests):
    def test_no_providers_when_unconfigured(self):
        payload = self.client.get("/api/v1/auth/oauth/providers").json()
        self.assertEqual(payload["providers"], [])

    def test_configured_provider_listed_without_leaking_secrets(self):
        self.configure_google()
        payload = self.client.get("/api/v1/auth/oauth/providers").json()
        keys = [item["key"] for item in payload["providers"]]
        self.assertEqual(keys, ["google"])
        body = self.client.get("/api/v1/auth/oauth/providers").text
        self.assertNotIn("google-secret", body)
        self.assertNotIn("client_id", body)

    def test_disabled_flag_hides_every_entry(self):
        self.configure_google()
        self.use_env({"AUS_ELE_ENABLE_SOCIAL_LOGIN": "false"})
        self.assertEqual(self.client.get("/api/v1/auth/oauth/providers").json()["providers"], [])
        self.assertEqual(self.start().status_code, 404)


class StartTests(OAuthSocialRouteTests):
    def test_unknown_provider_is_404(self):
        self.configure_google()
        self.assertEqual(self.client.get("/api/v1/auth/oauth/feishu/start").status_code, 404)

    def test_unconfigured_provider_is_404(self):
        self.assertEqual(self.start("github").status_code, 404)

    def test_authorization_url_points_at_builtin_google_endpoints(self):
        self.configure_google()
        location = urlparse(self.start_state_url())
        self.assertEqual(f"{location.scheme}://{location.netloc}{location.path}",
                         "https://accounts.google.com/o/oauth2/v2/auth")

    def test_redirect_uri_is_server_built_and_ignores_client_param(self):
        """客户端传入的 redirect_uri 必须完全无效（否则授权码会被转发到攻击者主机）。"""
        self.configure_google()
        state = self.start_state(redirect_uri="https://evil.test/steal")
        query = parse_qs(urlparse(self.start().headers["location"]).query)
        self.assertEqual(query["redirect_uri"][0], f"{BASE_URL}/api/v1/auth/oauth/google/callback")
        self.assertNotIn("evil.test", self.start().headers["location"])
        self.assertTrue(state)

    def test_pkce_sent_for_google_and_uses_s256(self):
        self.configure_google()
        query = parse_qs(urlparse(self.start_state_url()).query)
        self.assertEqual(query["code_challenge_method"][0], "S256")
        self.assertIn("code_challenge", query)
        # verifier 绝不能出现在授权 URL 里（那是它唯一一次以明文离开服务端的机会）
        self.assertNotIn("code_verifier", query)

    def test_state_is_stored_by_digest_not_plain_value(self):
        self.configure_google()
        state = self.start_state()
        listed = self.state_store.keys(oauth_routes._STATE_SCOPE)
        self.assertNotIn(state, listed)
        import hashlib

        self.assertIn(hashlib.sha256(state.encode("utf-8")).hexdigest(), listed)

    def test_start_is_rate_limited_per_ip(self):
        self.configure_google()
        self.use_env({"AUS_ELE_OAUTH_START_RATE_LIMIT": "2"})
        headers = {"X-Real-IP": "203.0.113.9"}
        for _ in range(2):
            self.assertEqual(self.client.get("/api/v1/auth/oauth/google/start", headers=headers).status_code, 302)
        third = self.client.get("/api/v1/auth/oauth/google/start", headers=headers)
        self.assertEqual(third.status_code, 429)
        self.assertIn("Retry-After", third.headers)

    def test_rate_limit_is_per_ip_not_global(self):
        self.configure_google()
        self.use_env({"AUS_ELE_OAUTH_START_RATE_LIMIT": "1"})
        self.assertEqual(self.client.get("/api/v1/auth/oauth/google/start",
                                         headers={"X-Real-IP": "203.0.113.1"}).status_code, 302)
        self.assertEqual(self.client.get("/api/v1/auth/oauth/google/start",
                                         headers={"X-Real-IP": "203.0.113.2"}).status_code, 302)

    def test_github_start_omits_pkce_but_keeps_state(self):
        self.configure_github()
        query = parse_qs(urlparse(self.start("github").headers["location"]).query)
        self.assertNotIn("code_challenge", query)
        self.assertIn("state", query)
        self.assertEqual(query["scope"][0], "read:user user:email")


class CallbackStateTests(OAuthSocialRouteTests):
    def setUp(self):
        super().setUp()
        self.configure_google()

    def test_missing_state_is_rejected(self):
        response = self.callback(code="abc")
        self.assertEqual(self.error_code(response), "state_invalid")

    def test_unknown_state_is_rejected(self):
        response = self.callback(code="abc", state="not-a-real-state")
        self.assertEqual(self.error_code(response), "state_invalid")

    def test_state_is_single_use(self):
        """一次性：第二次回调必须失败（recall+forget 两步实现会在这里露馅）。"""
        state = self.start_state()
        self.fake_idp({"/token": {"access_token": "t"}, "/userinfo": google_profile()})
        first = self.callback(code="c1", state=state)
        self.assertIn("oauth_access_token", self.fragment_params(first))
        second = self.callback(code="c1", state=state)
        self.assertEqual(self.error_code(second), "state_invalid")

    def test_state_cannot_be_consumed_on_another_provider(self):
        self.configure_github()
        state = self.start_state("google")
        response = self.callback("github", code="c", state=state)
        self.assertEqual(self.error_code(response), "state_invalid")

    def test_provider_error_consumes_state_and_redirects(self):
        state = self.start_state()
        response = self.callback(error="access_denied", state=state)
        self.assertEqual(self.error_code(response), "provider_denied")
        # 已消费的 state 即使配上合法 code 也不能再走通
        self.fake_idp({"/token": {"access_token": "t"}, "/userinfo": google_profile()})
        self.assertEqual(self.error_code(self.callback(code="c", state=state)), "state_invalid")

    def test_success_response_is_no_store(self):
        """回调响应里带着会话令牌，绝不允许被共享缓存留存。"""
        state = self.start_state()
        self.fake_idp({"/token": {"access_token": "t"}, "/userinfo": google_profile()})
        response = self.callback(code="c", state=state)
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_missing_base_url_still_lands_relative(self):
        """``_landing_url`` 的兜底：拼不出绝对地址时退回站内相对路径，而不是抛出去变 500。

        端点层面已经不会走到这一步（根地址缺失时 provider 直接判为不可用 → 501，见
        ``test_missing_base_url_blocks_start_and_hides_button``），所以这里测的是那个
        兜底分支本身 —— 它是「失败必须回到登录页」这条约定的最后一道保险。
        """
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("AUS_ELE_PUBLIC_BASE_URL", None)
        self.assertEqual(
            oauth_routes._landing_url("oauth_error=state_invalid"),
            "/login#oauth_error=state_invalid")
        os.environ["AUS_ELE_PUBLIC_BASE_URL"] = BASE_URL
        self.assertEqual(
            oauth_routes._landing_url("oauth_error=state_invalid"),
            f"{BASE_URL}/login#oauth_error=state_invalid")

    def test_missing_base_url_blocks_start_and_hides_button(self):
        """根地址缺失时 /start 必须是 501（配错），不是 302 把用户送去必然 mismatch 的 IdP。

        同时 /providers 不得再广告这个入口 —— 判据必须是同一个，否则前端出现
        「按钮在、点了报错」的割裂状态。
        """
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("AUS_ELE_PUBLIC_BASE_URL", None)
        self.assertEqual(self.start().status_code, 501)
        listed = self.client.get("/api/v1/auth/oauth/providers").json()["providers"]
        self.assertEqual([p["key"] for p in listed], [])
        # 回调同样早退：不能先消费掉 state 再失败，那会让用户卡在「点了没反应」
        self.assertEqual(self.callback(code="c", state="anything").status_code, 501)

    def test_return_to_rejects_absolute_and_protocol_relative(self):
        self.fake_idp({"/token": {"access_token": "t"}, "/userinfo": google_profile()})
        for bad in ("https://evil.test/x", "//evil.test/x", "/\\evil.test"):
            state = self.start_state(next=bad)
            response = self.callback(code="c", state=state)
            self.assertEqual(self.fragment_params(response).get("oauth_return_to", [""])[0], "", bad)
        state = self.start_state(next="/account")
        response = self.callback(code="c", state=state)
        self.assertEqual(self.fragment_params(response)["oauth_return_to"][0], "/account")


class CallbackIdentityTests(OAuthSocialRouteTests):
    def setUp(self):
        super().setUp()
        self.configure_google()
        self.email = f"social-{self.suffix}@analytical.test"

    def google_routes(self, profile=None):
        return {
            "/token": {"access_token": "at"},
            "/userinfo": profile or google_profile(email=self.email),
        }

    def login(self, profile=None):
        state = self.start_state()
        self.fake_idp(self.google_routes(profile))
        response = self.callback(code="code-1", state=state)
        return response, self.fragment_params(response)

    def test_new_user_gets_own_org_workspace_and_working_token(self):
        response, params = self.login()
        self.assertIn("oauth_access_token", params, response.text)
        token = params["oauth_access_token"][0]
        actor = authenticate_access_token(self.db, token)
        # 正向对照：邮箱一致时「提供方已验证」必须真的落下，否则另一个测试里
        # 「不一致所以没落下」的断言只是因为整条链路坏了而通过。
        self.assertIsNotNone(self.db.fetch_principal(actor["principal"]["principal_id"]).get("email_verified_at"))
        self.assertEqual(actor["workspace"]["workspace_id"], params["oauth_workspace_id"][0])
        self.assertEqual(actor["principal"]["email"], self.email)
        orgs = self.db.list_organizations_for_principal(actor["principal"]["principal_id"]) \
            if hasattr(self.db, "list_organizations_for_principal") else None
        if orgs is not None:
            self.assertEqual(len(orgs), 1, "社交登录应当只自建一个组织")
        # org_owner：能过 org_manage 检查（证明注册账户与社交账户权限同形）
        from access_control import check_organization_permission

        organization_id = actor["workspace"]["organization_id"]
        org_actor = self.db.fetch_organization_membership(organization_id, actor["principal"]["principal_id"])
        self.assertEqual(org_actor["role"], "org_owner")
        check_organization_permission(
            {"organization_membership": org_actor, "principal": actor["principal"],
             "organization": self.db.fetch_organization(organization_id)}, "org_manage")

    def test_second_login_reuses_same_principal_and_identity_row(self):
        first, first_params = self.login()
        principal_a = authenticate_access_token(self.db, first_params["oauth_access_token"][0])["principal"]
        second, second_params = self.login()
        principal_b = authenticate_access_token(self.db, second_params["oauth_access_token"][0])["principal"]
        self.assertEqual(principal_a["principal_id"], principal_b["principal_id"])
        rows = self.db.fetch_auth_identity_by_subject("social", "google", "g-100")
        self.assertIsNotNone(rows)

    def test_existing_password_account_is_linked_not_duplicated(self):
        from services import onboarding

        provisioned = onboarding.provision_account(
            self.db, email=self.email, display_name="Existing", password="Maple-Drum-77!grid")
        _, params = self.login()
        actor = authenticate_access_token(self.db, params["oauth_access_token"][0])
        self.assertEqual(actor["principal"]["principal_id"], provisioned["principal"]["principal_id"])
        self.assertEqual(actor["workspace"]["workspace_id"], provisioned["workspace"]["workspace_id"])

    def test_unverified_email_is_refused_and_creates_no_principal(self):
        _response, params = self.login(profile=google_profile(email=self.email, verified=False))
        self.assertEqual(params["oauth_error"][0], "email_unverified")
        self.assertIsNone(self.db.fetch_principal_by_email(self.email))

    def test_provider_without_email_is_refused(self):
        profile = google_profile(email=self.email)
        profile.pop("email")
        _response, params = self.login(profile=profile)
        self.assertEqual(params["oauth_error"][0], "email_unverified")
        self.assertIsNone(self.db.fetch_principal_by_email(self.email))

    def test_upstream_failure_maps_to_upstream_error(self):
        state = self.start_state()
        self.fake_idp({"/token": ({"error": "invalid_grant"}, 400)})
        response = self.callback(code="c", state=state)
        self.assertEqual(self.error_code(response), "upstream_unavailable")

    def test_social_and_enterprise_oidc_identities_do_not_share_a_namespace(self):
        """同一 subject 在 per-org SSO（provider_type=oidc）与社交登录之间不得互相命中。"""
        from access_control import seed_principal

        bare = seed_principal(self.db, email=f"ent-{self.suffix}@analytical.test", display_name="Ent")
        self.db.upsert_auth_identity({
            "auth_identity_id": f"ai_{uuid.uuid4().hex[:12]}",
            "principal_id": bare["principal_id"],
            "provider_type": "oidc",
            "provider_key": "google",
            "subject": "g-100",
            "email": bare["email"],
            "email_verified": 1,
            "created_at": "2026-09-06T00:00:00Z",
            "updated_at": "2026-09-06T00:00:00Z",
        })
        _response, params = self.login()
        actor = authenticate_access_token(self.db, params["oauth_access_token"][0])
        self.assertNotEqual(actor["principal"]["principal_id"], bare["principal_id"])

    def test_email_verified_is_not_marked_when_principal_email_differs(self):
        """换过邮箱的老账户：社交登录成功，但不能把「提供方的已验证」记到别的邮箱上。

        刻意不给 ``_mark_email_verified_from_provider`` 打桩：打桩后断言「验证位没落下」
        什么也没证明（函数压根没跑）。这里让真实代码跑完再看 DB，并同时断言登录确实
        落在了同一个 principal 上 —— 否则「没落下」可能只是因为登进了别人账户。
        正向对照见 ``test_new_user_gets_own_org_workspace_and_working_token``。
        """
        from access_control import link_auth_identity
        from services import onboarding

        provisioned = onboarding.provision_account(
            self.db, email=self.email, display_name="Moved", password="Maple-Drum-77!grid")
        link_auth_identity(self.db, principal_id=provisioned["principal"]["principal_id"],
                           provider_key="google", subject="g-100", email=self.email,
                           email_verified=True, provider_type="social")
        # 用户改了邮箱；提供方这次回的又是第三个地址 → 三者互不相等
        self.db.upsert_principal({**provisioned["principal"],
                                  "email": f"moved-{self.suffix}@analytical.test"})
        provider_email = f"provider-{self.suffix}@analytical.test"
        _response, params = self.login(profile=google_profile(email=provider_email))
        actor = authenticate_access_token(self.db, params["oauth_access_token"][0])
        self.assertEqual(actor["principal"]["principal_id"],
                         provisioned["principal"]["principal_id"], "subject 命中优先于邮箱匹配")
        self.assertIsNone(self.db.fetch_principal(actor["principal"]["principal_id"]).get("email_verified_at"))

    def test_existing_principal_without_workspace_is_not_promoted(self):
        from access_control import seed_principal

        bare = seed_principal(self.db, email=self.email, display_name="No WS")
        _response, params = self.login()
        self.assertEqual(params["oauth_error"][0], "no_workspace")
        self.assertEqual(
            self.db.list_workspace_memberships_by_principal(bare["principal_id"]), [],
            "无 workspace 的历史账户不应被社交登录自动升级为 org_owner")

    def test_github_uses_primary_verified_email_from_emails_endpoint(self):
        self.configure_github()
        gh_email = f"gh-{self.suffix}@analytical.test"
        state = self.start_state("github")
        self.fake_idp({
            "/login/oauth/access_token": {"access_token": "at", "token_type": "bearer"},
            "/user/emails": github_emails(
                {"email": f"old-{self.suffix}@analytical.test", "primary": False, "verified": True},
                {"email": gh_email, "primary": True, "verified": True},
            ),
            "api.github.com/user": github_profile(email=None),
        })
        response = self.callback("github", code="c", state=state)
        params = self.fragment_params(response)
        self.assertIn("oauth_access_token", params, response.text)
        actor = authenticate_access_token(self.db, params["oauth_access_token"][0])
        self.assertEqual(actor["principal"]["email"], gh_email)

    def test_github_without_primary_verified_email_is_refused(self):
        self.configure_github()
        state = self.start_state("github")
        self.fake_idp({
            "/login/oauth/access_token": {"access_token": "at"},
            "/user/emails": github_emails(
                {"email": f"x-{self.suffix}@analytical.test", "primary": True, "verified": False}),
            "api.github.com/user": github_profile(),
        })
        response = self.callback("github", code="c", state=state)
        self.assertEqual(self.error_code(response), "email_unverified")

    def test_github_token_response_in_form_encoding_is_parsed(self):
        """GitHub 的历史包袱：不带 accept 时回 x-www-form-urlencoded。"""
        self.configure_github()
        state = self.start_state("github")
        transport = FakeTransport({})
        transport.routes = {}

        def _post(url, **kwargs):
            transport.calls.append(("POST", url))
            response = FakeResponse(None, 200)
            response.text = "access_token=at&token_type=oauth&scope=read%3Auser"
            response.json = lambda: (_ for _ in ()).throw(ValueError("not json"))
            return response

        def _get(url, **kwargs):
            transport.calls.append(("GET", url))
            if "/user/emails" in url:
                return FakeResponse([{"email": f"form-{self.suffix}@analytical.test",
                                      "primary": True, "verified": True}])
            return FakeResponse(github_profile(email=None))

        transport.post = _post
        transport.get = _get
        with mock.patch("oauth_providers.httpx", transport):
            response = self.callback("github", code="c", state=state)
        self.assertIn("oauth_access_token", self.fragment_params(response), response.text)


class DiscoveryTests(OAuthSocialRouteTests):
    def setUp(self):
        super().setUp()
        self.configure_google()

    def test_discovery_failure_falls_back_to_pinned_endpoints(self):
        from oauth_providers import OAuthConfigError  # noqa: F811

        with mock.patch("oauth_providers._fetch_discovery", return_value={}):
            query = parse_qs(urlparse(self.start_state_url()).query)
        self.assertTrue(query["state"])
        location = urlparse(self.start_state_url()).netloc
        self.assertIn(location, {"accounts.google.com"})

    def test_discovery_endpoint_outside_allowlist_is_rejected(self):
        """发现文档可以把端点指到任意主机 —— 白名单是唯一拦住它的东西。"""
        hostile = {
            "authorization_endpoint": "https://evil.test/authorize",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
            "code_challenge_methods_supported": ["S256"],
        }
        with mock.patch("oauth_providers._fetch_discovery", return_value=hostile):
            response = self.start()
        # 该提供方整体不可用（501），而不是「悄悄把用户送去 evil.test」
        self.assertEqual(response.status_code, 501)

    def test_https_required_for_public_base_url(self):
        patcher = mock.patch.dict(os.environ, {"AUS_ELE_PUBLIC_BASE_URL": "http://app.test"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(self.start().status_code, 501)

    def test_landing_path_override_rejects_protocol_relative(self):
        patcher = mock.patch.dict(os.environ, {"AUS_ELE_OAUTH_LANDING_PATH": "//evil.test/x"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(oauth_routes._landing_path(), "/login")


if __name__ == "__main__":
    unittest.main()
