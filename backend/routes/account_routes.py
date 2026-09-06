"""账户中心自助 API（P0 商业化，2026-08-13）。

邀请制用户体系的自助层：注册通过接受邀请完成（既有 /api/auth/invites/accept），
本模块提供登录后的自助查询与管理：
- GET  /me                                    当前用户与所属 workspace
- GET  /workspaces/{ws}/members               成员列表
- GET  /workspaces/{ws}/invites               邀请列表（owner/admin）
- POST /workspaces/{ws}/invites               创建邀请（owner/admin）
- POST /workspaces/{ws}/invites/{id}/revoke   撤销邀请（owner/admin）
- GET  /workspaces/{ws}/api-keys              API Key 列表（脱敏）
- POST /workspaces/{ws}/api-keys              创建 API Key（raw key 仅返回一次）
- POST /workspaces/{ws}/api-keys/{id}/revoke  吊销 API Key
- GET  /workspaces/{ws}/usage                 用量看板（近 N 天 API/Agent 用量）

设计约束：
- 全部端点要求 JWT access token（authenticate_access_token 全链校验）
- 路径 workspace_id 必须与令牌绑定的 workspace 一致（403 防越权）
- server.py 零改动；鉴权/邀请/Key 逻辑全部委托 access_control / external_api_v1
"""

from __future__ import annotations

import datetime
import logging
import os
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from deps import get_db
from env_flags import env_int

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/account", tags=["account"])

_bearer_scheme = HTTPBearer(auto_error=False)

# 可邀请角色（owner 不可通过邀请产生）
INVITABLE_ROLES = {"admin", "analyst", "viewer", "exporter"}

_DEFAULT_PLAN = "starter"


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _get_actor(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> dict:
    """JWT Bearer → 完整 actor（principal/workspace/membership/org_membership）。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    from access_control import authenticate_access_token

    return authenticate_access_token(get_db(), credentials.credentials)


def _assert_workspace(actor: dict, workspace_id: str) -> None:
    """令牌绑定 workspace 与路径一致，否则 403（防水平越权）。"""
    if actor["workspace"]["workspace_id"] != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")


def _assert_human_write(actor: dict, *, action: str) -> None:
    """P0.1 匿名守卫（2026-09-05）：账户/权限类写操作拒绝 web-session 引导身份。

    必要性：``POST /api/v1/auth/web-session`` 对任意同源浏览器请求无凭据签发
    ``pr_websession`` token，而该身份在 ``ws_default`` 上历史持有 owner 角色 →
    只看 ``role`` 的写端点（订阅/API Key/邀请/成员密码/会话吊销）会被匿名触达。
    本守卫按 principal 判定，与角色解耦，故先于 P0.2 的角色降级发布。
    """
    from access_control import assert_human_actor

    assert_human_actor(actor, action=action)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class InviteCreateRequest(BaseModel):
    email: str = Field(..., description="受邀人邮箱")
    role: str = Field("analyst", description="角色：admin/analyst/viewer/exporter")


class ApiKeyCreateRequest(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=80, description="Key 名称")


class AccountLoginRequest(BaseModel):
    email: str = Field(..., description="登录邮箱")
    password: str = Field(..., description="密码")
    workspace_id: Optional[str] = Field(None, description="可缺省：自动取首个所属 workspace")


class InviteAcceptRequest(BaseModel):
    invite_token: str = Field(..., description="邀请 token")
    display_name: str = Field(..., description="显示名")
    password: str = Field(..., min_length=8, description="密码（至少 8 位）")


# ---------------------------------------------------------------------------
# 邀请接受限流（2026-08-14）：防 token 探测/暴力尝试。
# 同一 invite_token+IP 在 10 分钟内最多 10 次。
# server.py 的 query 版端点也复用本限流器（from-import 惰性引入）。
#
# P0.7（2026-09-05）：窗口外置到 shared_state。原实现有三个只在多 worker 下暴露的洞：
# 1. 每 worker 各持一份 → 10 次实际上限按 worker 数线性放大；
# 2. 过滤后的列表写回 dict 之前没有任何互斥 → 同 worker 并发可在 check-then-append
#    之间同时通过（TOCTOU），限流形同建议；
# 3. 键按 ``token|IP`` 无限累积，撞限路径也照加 → 探测本身就能把内存吃满。
# 之所以现在必须修：R1 的自助注册会把接受邀请路径推到公网入口，这个限流是它唯一的
# token 探测防线。
# ---------------------------------------------------------------------------

_INVITE_ACCEPT_MAX_ATTEMPTS = int(os.environ.get("AUS_ELE_INVITE_ACCEPT_RATE_LIMIT", "10"))
_INVITE_ACCEPT_WINDOW_SECONDS = 600
_INVITE_ACCEPT_RATE_SCOPE = "invite_accept_rl"


def _invite_accept_max_attempts() -> int:
    """调用时读取，而不是只在 import 时读一次（便于按环境调档而不改代码）。"""
    try:
        return max(0, int(os.environ.get("AUS_ELE_INVITE_ACCEPT_RATE_LIMIT", str(_INVITE_ACCEPT_MAX_ATTEMPTS))))
    except (TypeError, ValueError):
        return _INVITE_ACCEPT_MAX_ATTEMPTS


def check_invite_accept_rate_limit(invite_token: str, client_ip: str | None = None) -> None:
    from shared_state import get_state_store

    key = f"{invite_token}|{client_ip or 'unknown'}"
    allowed, retry_after = get_state_store().register_attempt(
        _INVITE_ACCEPT_RATE_SCOPE,
        key,
        limit=_invite_accept_max_attempts(),
        window_seconds=_INVITE_ACCEPT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many invite accept attempts, please retry later",
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=8, description="新密码（至少 8 位）")


@router.post("/password")
def change_password(body: PasswordChangeRequest, actor: dict = Depends(_get_actor)):
    """自助修改密码（2026-08-14）：验旧改新，错误语义与登录一致。"""
    _assert_human_write(actor, action="account.password_change")
    from access_control import change_principal_password

    change_principal_password(
        get_db(),
        principal_id=actor["principal"]["principal_id"],
        current_password=body.current_password,
        new_password=body.new_password,
    )
    logger.info("password changed: principal=%s", actor["principal"]["principal_id"])
    return {"changed": True}


# ---------------------------------------------------------------------------
# 忘记密码（2026-08-14）：邮件重置链路；防邮箱枚举（统一响应）
# ---------------------------------------------------------------------------

_RESET_TOKEN_TTL_SECONDS = 30 * 60

# 重置请求限流（R1.1 配套，2026-09-06）：自助注册开放前这里没有任何速率约束。
# 为什么必须补：注册入口一开，``/password/reset-request`` 就从「邀请制下的内部功能」
# 变成公开可刷端点 —— 每次调用都会插一行 password_reset 并走一次 SMTP 会话，
# 等于免费送人一个「灌满别人收件箱 + 撑爆我们库表」的开关。
_RESET_REQ_IP_SCOPE = "reset_request_ip_rl"
_RESET_REQ_EMAIL_SCOPE = "reset_request_email_rl"
_RESET_REQ_IP_LIMIT_DEFAULT = 20
_RESET_REQ_IP_WINDOW_SECONDS = 3600
_RESET_REQ_EMAIL_LIMIT_DEFAULT = 5
_RESET_REQ_EMAIL_WINDOW_SECONDS = 900


def _reset_req_ip_limit() -> int:
    return env_int("AUS_ELE_RESET_REQ_IP_LIMIT", _RESET_REQ_IP_LIMIT_DEFAULT, floor=1)


def _reset_req_email_limit() -> int:
    return env_int("AUS_ELE_RESET_REQ_EMAIL_LIMIT", _RESET_REQ_EMAIL_LIMIT_DEFAULT, floor=1)


def _enforce_reset_request_limits(client_ip: str, email: str) -> None:
    """两个正交维度：IP 拦「一份邮箱列表批量灌邮件」，邮箱维度拦「盯着一个人反复轰」。

    一律走 shared_state（P0.7 的外置窗口），不在本模块新建进程内 dict。
    """
    from shared_state import get_state_store

    store = get_state_store()
    for scope, key, limit, window in (
        (_RESET_REQ_IP_SCOPE, client_ip, _reset_req_ip_limit(), _RESET_REQ_IP_WINDOW_SECONDS),
        (_RESET_REQ_EMAIL_SCOPE, email, _reset_req_email_limit(), _RESET_REQ_EMAIL_WINDOW_SECONDS),
    ):
        allowed, retry_after = store.register_attempt(scope, key, limit=limit, window_seconds=window)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many password reset requests, please retry later",
                headers={"Retry-After": str(max(1, int(retry_after) + 1))},
            )


class PasswordResetRequestBody(BaseModel):
    email: str = Field(..., description="账户邮箱")


class PasswordResetConfirmBody(BaseModel):
    token: str = Field(..., description="重置令牌（邮件链接中）")
    new_password: str = Field(..., min_length=8, description="新密码（至少 8 位）")


def _reset_token_hash(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/password/reset-request")
def request_password_reset(body: PasswordResetRequestBody, request: Request = None):
    """请求密码重置邮件（无需登录）。防枚举：无论邮箱是否存在均返回相同响应。

    限流在「查邮箱」之前执行：否则被限流的探测请求仍然要先做一次 DB 查询，
    刷限流本身就成了免费的读放大。响应体不区分邮箱是否存在（429 也不区分）。
    """
    from routes.auth_routes import _client_ip  # 惰性：避免 account_routes ↔ auth_routes 成环

    db = get_db()
    email = (body.email or "").strip().lower()
    _enforce_reset_request_limits(_client_ip(request) if request is not None else "unknown", email)
    principal = db.fetch_principal_by_email(email) if email else None
    if principal:
        import secrets as _secrets

        token = _secrets.token_urlsafe(32)
        now = datetime.datetime.now(datetime.timezone.utc)
        db.insert_password_reset(
            {
                "reset_id": f"rst_{uuid.uuid4().hex[:12]}",
                "principal_id": principal["principal_id"],
                "token_hash": _reset_token_hash(token),
                "expires_at": (now + datetime.timedelta(seconds=_RESET_TOKEN_TTL_SECONDS))
                .isoformat().replace("+00:00", "Z"),
                "used_at": None,
                "created_at": now.isoformat().replace("+00:00", "Z"),
            }
        )
        # best-effort 发信；SMTP 未配置时降级（管理员可走成员管理重置）。
        # 但降级不能静默：send_email 永不抛，只看异常会把「一封都没发出去」判成成功，
        # 用户就卡在「说发了邮件却没收到」的死路（R1.1 修的同源问题）。
        try:
            from services.email_sender import send_email
            from services.email_verification import public_base_url
            from brand import BRAND_NAME_ZH, subject as email_subject

            # 绝对 URL（既有 bug 修复）：原来是 ``/reset?token=...``，在邮件客户端里
            # 点不开 —— 邮件没有 base URL 上下文，相对路径是死的。
            reset_url = f"{public_base_url()}/reset?token={token}"
            result = send_email(
                to=email,
                subject=email_subject("密码重置"),
                body=(
                    f"你正在重置 {BRAND_NAME_ZH} 账户密码。\n"
                    f"请在 30 分钟内访问以下链接完成重置：{reset_url}\n"
                    "若非本人操作，请忽略本邮件。"
                ),
            )
            if not (isinstance(result, dict) and result.get("delivered")):
                logger.warning(
                    "password reset email not delivered: principal=%s degraded=%s reason=%s",
                    principal["principal_id"],
                    bool((result or {}).get("degraded")) if isinstance(result, dict) else True,
                    (result or {}).get("reason") if isinstance(result, dict) else "non-dict result",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("password reset email failed: %s", exc)
    # 统一响应，不泄露邮箱存在性
    return {"sent": True}


@router.post("/password/reset-confirm")
def confirm_password_reset(body: PasswordResetConfirmBody):
    """凭邮件令牌重置密码；成功后吊销该用户全部会话与令牌。"""
    from access_control import set_principal_password

    db = get_db()
    record = db.fetch_password_reset_by_token_hash(_reset_token_hash(body.token))
    if not record or record.get("used_at"):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    expires_at = datetime.datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    if expires_at <= datetime.datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    set_principal_password(db, principal_id=record["principal_id"], password=body.new_password)
    db.mark_password_reset_used(record["reset_id"], datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"))
    # 安全：重置密码后全部既有会话/令牌失效
    db.revoke_auth_sessions_by_principal(record["principal_id"])
    db.revoke_access_tokens_by_principal(record["principal_id"])
    logger.info("password reset completed: principal=%s", record["principal_id"])
    return {"reset": True}


# ---------------------------------------------------------------------------
# 工作空间切换（2026-08-14）
# ---------------------------------------------------------------------------


@router.post("/workspaces/{workspace_id}/login-session")
def switch_workspace(workspace_id: str, actor: dict = Depends(_get_actor)):
    """已登录用户切换到另一个所属 workspace（免密码，完整资格校验）。"""
    _assert_human_write(actor, action="account.workspace_switch_session")
    from access_control import switch_workspace_session

    session = switch_workspace_session(
        get_db(),
        principal_id=actor["principal"]["principal_id"],
        workspace_id=workspace_id,
    )
    return session


# ---------------------------------------------------------------------------
# 资料编辑（2026-08-14）
# ---------------------------------------------------------------------------


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)


@router.patch("/me")
def update_profile(body: ProfileUpdateRequest, actor: dict = Depends(_get_actor)):
    _assert_human_write(actor, action="account.profile_update")
    db = get_db()
    principal = actor["principal"]
    updated = db.upsert_principal(
        {
            **principal,
            "display_name": body.display_name.strip(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    return {"principal_id": updated["principal_id"], "display_name": updated["display_name"]}


# ---------------------------------------------------------------------------
# 会话管理（2026-08-14）
# ---------------------------------------------------------------------------


@router.get("/sessions")
def list_sessions(actor: dict = Depends(_get_actor)):
    db = get_db()
    items = db.list_auth_sessions_by_principal(actor["principal"]["principal_id"])
    return {"items": items, "current_session_id": (actor.get("session") or {}).get("session_id")}


@router.post("/sessions/revoke-others")
def revoke_other_sessions(actor: dict = Depends(_get_actor)):
    """登出其他设备：保留当前会话，吊销其余会话与令牌。"""
    _assert_human_write(actor, action="account.sessions_revoke_others")
    db = get_db()
    pid = actor["principal"]["principal_id"]
    current = (actor.get("session") or {}).get("session_id")
    revoked = db.revoke_auth_sessions_by_principal(pid, exclude_session_id=current)
    db.revoke_access_tokens_by_principal(pid)
    # 重新给当前会话补发令牌已被吊销的影响：当前会话不受影响（令牌按 session 绑定，
    # revoke_access_tokens 会吊销含当前的全部令牌），由前端静默 refresh 重建
    return {"revoked_sessions": revoked}


# ---------------------------------------------------------------------------
# 管理员重置成员密码（2026-08-14，功能5）
# ---------------------------------------------------------------------------


class MemberPasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


@router.post("/workspaces/{workspace_id}/members/{principal_id}/reset-password")
def reset_member_password(
    workspace_id: str,
    principal_id: str,
    body: MemberPasswordResetRequest,
    actor: dict = Depends(_get_actor),
):
    """owner/admin 重置本 workspace 成员密码；重置后吊销目标全部会话。"""
    _assert_human_write(actor, action="account.member_password_reset")
    _assert_workspace(actor, workspace_id)
    if actor["membership"]["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can reset member passwords")
    db = get_db()
    if not db.fetch_workspace_membership(workspace_id, principal_id):
        raise HTTPException(status_code=404, detail="Member not found")
    from access_control import set_principal_password

    set_principal_password(db, principal_id=principal_id, password=body.new_password)
    db.revoke_auth_sessions_by_principal(principal_id)
    db.revoke_access_tokens_by_principal(principal_id)
    logger.info("member password reset: ws=%s target=%s by=%s",
                workspace_id, principal_id, actor["principal"]["principal_id"])
    return {"reset": True}


# ---------------------------------------------------------------------------
# Invite accept（JSON body 版，2026-08-13 代码审查修复）
# 既有 /api/auth/invites/accept 仅收 Query 参数，密码会进 URL → 落日志。
# 本端点用 JSON body，密码不进 URL（CWE-598）。server.py 保持零改动。
# ---------------------------------------------------------------------------


@router.post("/invites/accept")
def accept_invite(body: InviteAcceptRequest, request: "Request" = None):
    """接受邀请（注册）：JSON body，密码不进 URL；限流防 token 探测。"""
    from access_control import accept_workspace_invite

    check_invite_accept_rate_limit(
        body.invite_token, request.client.host if request and request.client else None
    )
    return accept_workspace_invite(
        get_db(),
        invite_token=body.invite_token.strip(),
        display_name=body.display_name.strip(),
        password=body.password,
    )


# ---------------------------------------------------------------------------
# Login（友好入口：workspace_id 可缺省）
# ---------------------------------------------------------------------------


@router.post("/login")
def account_login(body: AccountLoginRequest):
    """登录：不指定 workspace_id 时自动选首个所属 workspace。

    凭据校验/限流/会话签发全部委托 access_control.login_with_password，
    本端点只做 workspace 解析，错误语义与原 /api/auth/login 一致。
    """
    db = get_db()
    email = (body.email or "").strip().lower()
    principal = db.fetch_principal_by_email(email) if email else None
    workspace_id = body.workspace_id
    if not workspace_id:
        if not principal:
            # 与 login_with_password 相同的错误语义，不泄露邮箱是否存在
            raise HTTPException(status_code=401, detail="Invalid email or password")
        memberships = db.list_workspace_memberships_by_principal(principal["principal_id"])
        if not memberships:
            # 统一 401 语义：无 membership 与凭据错误不可区分（防邮箱枚举 oracle）
            raise HTTPException(status_code=401, detail="Invalid email or password")
        workspace_id = memberships[0]["workspace_id"]
    from access_control import login_with_password

    return login_with_password(db, email=email, password=body.password, workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get("/me")
def get_me(actor: dict = Depends(_get_actor)):
    """当前用户画像：principal + 全部 workspace 成员关系（含角色与组织名）。"""
    db = get_db()
    principal = actor["principal"]
    memberships = db.list_workspace_memberships_by_principal(principal["principal_id"])

    workspaces = []
    for m in memberships:
        ws = db.fetch_workspace(m["workspace_id"])
        if not ws:
            continue
        org = db.fetch_organization(ws["organization_id"]) if ws.get("organization_id") else None
        # 组织角色逐条查：actor 自带的 organization_membership 只覆盖**当前** workspace
        # 所属组织，而顶栏切换器要按每个空间分别判断「能不能进组织管理」。成员关系条数是
        # 个位数（一人不会加入几十个组织），这里的额外查询比让前端猜角色换来的正确性便宜。
        org_membership = (
            db.fetch_organization_membership(ws["organization_id"], principal["principal_id"])
            if ws.get("organization_id")
            else None
        )
        workspaces.append(
            {
                "workspace_id": m["workspace_id"],
                "name": ws.get("name"),
                "role": m["role"],
                "organization_id": ws.get("organization_id"),
                "organization_name": (org or {}).get("name"),
                "organization_role": (org_membership or {}).get("role"),
            }
        )

    return {
        "principal": {
            "principal_id": principal["principal_id"],
            "email": principal.get("email"),
            "display_name": principal.get("display_name"),
        },
        "current_workspace_id": actor["workspace"]["workspace_id"],
        "workspaces": workspaces,
    }


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/members")
def list_members(workspace_id: str, actor: dict = Depends(_get_actor)):
    """成员列表（含邮箱与显示名）。任何 workspace 成员可查。"""
    _assert_workspace(actor, workspace_id)
    db = get_db()
    members = []
    for m in db.list_workspace_memberships(workspace_id):
        p = db.fetch_principal(m["principal_id"])
        members.append(
            {
                "membership_id": m["membership_id"],
                "principal_id": m["principal_id"],
                "email": (p or {}).get("email"),
                "display_name": (p or {}).get("display_name"),
                "role": m["role"],
                "created_at": m["created_at"],
            }
        )
    return {"workspace_id": workspace_id, "members": members, "total": len(members)}


# ---------------------------------------------------------------------------
# Invites（邀请制注册闭环）
# ---------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/invites")
def list_invites(workspace_id: str, actor: dict = Depends(_get_actor)):
    """邀请列表（owner/admin）。token 仅在未接受/未撤销时返回（供复制邀请链接）。"""
    _assert_workspace(actor, workspace_id)
    from access_control import check_workspace_permission

    check_workspace_permission(actor, "member_manage")
    db = get_db()
    invites = []
    for inv in db.list_workspace_invites(workspace_id):
        active = (not inv["revoked"]) and not inv["accepted_at"]
        invites.append(
            {
                "invite_id": inv["invite_id"],
                "email": inv["email"],
                "role": inv["role"],
                "status": "accepted" if inv["accepted_at"] else ("revoked" if inv["revoked"] else "pending"),
                "invite_token": inv["invite_token"] if active else None,
                "created_at": inv["created_at"],
                "accepted_at": inv["accepted_at"],
            }
        )
    return {"workspace_id": workspace_id, "invites": invites, "total": len(invites)}


@router.post("/workspaces/{workspace_id}/invites")
def create_invite(workspace_id: str, body: InviteCreateRequest, actor: dict = Depends(_get_actor)):
    """创建邀请（owner/admin）。返回 invite_token，前端拼 /invite?token=xxx 链接。"""
    _assert_human_write(actor, action="account.invite_create")
    _assert_workspace(actor, workspace_id)
    role = (body.role or "").strip().lower()
    if role not in INVITABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(INVITABLE_ROLES)}")
    email = (body.email or "").strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email")
    from access_control import create_workspace_invite

    invite = create_workspace_invite(get_db(), actor=actor, workspace_id=workspace_id, email=email, role=role)
    return {
        "invite_id": invite["invite_id"],
        "email": invite["email"],
        "role": invite["role"],
        "invite_token": invite["invite_token"],
        "invite_url_path": f"/invite?token={invite['invite_token']}",
        "status": "pending",
    }


@router.post("/workspaces/{workspace_id}/invites/{invite_id}/revoke")
def revoke_invite(workspace_id: str, invite_id: str, actor: dict = Depends(_get_actor)):
    """撤销未接受的邀请（owner/admin）。"""
    _assert_human_write(actor, action="account.invite_revoke")
    _assert_workspace(actor, workspace_id)
    from access_control import revoke_workspace_invite

    updated = revoke_workspace_invite(get_db(), actor=actor, invite_id=invite_id)
    return {"invite_id": updated["invite_id"], "status": "revoked"}


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


def _mask_api_key(key_hash: str) -> str:
    return "****" + (key_hash[-4:] if key_hash else "")


@router.get("/workspaces/{workspace_id}/api-keys")
def list_api_keys(workspace_id: str, actor: dict = Depends(_get_actor)):
    """API Key 列表（脱敏：仅哈希尾 4 位 + 当日用量）。owner/admin 可见。"""
    _assert_workspace(actor, workspace_id)
    from access_control import check_workspace_permission
    from external_api_v1 import summarize_external_api_quota, _utc_day_start_iso

    check_workspace_permission(actor, "workspace_manage")
    db = get_db()
    keys = []
    for client in db.list_external_api_clients(workspace_id):
        quota = summarize_external_api_quota(db, client=client)
        keys.append(
            {
                "client_id": client["client_id"],
                "client_name": client["client_name"],
                "plan": client["plan"],
                "enabled": client["enabled"],
                "api_key_masked": _mask_api_key(client["api_key"]),
                "created_at": client["created_at"],
                "daily_unit_limit": quota["daily_unit_limit"],
                "used_units_today": quota["used_units"],
            }
        )
    return {"workspace_id": workspace_id, "api_keys": keys, "total": len(keys)}


@router.post("/workspaces/{workspace_id}/api-keys")
def create_api_key(workspace_id: str, body: ApiKeyCreateRequest, actor: dict = Depends(_get_actor)):
    """创建 API Key（owner/admin）。raw key 仅本次响应返回一次，此后不可再查。"""
    _assert_human_write(actor, action="account.api_key_create")
    _assert_workspace(actor, workspace_id)
    from access_control import check_workspace_permission
    from external_api_v1 import seed_external_api_client

    check_workspace_permission(actor, "workspace_manage")
    raw_key = "ak_" + secrets.token_urlsafe(32)
    client = seed_external_api_client(
        get_db(),
        client_id=f"cli_{uuid.uuid4().hex[:12]}",
        api_key=raw_key,
        client_name=body.client_name.strip(),
        plan=_DEFAULT_PLAN,
        organization_id=actor["workspace"].get("organization_id"),
        workspace_id=workspace_id,
    )
    logger.info("api key created: client_id=%s ws=%s", client["client_id"], workspace_id)
    return {
        "client_id": client["client_id"],
        "client_name": client["client_name"],
        "plan": client["plan"],
        "api_key_raw": raw_key,
        "warning": "api_key_raw 仅本次返回一次，请立即保存；页面关闭后无法再次查看",
    }


@router.post("/workspaces/{workspace_id}/api-keys/{client_id}/revoke")
def revoke_api_key(workspace_id: str, client_id: str, actor: dict = Depends(_get_actor)):
    """吊销 API Key（置为 disabled，不可恢复）。"""
    _assert_human_write(actor, action="account.api_key_revoke")
    _assert_workspace(actor, workspace_id)
    from access_control import check_workspace_permission

    check_workspace_permission(actor, "workspace_manage")
    db = get_db()
    client = db.fetch_external_api_client(client_id)
    if not client or client.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="API key not found")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    db.upsert_external_api_client({**client, "enabled": False, "updated_at": now})
    logger.info("api key revoked: client_id=%s ws=%s", client_id, workspace_id)
    return {"client_id": client_id, "enabled": False}


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/usage")
def get_usage(workspace_id: str, days: int = 30, actor: dict = Depends(_get_actor)):
    """用量看板：近 N 天 API 调用量（按天）+ Agent 运行次数（按天）。

    数据源为既有 external_api_usage 账本与 agent_execution_log，无新计量表。
    """
    _assert_workspace(actor, workspace_id)
    days = max(1, min(int(days), 90))
    db = get_db()

    since = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")

    # API 用量按天聚合（本 workspace 的 client）
    api_daily: dict[str, int] = {}
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT substr(u.created_at::text, 1, 10) AS day, COALESCE(SUM(u.request_units), 0)
                FROM {db.API_USAGE_TABLE} u
                JOIN {db.API_CLIENT_TABLE} c ON c.client_id = u.client_id
                WHERE c.workspace_id = ? AND u.created_at >= ?
                GROUP BY day ORDER BY day ASC
                """,
                (workspace_id, since),
            )
            for row in cursor.fetchall():
                api_daily[row[0]] = int(row[1] or 0)
    except Exception as exc:  # noqa: BLE001 — 账本表不存在时降级为空
        logger.debug("api usage aggregation skipped: %s", exc)

    # Agent 运行按天聚合（P1-1 计量加固后恢复，2026-08-14）：
    # agent_execution_log 已带 workspace_id 维度，按租户过滤无泄露
    agent_daily: dict[str, int] = {}
    try:
        # 惰性自愈列迁移：老库（表存在但列未迁移）下避免静默归零（2026-08-14 代码审查）
        from routes.agent_routes import _ensure_agent_log_table

        _ensure_agent_log_table()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='agent_execution_log'"
            )
            if cursor.fetchone():
                cursor.execute(
                    """
                    SELECT substr(created_at::text, 1, 10) AS day, COUNT(*)
                    FROM agent_execution_log
                    WHERE workspace_id = ? AND created_at >= ?
                    GROUP BY day ORDER BY day ASC
                    """,
                    (workspace_id, since),
                )
                for row in cursor.fetchall():
                    agent_daily[row[0]] = int(row[1] or 0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("agent usage aggregation skipped: %s", exc)

    return {
        "workspace_id": workspace_id,
        "window_days": days,
        "api_usage_daily": [{"date": d, "units": v} for d, v in sorted(api_daily.items())],
        "agent_runs_daily": [{"date": d, "runs": v} for d, v in sorted(agent_daily.items())],
        "totals": {
            "api_units": sum(api_daily.values()),
            "agent_runs": sum(agent_daily.values()),
        },
    }


class SubscriptionUpdateRequest(BaseModel):
    plan: str = Field(..., description="套餐：starter/growth/pro/internal")


# ---------------------------------------------------------------------------
# Subscription（P1-2 商业化，2026-08-14；支付后置，软配额只展示不阻断）
# ---------------------------------------------------------------------------

# internal 为运营/内部专用（无限配额），不得自助切换；enterprise 同理排除（2026-08-14 代码审查）
_UPDATABLE_PLANS = {"starter", "growth", "pro"}

# 日计数缓存（P0.7，2026-09-05）：workspace_id → (day, agent_runs, api_units)，60s TTL。
# 原先是两个进程内 dict（值 + 时间戳），多 worker 下每台各查各的：同一时刻两个请求
# 打到不同 worker 会拿到不同的"今日用量"，而软配额的 over_quota 标记正是从这里算出
# —— 配额展示不一致会在收费就绪时直接变成对账纠纷。外置到 shared_state（Redis 优先、
# 回落进程内），并把 day 一起存进值里：TTL 60s 跨过零点时不能拿昨天的计数报今天。
_QUOTA_CACHE_SCOPE = "quota_usage"
_QUOTA_CACHE_TTL_SECONDS = int(os.environ.get("AUS_ELE_QUOTA_CACHE_TTL_SECONDS", "60"))


def _state_store():
    from shared_state import get_state_store

    return get_state_store()


def _today_key() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _today_usage(db, workspace_id: str) -> tuple[int, int]:
    """今日 Agent 运行数 + API units（带 TTL 的跨 worker 共享缓存）。"""
    day = _today_key()
    cached = _state_store().recall(_QUOTA_CACHE_SCOPE, workspace_id)
    if (
        isinstance(cached, (list, tuple))
        and len(cached) == 3
        and cached[0] == day
    ):
        return int(cached[1]), int(cached[2])

    day_start = f"{day}T00:00:00Z"
    agent_runs = 0
    api_units = 0
    try:
        # 惰性自愈列迁移（2026-08-14 代码审查）
        from routes.agent_routes import _ensure_agent_log_table

        _ensure_agent_log_table()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='agent_execution_log'"
            )
            if cursor.fetchone():
                cursor.execute(
                    "SELECT COUNT(*) FROM agent_execution_log WHERE workspace_id = ? AND created_at >= ?",
                    (workspace_id, day_start),
                )
                agent_runs = int((cursor.fetchone() or [0])[0] or 0)
        from external_api_v1 import _utc_day_start_iso

        for client in db.list_external_api_clients(workspace_id):
            api_units += db.sum_external_api_usage_units(
                client_id=client["client_id"], created_at_from=_utc_day_start_iso()
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("quota usage query skipped: %s", exc)
        return agent_runs, api_units  # 异常路径不缓存，下次重算（2026-08-14 代码审查）

    # 值里带 day：跨零点时旧缓存的 day 对不上，读侧直接判为未命中重算（见上方注释）。
    _state_store().remember(
        _QUOTA_CACHE_SCOPE,
        workspace_id,
        [day, agent_runs, api_units],
        _QUOTA_CACHE_TTL_SECONDS,
    )
    return agent_runs, api_units


@router.get("/workspaces/{workspace_id}/subscription")
def get_subscription(workspace_id: str, actor: dict = Depends(_get_actor)):
    """订阅与配额：plan + 今日用量/配额（软配额，over_quota 只标记不阻断）。

    无订阅记录时返回默认 starter（不写库，避免并发建记录）。
    """
    _assert_workspace(actor, workspace_id)
    from external_api_v1 import AGENT_RUN_DAILY_LIMITS, PLAN_DAILY_UNIT_LIMITS

    db = get_db()
    sub = db.fetch_workspace_subscription(workspace_id)
    plan = (sub or {}).get("plan", "starter")
    status = (sub or {}).get("status", "active")

    agent_runs, api_units = _today_usage(db, workspace_id)
    agent_limit = AGENT_RUN_DAILY_LIMITS.get(plan)
    api_limit = PLAN_DAILY_UNIT_LIMITS.get(plan)

    return {
        "workspace_id": workspace_id,
        "plan": plan,
        "status": status,
        "payment_provider": (sub or {}).get("payment_provider"),
        "today": {
            "agent_runs": agent_runs,
            "agent_run_limit": agent_limit,
            "agent_over_quota": agent_limit is not None and agent_runs > agent_limit,
            "api_units": api_units,
            "api_unit_limit": api_limit,
            "api_over_quota": api_limit is not None and api_units > api_limit,
        },
        "note": "软配额：超额只标记不阻断；支付就绪后开启硬阻断（商业化路线图 P1-3）",
    }


@router.post("/workspaces/{workspace_id}/subscription")
def update_subscription(workspace_id: str, body: SubscriptionUpdateRequest, actor: dict = Depends(_get_actor)):
    """切换套餐（仅 owner，内部调套用；payment_provider 记为 manual）。"""
    _assert_human_write(actor, action="account.subscription_update")
    _assert_workspace(actor, workspace_id)
    if actor["membership"]["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owner can change subscription")
    plan = (body.plan or "").strip().lower()
    if plan not in _UPDATABLE_PLANS:
        raise HTTPException(status_code=422, detail=f"plan must be one of {sorted(_UPDATABLE_PLANS)}")
    db = get_db()
    updated = db.upsert_workspace_subscription(
        {
            "workspace_id": workspace_id,
            "plan": plan,
            "status": "active",
            "payment_provider": "manual",
            "payment_ref": None,
        }
    )
    # 失效跨 worker 生效（P0.7）：原先只 pop 本进程 dict，切套餐后其他 worker 仍会
    # 拿旧计数报旧配额的视图最长 60s。
    _state_store().forget(_QUOTA_CACHE_SCOPE, workspace_id)
    logger.info("subscription updated: ws=%s plan=%s", workspace_id, plan)
    return updated
