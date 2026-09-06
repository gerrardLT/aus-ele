"""社交登录提供方（Google / GitHub）的协议实现（R1.2，2026-09-06）。

职责边界：本模块只做 **协议**（授权 URL、code 换 token、取身份三元组），不碰会话签发、
不碰 org/ws 建档、不碰限流 —— 那些在 ``routes/oauth_routes.py`` 与 ``access_control``。

与既有 ``oidc_client.py`` / ``oidc_provider`` 表的关系（刻意不复用，理由要留痕）：
``oidc_provider`` 是 **per-org 企业 SSO** 语义（``fetch_oidc_provider_by_key`` 要求
org_id，登录者加入的是那个 org），而社交登录的语义是 **个人账户自助开通**（首登即自建
org）。把两者塞进同一张表会让「企业 SSO 域名策略（P0.3 的 verified 域名门槛）」与
「个人 gmail.com 登录」在同一条代码路径上互相打架 —— 那正是 P0.3 要堵的那类缺陷。

三个关键取舍：

1. **不校验 ID token 签名，改用 userinfo 端点。** Google 的 code 流程里 ID token 只有
   两个合法去处：浏览器（前端自己验 → 就是被 P0.5 关掉的旧端点那种自证式伪造）或后端
   （需要引 JWKS 验签依赖）。本模块走后端 code exchange + 服务端发起的 TLS 请求拿
   userinfo，信任根是「我们与白名单主机之间的 TLS」，不是「别人递给我们的一个 JWT」。
   零新依赖（``httpx`` 已在 requirements.txt:25），且攻击面比验签方案更小：签名密钥轮换、
   alg 混淆、aud/iss 漏判这三类实现型漏洞在这里结构上不存在。
2. **端点白名单是硬约束，发现文档只是加速器。** 发现文档可以配错、可以被
   ``AUS_ELE_OAUTH_*_DISCOVERY_URL`` 指到别处，但拿到的每个端点都必须过 HTTPS + 主机
   白名单（``_ENDPOINT_HOST_ALLOWLIST``），否则整份文档丢弃、回落到内置常量。没有这道
   闸门，「配一个 discovery URL」等于「把 code 和 access token 送到任意主机」。
3. **``redirect_uri`` 一律服务端构造，绝不接受调用方传入。** OAuth 的 redirect_uri 是
   唯一的「code 送到哪」的凭据；接受 query 参数就等于把授权码转发给攻击者，state 校验
   做得再对也白做。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlparse

import httpx

from env_flags import env_float, env_int

logger = logging.getLogger(__name__)

DISCOVERY_CACHE_SCOPE = "oauth_discovery"
DISCOVERY_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_HTTP_TIMEOUT_SECONDS = 8.0


def http_timeout_seconds() -> float:
    """对外 HTTP 超时。调用时读（与 state_ttl_seconds 同一纪律），下界 1s：
    写成 0 或负数的配置若被照用，等于给每个社交登录请求一个「立即失败」的默认值。"""
    return env_float("AUS_ELE_OAUTH_HTTP_TIMEOUT_SECONDS", DEFAULT_HTTP_TIMEOUT_SECONDS, floor=1.0)


# state/nonce 的存活时间。10 分钟是「用户被 IdP 的登录页挡住 + 手机确认」的合理上界；
# 再长就把「一次点击生成的授权请求」变成了可被复用的长期凭据。刻意在调用时读 env
# （P0.6/P0.7 学到的同一课）：import 时读一次的配置，测试无法在 patch.dict 后生效。
DEFAULT_STATE_TTL_SECONDS = 600


def state_ttl_seconds() -> int:
    return env_int("AUS_ELE_OAUTH_STATE_TTL_SECONDS", DEFAULT_STATE_TTL_SECONDS, floor=60)


PROVIDER_KEYS = ("google", "github")


class OAuthConfigError(RuntimeError):
    """配置不可用（缺凭据、发现文档指向白名单外主机）。→ 501/500，绝不静默放行。"""


class OAuthUpstreamError(RuntimeError):
    """上游 IdP 报错或返回无法解析的载荷。→ 502，与「凭据无效」区分开，避免把上游
    抖动伪装成用户凭据问题（那会让运维去查一个根本不存在的账号问题）。"""


class OAuthRejected(RuntimeError):
    """提供方返回的身份不可接受（无已验证邮箱）。→ 403，面向用户的明确提示。"""


@dataclass(frozen=True)
class OAuthProvider:
    key: str
    label: str
    client_id: str
    client_secret: str = field(repr=False)
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    email_endpoint: str | None
    scopes: tuple[str, ...]
    supports_pkce: bool
    extra_authorize_params: dict[str, str] = field(default_factory=dict)

    def public_view(self) -> dict:
        """给前端的东西：只有按钮需要的字段。secret 与端点绝不出现在这里。"""
        return {"key": self.key, "label": self.label, "scopes": list(self.scopes)}


# 内置常量：Google/GitHub 的端点十年不变，写死的价值在于「发现文档拉不到时仍能工作」。
_BUILTIN = {
    "google": {
        "label": "Google",
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        "email_endpoint": None,
        "scopes": ("openid", "email", "profile"),
        "supports_pkce": True,
        # prompt=select_account：同一 Google 账号有多个时，不弹选择框会让用户被迫先登出
        # 系统里的 Google 账号才能换号，这是社交登录最常见的「登错人」投诉来源。
        "extra_authorize_params": {"prompt": "select_account"},
    },
    "github": {
        "label": "GitHub",
        "authorization_endpoint": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "userinfo_endpoint": "https://api.github.com/user",
        # GitHub 没有 OIDC 发现文档：/user 的 email 字段可能为 null（用户在
        # «Email settings» 里选了私有邮箱），必须再取 /user/emails 拿主邮箱。
        "discovery_url": None,
        "email_endpoint": "https://api.github.com/user/emails",
        "scopes": ("read:user", "user:email"),
        "supports_pkce": False,  # GitHub 的 OAuth App 不支持 PKCE（2026-09 现状）
        "extra_authorize_params": {},
    },
}

# 发现文档 / env 覆盖允许落到哪些主机。新增提供方或换自建代理时必须显式加白名单，
# 这个名单是唯一一处「谁能拿到我们的 code 与 access token」的定义。
_ENDPOINT_HOST_ALLOWLIST = {
    "accounts.google.com",
    "oauth2.googleapis.com",
    "openidconnect.googleapis.com",
    "www.googleapis.com",
    "token.oauth2.googleapis.com",
    "github.com",
    "api.github.com",
}


def _allow_any_host() -> bool:
    from env_flags import env_flag

    # 默认 false：给自建代理开这个口子要用 env 显式表态，而不是让代码猜。
    return env_flag("AUS_ELE_OAUTH_ALLOW_ANY_HOST", False)


def _host_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return _allow_any_host() or host in _ENDPOINT_HOST_ALLOWLIST


def _assert_endpoint_url(provider_key: str, name: str, url: str) -> str:
    url = (url or "").strip()
    if not url or not _host_allowed(url):
        raise OAuthConfigError(
            f"{provider_key}: endpoint {name!r} rejected (must be https and an allow-listed host): {url!r}"
        )
    return url


def _assert_base_url(name: str, raw: str) -> str:
    """校验「我们自己的对外根地址」。

    这里**不能**复用 ``_host_allowed``：那份白名单管的是「我们的 code 与 access token
    能发给哪些 IdP 主机」，而根地址是我们自己的站点域名 —— 拿它去比对 Google 的白名单，
    结果是所有正常的自建域名（``https://app.example.com``）一律被拒，运维只能去开
    ``AUS_ELE_OAUTH_ALLOW_ANY_HOST``，而那同时把端点白名单也关了 —— 一个配置项被迫
    承担两个方向相反的决定。

    本站真正需要拦的是：非 https（IdP 也不会允许 http 回调）、缺主机、URL 里塞了
    userinfo/query/fragment（会被拼进 redirect_uri）。本机开发单独放行 localhost。
    """
    raw = (raw or "").strip().rstrip("/")
    if not raw:
        raise OAuthConfigError(f"{name} is required for social login callbacks")
    try:
        parsed = urlparse(raw)
    except ValueError as exc:  # pragma: no cover - urlparse 仅在非法端口等场景抛
        raise OAuthConfigError(f"{name} is not a parseable URL: {raw!r}") from exc
    host = (parsed.hostname or "").lower()
    scheme_ok = parsed.scheme == "https" or (
        parsed.scheme == "http" and raw.startswith(("http://localhost", "http://127.0.0.1")))
    if scheme_ok and host and not parsed.username and not parsed.password \
            and not parsed.query and not parsed.fragment:
        return raw
    raise OAuthConfigError(
        f"{name} must be an https URL (http only for localhost), without credentials "
        f"or query/fragment: {raw!r}")


def public_base_url() -> str:
    """构造 redirect_uri 与落地页用的对外根地址。

    缺失时**不回落 localhost**：社交登录的 redirect_uri 必须与 IdP 控制台登记的完全
    一致，静默用错根地址会表现为「IdP 报 redirect_uri_mismatch」这种离根因很远的错。
    """
    return _assert_base_url("AUS_ELE_PUBLIC_BASE_URL", os.environ.get("AUS_ELE_PUBLIC_BASE_URL") or "")


def redirect_uri_for(provider_key: str) -> str:
    """服务端构造回调地址（见模块 docstring 第 3 条）。"""
    override = (os.environ.get("AUS_ELE_OAUTH_REDIRECT_BASE_URL") or "").strip()
    base = _assert_base_url("AUS_ELE_OAUTH_REDIRECT_BASE_URL", override) if override else public_base_url()
    return f"{base}/api/v1/auth/oauth/{provider_key}/callback"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _endpoints(provider_key: str, *, refresh: bool = False) -> dict:
    """合并「内置常量 ← 发现文档 ← env 覆盖」。

    优先级说明：env 覆盖最高（应急换端点不必等发现文档，也不该被远端文档反向改掉），
    发现文档次之，内置常量兜底。三层都要过同一道主机白名单 —— 白名单是函数内最后
    一步，不是某一层的特点。
    """
    builtin = dict(_BUILTIN[provider_key])
    selected = {
        "authorization_endpoint": builtin["authorization_endpoint"],
        "token_endpoint": builtin["token_endpoint"],
        "userinfo_endpoint": builtin["userinfo_endpoint"],
        "email_endpoint": builtin.get("email_endpoint"),
        "supports_pkce": bool(builtin["supports_pkce"]),
    }

    discovery_url = _env(f"AUS_ELE_OAUTH_{provider_key.upper()}_DISCOVERY_URL") or builtin.get("discovery_url")
    document: dict = {}
    if discovery_url:
        document = _fetch_discovery(provider_key, str(discovery_url), refresh=refresh)

    mapping = {
        "authorization_endpoint": "authorization_endpoint",
        "token_endpoint": "token_endpoint",
        "userinfo_endpoint": "userinfo_endpoint",
    }
    for field_name, doc_key in mapping.items():
        value = _env(f"AUS_ELE_OAUTH_{provider_key.upper()}_{field_name.upper()}") or document.get(doc_key)
        if value:
            selected[field_name] = str(value)

    methods = document.get("code_challenge_methods_supported") or []
    if isinstance(methods, list) and "S256" in methods:
        selected["supports_pkce"] = True
    return selected


def _fetch_discovery(provider_key: str, url: str, *, refresh: bool = False) -> dict:
    """拉取并缓存 OIDC 发现文档。失败返回 ``{}``（调用方回落到内置常量）。"""
    from shared_state import get_state_store

    if not _host_allowed(url) and not _allow_any_host():
        raise OAuthConfigError(f"{provider_key}: discovery URL outside the host allow-list: {url!r}")
    store = get_state_store()
    cache_key = provider_key
    if not refresh:
        cached = store.recall(DISCOVERY_CACHE_SCOPE, cache_key)
        if isinstance(cached, dict) and cached:
            return cached
    try:
        response = httpx.get(url, timeout=http_timeout_seconds(), headers={"accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 — 发现文档是可选加速器，不得因此拒绝登录
        logger.warning("oauth discovery fetch failed for %s: %s", provider_key, exc)
        return {}
    if not isinstance(payload, dict):
        logger.warning("oauth discovery payload for %s is not an object", provider_key)
        return {}
    store.remember(DISCOVERY_CACHE_SCOPE, cache_key, payload, DISCOVERY_CACHE_TTL_SECONDS)
    return payload


def provider_config(provider_key: str) -> OAuthProvider | None:
    """按 env 组装提供方配置；凭据缺失返回 ``None``（未配置 = 不提供该入口）。"""
    key = (provider_key or "").strip().lower()
    if key not in _BUILTIN:
        return None
    upper = key.upper()
    client_id = _env(f"AUS_ELE_OAUTH_{upper}_CLIENT_ID")
    client_secret = _env(f"AUS_ELE_OAUTH_{upper}_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    endpoints = _endpoints(key)
    # 根地址与端点同属「这个提供方能不能走通」：redirect_uri 拼不出来，授权请求发出去
    # 也只会被 IdP 以 redirect_uri_mismatch 打回。在此判定而不是等 build_authorization_url
    # 抛，是为了让 /providers 不广告一个点下去必然 500 的按钮，让错误统一走 501。
    redirect_uri_for(key)
    return OAuthProvider(
        key=key,
        label=_BUILTIN[key]["label"],
        client_id=client_id,
        client_secret=client_secret,
        authorization_endpoint=_assert_endpoint_url(key, "authorization_endpoint", endpoints["authorization_endpoint"]),
        token_endpoint=_assert_endpoint_url(key, "token_endpoint", endpoints["token_endpoint"]),
        userinfo_endpoint=_assert_endpoint_url(key, "userinfo_endpoint", endpoints["userinfo_endpoint"]),
        email_endpoint=(
            _assert_endpoint_url(key, "email_endpoint", endpoints["email_endpoint"])
            if endpoints.get("email_endpoint")
            else None
        ),
        scopes=_BUILTIN[key]["scopes"],
        supports_pkce=bool(endpoints["supports_pkce"]),
        extra_authorize_params=dict(_BUILTIN[key]["extra_authorize_params"]),
    )


def configured_providers() -> list[OAuthProvider]:
    """已配置的提供方列表。未配置的直接不出现（前端据此隐藏按钮）。

    单个提供方配错（例如发现文档指到白名单外）只跳过它自己并记日志 —— 不能让
    GitHub 的配错把 Google 也带走。
    """
    ready: list[OAuthProvider] = []
    for key in PROVIDER_KEYS:
        try:
            provider = provider_config(key)
        except OAuthConfigError as exc:
            logger.error("oauth provider %s misconfigured: %s", key, exc)
            continue
        if provider is not None:
            ready.append(provider)
    return ready


def new_state() -> str:
    """CSRF 防线：32 字节随机值，服务端留存期望值，回调比对后才继续。"""
    return secrets.token_urlsafe(32)


def new_nonce() -> str:
    return secrets.token_urlsafe(32)


def new_pkce_verifier() -> str:
    # RFC 7636 要求 verifier 长度 43-128 字符且字符集受限；token_urlsafe(48) → 64 字符。
    return secrets.token_urlsafe(48)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorization_url(provider: OAuthProvider, *, state: str, nonce: str, code_challenge: str | None) -> str:
    params = {
        "client_id": provider.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri_for(provider.key),
        "scope": " ".join(provider.scopes),
        "state": state,
    }
    # nonce 对 userinfo 方案没有密码学意义（不发 ID token），但对 Google 的
    # form_post 变体与未来切到 ID token 校验时是必需字段，且它同时充当
    # 「同一个 state 只能被一个浏览器上下文消费」的辅助判据，因此仍然发送。
    if nonce:
        params["nonce"] = nonce
    if provider.supports_pkce and code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    params.update(provider.extra_authorize_params)
    return f"{provider.authorization_endpoint}?{urlencode(params)}"


@dataclass(frozen=True)
class SocialIdentity:
    subject: str
    email: str
    email_verified: bool
    display_name: str
    provider_key: str

    @property
    def provider_label(self) -> str:
        return _BUILTIN[self.provider_key]["label"]


def exchange_code(provider: OAuthProvider, *, code: str, code_verifier: str | None = None) -> str:
    """用授权码换 access token，返回 token 字符串。"""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri_for(provider.key),
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
    }
    if provider.supports_pkce and code_verifier:
        payload["code_verifier"] = code_verifier
    headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
    try:
        response = httpx.post(
            provider.token_endpoint,
            data=urlencode(payload),
            headers=headers,
            timeout=http_timeout_seconds(),
        )
        response.raise_for_status()
        data = _decode_form_or_json(response)
    except httpx.HTTPStatusError as exc:
        # 只记状态码与上游 error 字段：响应体里可能含 token，日志是长期留存的外泄通道。
        logger.warning("oauth token exchange failed: provider=%s status=%s body=%s",
                       provider.key, exc.response.status_code, str(exc.response.text)[:200])
        raise OAuthUpstreamError(f"{provider.key} rejected the authorization code") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("oauth token exchange error: provider=%s err=%s", provider.key, exc)
        raise OAuthUpstreamError(f"{provider.key} token endpoint unavailable") from exc

    token = data.get("access_token")
    if not token:
        logger.warning("oauth token response without access_token: provider=%s error=%r",
                       provider.key, data.get("error"))
        raise OAuthUpstreamError(f"{provider.key} returned no access token")
    return str(token)


def _decode_form_or_json(response: httpx.Response) -> dict:
    """GitHub 的历史包袱：不带 accept 时回 ``x-www-form-urlencoded``。"""
    try:
        payload = response.json()
    except ValueError:
        payload = dict(
            pair.split("=", 1) for pair in (response.text or "").split("&") if "=" in pair
        )
    return payload if isinstance(payload, dict) else {}


def fetch_identity(provider: OAuthProvider, access_token: str) -> SocialIdentity:
    """取外部身份三元组。邮箱缺失/未验证一律拒绝（见 ``_require_verified_email``）。"""
    headers = {"accept": "application/json", "authorization": f"Bearer {access_token}"}
    try:
        response = httpx.get(provider.userinfo_endpoint, headers=headers, timeout=http_timeout_seconds())
        response.raise_for_status()
        profile = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("oauth userinfo failed: provider=%s status=%s", provider.key, exc.response.status_code)
        raise OAuthUpstreamError(f"{provider.key} userinfo endpoint rejected the token") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("oauth userinfo error: provider=%s err=%s", provider.key, exc)
        raise OAuthUpstreamError(f"{provider.key} userinfo endpoint unavailable") from exc
    if not isinstance(profile, dict):
        raise OAuthUpstreamError(f"{provider.key} returned an unexpected userinfo payload")

    subject = profile.get("sub") or profile.get("id")
    if subject is None or str(subject).strip() == "":
        raise OAuthUpstreamError(f"{provider.key} userinfo returned no subject identifier")

    email = (profile.get("email") or "").strip().lower()
    email_verified = bool(profile.get("email_verified"))
    if provider.key == "github":
        email, email_verified = _github_primary_email(provider, headers=headers)
    email = email.strip().lower()
    if not email or not email_verified:
        # 拒的不是「没拿到邮箱」而是「拿不到提供方担保已验证的邮箱」：否则任何人都能
        # 在 IdP 上填一个别人的邮箱，把这条路径变成账户接管入口。
        raise OAuthRejected(f"{provider.label} did not return a verified email address")

    display_name = (profile.get("name") or profile.get("login") or email.split("@", 1)[0]).strip()
    return SocialIdentity(
        subject=str(subject).strip(),
        email=email,
        email_verified=True,
        display_name=display_name or email,
        provider_key=provider.key,
    )


def _github_primary_email(provider: OAuthProvider, *, headers: dict) -> tuple[str, bool]:
    """GitHub：主邮箱且已验证才算数。

    ``/user`` 的 ``email`` 字段在开启「邮箱私有」后为 null，或是一个未验证的历史邮箱；
    只有 ``/user/emails`` 里 ``primary and verified`` 那一条才是 GitHub 担保的归属地址。
    """
    endpoint = provider.email_endpoint
    if not endpoint:
        return "", False
    try:
        response = httpx.get(endpoint, headers=headers, timeout=http_timeout_seconds())
        response.raise_for_status()
        rows = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("oauth github email list failed: %s", exc)
        raise OAuthUpstreamError("GitHub email endpoint unavailable") from exc
    if not isinstance(rows, list):
        raise OAuthUpstreamError("GitHub returned an unexpected email list")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("primary") and row.get("verified"):
            return str(row.get("email") or ""), True
    # 没有任何「主 + 已验证」邮箱：GitHub 账号没有可用邮箱时确实会发生，
    # 这时用户需要先去 IdP 补邮箱，而不是在我们这里换一个能登进来的邮箱。
    return "", False


__all__ = [
    "OAuthConfigError",
    "OAuthProvider",
    "OAuthRejected",
    "OAuthUpstreamError",
    "PROVIDER_KEYS",
    "SocialIdentity",
    "build_authorization_url",
    "configured_providers",
    "exchange_code",
    "fetch_identity",
    "new_nonce",
    "new_pkce_verifier",
    "new_state",
    "pkce_challenge",
    "provider_config",
    "redirect_uri_for",
    "state_ttl_seconds",
]
