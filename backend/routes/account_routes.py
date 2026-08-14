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
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from deps import get_db

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
# Invite accept（JSON body 版，2026-08-13 代码审查修复）
# 既有 /api/auth/invites/accept 仅收 Query 参数，密码会进 URL → 落日志。
# 本端点用 JSON body，密码不进 URL（CWE-598）。server.py 保持零改动。
# ---------------------------------------------------------------------------


@router.post("/invites/accept")
def accept_invite(body: InviteAcceptRequest):
    """接受邀请（注册）：JSON body，密码不进 URL。"""
    from access_control import accept_workspace_invite

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
        workspaces.append(
            {
                "workspace_id": m["workspace_id"],
                "name": ws.get("name"),
                "role": m["role"],
                "organization_id": ws.get("organization_id"),
                "organization_name": (org or {}).get("name"),
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

# 进程内日计数缓存：workspace_id → (day, agent_runs, api_units)，60s TTL，
# 避免每次查订阅都聚合查库（B 视角性能设计）
_quota_cache: dict[str, tuple[str, int, int]] = {}
_QUOTA_CACHE_TTL_SECONDS = 60
_quota_cache_ts: dict[str, float] = {}


def _today_key() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _today_usage(db, workspace_id: str) -> tuple[int, int]:
    """今日 Agent 运行数 + API units（带 60s 进程内缓存）。"""
    import time as _time

    day = _today_key()
    cached = _quota_cache.get(workspace_id)
    ts = _quota_cache_ts.get(workspace_id, 0.0)
    if cached and cached[0] == day and (_time.time() - ts) < _QUOTA_CACHE_TTL_SECONDS:
        return cached[1], cached[2]

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

    _quota_cache[workspace_id] = (day, agent_runs, api_units)
    _quota_cache_ts[workspace_id] = _time.time()
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
    _quota_cache.pop(workspace_id, None)
    _quota_cache_ts.pop(workspace_id, None)
    logger.info("subscription updated: ws=%s plan=%s", workspace_id, plan)
    return updated
