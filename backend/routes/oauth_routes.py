"""Google / GitHub 社交登录端点（R1.2，2026-09-06）。

- GET /api/v1/auth/oauth/providers              已配置的提供方（前端据此决定按钮显隐）
- GET /api/v1/auth/oauth/{provider}/start       302 到 IdP（无 JS 也能跑通）
- GET /api/v1/auth/oauth/{provider}/callback    code 换 token → userinfo → 建/认账户 → 落地

三条设计判定（协议细节见 ``oauth_providers`` 的 docstring）：

1. **state 存服务端，一次性消费。** 旧端点（``/api/auth/oidc/callback``，已在 P0.5 默认
   关闭）之所以是漏洞，正是因为 state 的两侧都由客户端提供 —— 自证式校验等于没有校验。
   这里 state 由服务端生成并存放，回调必须先在服务端存储里命中才算数；``consume`` 用
   原子读删（见 ``shared_state.SharedStateStore.consume``），否则并发第二次回调能重放。
2. **社交登录绝不自动加入任何组织。** 组织入组一律要求「已验证域名 + 邀请/域名策略」
   （P0.3）。如果 gmail.com 上的 Google 登录能命中某个把 ``gmail.com`` 登记为组织域名的
   组织，那就等于绕开了 P0.3 的全部工作 —— 公共邮箱域名本来也在黑名单里，但依赖黑名单
   不如在入口就不做这件事。
3. **未验证邮箱的 IdP 身份一律拒绝落地。** 见 ``oauth_providers.fetch_identity``：提供方
   不担保邮箱归属时，自动按邮箱匹配已有账户就是账户接管通道。

紧急回滚（C 类，零代码）：``AUS_ELE_ENABLE_SOCIAL_LOGIN=false`` 重启 → /start 与
/providers 一律 404/空列表，前端按钮自动消失；已用社交登录建出来的账户仍可用密码登录
（若其设过密码），不会因为关开关而失联。

多 worker 部署前提：state 必须落在 Redis 上。进程内回落在「/start 打在 worker A、
IdP 回调打在 worker B」的组合下必然找不到 state → 表现为随机 401。这是**失败关闭**
（拒绝登录）而不是放行，因此可接受；但生产 compose 必须配 ``REDIS_URL``（P0.7 已配好）。
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from env_flags import env_flag, env_int
from routes.auth_routes import _client_ip
from shared_state import get_state_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["oauth"])

_STATE_SCOPE = "oauth_state"
_START_IP_SCOPE = "oauth_start_rl"
_CALLBACK_IP_SCOPE = "oauth_callback_rl"
_START_LIMIT_DEFAULT = 30
_CALLBACK_LIMIT_DEFAULT = 60
_LANDING_PATH_DEFAULT = "/login"

# provider_type 与企业的 per-org SSO 分开，理由见 access_control.link_auth_identity
SOCIAL_PROVIDER_TYPE = "social"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _social_login_enabled() -> bool:
    return env_flag("AUS_ELE_ENABLE_SOCIAL_LOGIN", True)


def _rate_limit(*, scope: str, key: str, limit: int, detail: str) -> None:
    allowed, retry_after = get_state_store().register_attempt(
        scope, key, limit=limit, window_seconds=600
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


def _state_key(state: str) -> str:
    """以 state 的摘要做键：与 R1.1 验证 token 只存摘要同一纪律。

    state 本身是随机凭据，键里带上它等于把凭据写进任何按 keys() 列举的运维视图、
    以及 Redis 的 MONITOR/慢日志。摘要不影响一次性判定（命中仍需完全相等）。
    """
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _landing_path() -> str:
    """回调落地页路径（前端 ``LoginPage`` 读 URL fragment 完成 token 落地）。

    只接受单一相对路径：拒绝 ``//host``（协议相对 → 等于开放重定向）、拒绝带
    scheme 的值、拒绝换行（响应头注入）。配错时回落默认值并 warning —— 这条链路的
    失败模式必须是「回到登录页」，不能是 500。
    """
    raw = (os.environ.get("AUS_ELE_OAUTH_LANDING_PATH") or _LANDING_PATH_DEFAULT).strip()
    if (
        not raw.startswith("/")
        or raw.startswith("//")
        or "\\" in raw
        or any(char in raw for char in ("\r", "\n"))
        or urlparse(raw).netloc
    ):
        logger.warning("AUS_ELE_OAUTH_LANDING_PATH=%r rejected, using %s", raw, _LANDING_PATH_DEFAULT)
        return _LANDING_PATH_DEFAULT
    return raw[:200]


def _sanitize_return_to(raw: str | None) -> str:
    """``?next=`` 只允许站内相对路径，规则与 ``_landing_path`` 同源。"""
    value = (raw or "").strip()
    if not value:
        return ""
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(char in value for char in ("\r", "\n"))
        or urlparse(value).netloc
    ):
        return ""
    return value[:200]


def _landing_url(fragment: str) -> str:
    """落地地址：优先绝对 URL（base env），缺失时退回相对路径。

    成功与失败两条路径共用同一个构造点，避免出现「失败用了一套根地址、成功用了另一套」。
    """
    from oauth_providers import OAuthConfigError, public_base_url

    try:
        return f"{public_base_url()}{_landing_path()}#{fragment}"
    except OAuthConfigError:
        logger.warning("oauth landing URL fell back to relative Location (no PUBLIC_BASE_URL)")
        return f"{_landing_path()}#{fragment}"


def _error_redirect(*, provider_key: str, code: str) -> RedirectResponse:
    """失败也要回到登录页（带 fragment 错误码），而不是把裸 JSON 甩给用户。"""
    fragment = urlencode({"oauth_error": code, "oauth_provider": provider_key})
    return RedirectResponse(_landing_url(fragment), status_code=302)


def _require_provider(provider_key: str):
    """返回 provider 配置；未配置 = 404（前端隐藏按钮的同一个判据）。"""
    from oauth_providers import OAuthConfigError, provider_config

    if not _social_login_enabled():
        raise HTTPException(status_code=404, detail="Social login is disabled")
    try:
        provider = provider_config(provider_key)
    except OAuthConfigError as exc:
        # 配置错误不能降级成 404（那会让人以为「没开这个入口」），也不能 500 泄漏细节
        logger.error("oauth provider %s config error: %s", provider_key, exc)
        raise HTTPException(status_code=501, detail="Social login provider is misconfigured") from exc
    if provider is None:
        raise HTTPException(status_code=404, detail="Social login provider not configured")
    return provider


@router.get("/providers")
def list_providers() -> dict:
    """已配置且可用的社交登录入口。前端据此渲染按钮，未配置时按钮不出现。

    刻意不返回 client_id：它是公开值（出现在授权 URL 里），但把它放进一个 JSON 列表
    等于多一处需要审查的敏感字段，而前端并不需要它。
    """
    if not _social_login_enabled():
        return {"providers": []}
    from oauth_providers import configured_providers

    return {"providers": [provider.public_view() for provider in configured_providers()]}


@router.get("/{provider_key}/start")
def start_login(provider_key: str, request: Request = None, next: str = None):  # noqa: A002
    """发起授权：存 state → 302 到 IdP。

    用 GET + 302 而不是「POST 返回 authorization_url」：前端只需要一个
    ``<a href>`，无 JS 也能完成登录，且授权请求的发起者是浏览器本身（这正是 state
    要防的 CSRF 场景里唯一可信的发起方）。
    """
    from oauth_providers import (
        build_authorization_url,
        new_nonce,
        new_pkce_verifier,
        new_state,
        pkce_challenge,
        state_ttl_seconds,
    )

    # 限流在解析 provider 配置**之前**：``_require_provider`` 对 Google 会去拉发现文档，
    # 让未限流的请求触发对外 HTTP 是把 CSRF 防线换成了 SSRF 放大器。
    ip = _client_ip(request) if request is not None else "unknown"
    _rate_limit(
        scope=_START_IP_SCOPE, key=ip,
        limit=env_int("AUS_ELE_OAUTH_START_RATE_LIMIT", _START_LIMIT_DEFAULT, floor=1),
        detail="Too many social login attempts. Please try again later.",
    )
    provider = _require_provider(provider_key)

    state = new_state()
    nonce = new_nonce()
    verifier = new_pkce_verifier() if provider.supports_pkce else ""
    ttl = state_ttl_seconds()
    get_state_store().remember(
        _STATE_SCOPE,
        _state_key(state),
        {
            "provider": provider.key,
            "nonce": nonce,
            "verifier": verifier,
            "return_to": _sanitize_return_to(next),
            "requested_at": _now_iso(),
        },
        ttl,
    )
    url = build_authorization_url(
        provider, state=state, nonce=nonce,
        code_challenge=pkce_challenge(verifier) if verifier else None,
    )
    return RedirectResponse(url, status_code=302)


@router.get("/{provider_key}/callback")
def complete_login(
    provider_key: str,
    request: Request = None,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """回调：一次性消费 state → code 换 token → 取身份 → 建/认账户 → 签发会话。"""
    from oauth_providers import (
        OAuthConfigError,
        OAuthRejected,
        OAuthUpstreamError,
        exchange_code,
        fetch_identity,
    )

    ip = _client_ip(request) if request is not None else "unknown"
    _rate_limit(
        scope=_CALLBACK_IP_SCOPE, key=ip,
        limit=env_int("AUS_ELE_OAUTH_CALLBACK_RATE_LIMIT", _CALLBACK_LIMIT_DEFAULT, floor=1),
        detail="Too many social login callbacks. Please try again later.",
    )
    provider = _require_provider(provider_key)

    if error:
        # IdP 自己报错（用户拒绝授权 / 上游故障）。两家在拒绝时都会把 state 原样带回，
        # 所以这里也消费它：一次授权请求到此为止，留在存储里到 TTL 到期只会多一个可窗口。
        if state:
            get_state_store().consume(_STATE_SCOPE, _state_key(state))
        logger.info("oauth callback provider %s returned error=%r ip=%s", provider_key, error, ip)
        return _error_redirect(provider_key=provider_key, code="provider_denied")

    if not code or not state:
        return _error_redirect(provider_key=provider_key, code="state_invalid")

    stored = get_state_store().consume(_STATE_SCOPE, _state_key(state))
    if not isinstance(stored, dict) or stored.get("provider") != provider.key:
        # 缺失 / 过期 / 换了 provider 都同一句话：不给「state 存在但不属于这里」这种探测口
        logger.warning("oauth callback state rejected: provider=%s ip=%s", provider_key, ip)
        return _error_redirect(provider_key=provider_key, code="state_invalid")

    try:
        access_token = exchange_code(provider, code=code, code_verifier=stored.get("verifier") or None)
        identity = fetch_identity(provider, access_token)
    except OAuthRejected as exc:
        logger.warning("oauth callback identity rejected: provider=%s ip=%s", provider_key, ip)
        return _error_redirect(provider_key=provider_key, code="email_unverified")
    except OAuthUpstreamError as exc:
        logger.warning("oauth callback upstream failure: provider=%s ip=%s err=%s", provider_key, ip, exc)
        return _error_redirect(provider_key=provider_key, code="upstream_unavailable")
    except OAuthConfigError as exc:
        logger.error("oauth callback config failure: provider=%s err=%s", provider_key, exc)
        return _error_redirect(provider_key=provider_key, code="provider_misconfigured")

    db = _get_db()
    resolved = _resolve_social_principal(db, provider=provider, identity=identity)
    if isinstance(resolved, RedirectResponse):
        return resolved

    session, access = _issue_social_session(
        db,
        principal=resolved["principal"],
        auth_identity=resolved["auth_identity"],
        workspace=resolved["workspace"],
        provider_key=provider.key,
    )
    fragment = urlencode({
        # 令牌走 fragment 而不是 query：query 会进服务端访问日志、代理日志与 Referer，
        # fragment 只在浏览器内可见，且落地页会立即 replaceState 抹掉历史（见前端
        # lib/oauthReturn.js）。这是 OAuth implicit 回传访问令牌的既有标准做法。
        "oauth_access_token": access["token"],
        "oauth_access_token_expires_in": str(access.get("expires_in") or ""),
        "oauth_session_token": session["session_token"],
        "oauth_workspace_id": session["workspace_id"],
        "oauth_provider": provider.key,
        "oauth_return_to": stored.get("return_to") or "",
    })
    target = _landing_url(fragment)
    logger.info(
        "social login ok: provider=%s principal=%s ws=%s new=%s",
        provider.key, resolved["principal"]["principal_id"],
        session["workspace_id"], resolved.get("provisioned"),
    )
    return RedirectResponse(target, status_code=302, headers={"Cache-Control": "no-store"})


def _get_db():
    from deps import get_db

    return get_db()


def _resolve_social_principal(db, *, provider, identity):
    """把外部身份映射为「有可用 workspace 的本系统账户」。

    三种情形：① 已绑定过该 subject → 直接登录；② 邮箱已有账户（用户先前用密码注册）
    → 绑定 subject 到该账户，不新建重复账户；③ 全新用户 → 建账户 + org/ws。
    ②③ 都走同一套 onboarding 代码，保证社交登录账户与注册账户权限同形。
    """
    from access_control import resolve_principal_for_oidc_claims
    from services import onboarding

    resolved = resolve_principal_for_oidc_claims(
        db,
        provider_key=provider.key,
        subject=identity.subject,
        email=identity.email,
        email_verified=identity.email_verified,
        display_name=identity.display_name,
        provider_type=SOCIAL_PROVIDER_TYPE,
    )
    principal = resolved.get("principal")
    if not principal:
        # 极端态：身份记录指向一个已被删除的 principal
        logger.error("oauth identity points at missing principal: %s", resolved["auth_identity"])
        return _error_redirect(provider_key=provider.key, code="account_unavailable")

    provisioned = False
    workspace = _pick_workspace(db, principal_id=principal["principal_id"])
    if workspace is None:
        if not resolved.get("principal_created"):
            # 邮箱已存在但没有任何可用 workspace：可能是历史邀请中途失败的账户。
            # 直接开通一个自有 org 会把「无权限的旧邮箱」升级成「org_owner」，
            # 因此只给**本次新建**的 principal 自动建档，其余引导走人工/邀请路径。
            logger.warning("social login refused: principal %s has no workspace", principal["principal_id"])
            return _error_redirect(provider_key=provider.key, code="no_workspace")
        attached = onboarding.attach_first_organization(
            db, principal=principal, auth_method=f"social:{provider.key}"
        )
        workspace = {
            "workspace": attached["workspace"],
            "organization_id": attached["organization"]["organization_id"],
        }
        provisioned = True

    _mark_email_verified_from_provider(db, principal=principal, identity=identity)
    return {
        "principal": db.fetch_principal(principal["principal_id"]) or principal,
        "auth_identity": resolved["auth_identity"],
        "workspace": workspace,
        "provisioned": provisioned,
    }


def _pick_workspace(db, *, principal_id: str) -> dict | None:
    """取该 principal 第一个「ws 成员关系 + 组织成员关系均有效」的 workspace。

    校验链与 ``login_with_password`` 一致（workspace 存在 → ws membership → org
    membership 且 status=active）：漏掉任一环都会签发出一个「进不去」的会话，而
    ``authenticate_access_token`` 每次请求都现读 membership，所以这里的判定不是
    形式检查，它决定令牌是否真的可用。
    """
    for membership in db.list_workspace_memberships_by_principal(principal_id) or []:
        workspace = db.fetch_workspace(membership["workspace_id"])
        organization_id = (workspace or {}).get("organization_id")
        if not workspace or not organization_id:
            continue
        org_membership = db.fetch_organization_membership(organization_id, principal_id)
        if org_membership and org_membership.get("status") == "active":
            return {"workspace": workspace, "organization_id": organization_id}
    return None


def _mark_email_verified_from_provider(db, *, principal: dict, identity) -> None:
    """把提供方已担保的邮箱归属落到 ``email_verified_at``。

    只有 principal 当前邮箱与提供方返回的邮箱**完全一致**才标记：否则一次
    「换了邮箱的旧账户社交登录」会把别人的未验证邮箱标成已验证。
    """
    if principal.get("email_verified_at"):
        return
    if (principal.get("email") or "").strip().lower() != identity.email:
        return
    try:
        db.mark_principal_email_verified(principal["principal_id"], _now_iso())
    except Exception as exc:  # noqa: BLE001 — 验证位失败不该阻断已完成的登录
        logger.warning("marking email verified after social login failed: %s", exc)


def _issue_social_session(db, *, principal: dict, auth_identity: dict, workspace: dict, provider_key: str):
    from access_control import issue_access_token, issue_oidc_session

    organization_id = workspace["organization_id"]
    workspace_id = workspace["workspace"]["workspace_id"]
    session = issue_oidc_session(
        db,
        principal_id=principal["principal_id"],
        organization_id=organization_id,
        workspace_id=workspace_id,
        auth_identity_id=auth_identity["auth_identity_id"],
        auth_method=f"social:{provider_key}",
    )
    access = issue_access_token(
        db,
        principal_id=principal["principal_id"],
        workspace_id=workspace_id,
        session_id=session["session_id"],
    )
    return session, access


__all__ = [
    "SOCIAL_PROVIDER_TYPE",
    "complete_login",
    "list_providers",
    "router",
    "start_login",
]
