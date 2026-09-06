from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid

from fastapi import HTTPException

from shared_state import get_state_store


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 匿名 web-session 引导身份（P0.1，2026-09-05）
# ---------------------------------------------------------------------------
# routes/auth_routes.py 的 bootstrap 端点为「同源浏览器请求但尚未登录」的访客签发
# token，principal_id 固定。历史上该身份被授成 ws_default 的 owner，而账户写端点
# 只看 role → 匿名访客可越权改套餐/建邀请/吊销他人会话。此处提供单一事实来源，
# 使「principal 级守卫」不依赖 role（role 降级是第二道锁，见 P0.2）。
BOOTSTRAP_PRINCIPAL_ID = os.environ.get("AUS_ELE_BOOTSTRAP_PRINCIPAL_ID", "pr_websession")


def is_anonymous_bootstrap(actor_or_principal_id) -> bool:
    """判断给定 actor / principal 是否为匿名引导身份。

    兼容三种入参形态：完整 actor（含 principal 字典）、扁平 principal 字典、
    直接传 principal_id 字符串。None / 结构缺失一律判为非匿名（不误伤正常用户）。
    """
    if not actor_or_principal_id:
        return False
    if isinstance(actor_or_principal_id, str):
        return actor_or_principal_id == BOOTSTRAP_PRINCIPAL_ID
    if not isinstance(actor_or_principal_id, dict):
        return False
    principal = actor_or_principal_id.get("principal")
    if isinstance(principal, dict):
        return principal.get("principal_id") == BOOTSTRAP_PRINCIPAL_ID
    return actor_or_principal_id.get("principal_id") == BOOTSTRAP_PRINCIPAL_ID


def assert_human_actor(actor: dict, *, action: str) -> dict:
    """账户/权限类写操作的匿名守卫：引导身份一律 403。

    文案刻意通用（"requires a registered account"）：不复述内部角色或权限位，
    避免向匿名方泄露权限模型细节。返回 actor 以便调用方链式使用。
    """
    if is_anonymous_bootstrap(actor):
        logger.warning(
            "anonymous bootstrap denied on account write: action=%s workspace=%s",
            action,
            ((actor or {}).get("workspace") or {}).get("workspace_id"),
        )
        raise HTTPException(
            status_code=403,
            detail="This action requires a registered account",
        )
    return actor


ROLE_PERMISSIONS = {
    "owner": {"org_manage", "workspace_manage", "member_manage", "export", "read_audit"},
    "admin": {"workspace_manage", "member_manage", "export", "read_audit"},
    "analyst": {"export"},
    "viewer": set(),
    "exporter": {"export"},
}

ORG_ROLE_PERMISSIONS = {
    "org_owner": {"org_manage", "member_manage", "workspace_manage", "read_audit"},
    "org_admin": {"member_manage", "workspace_manage", "read_audit"},
    "org_billing_viewer": set(),
    "org_member": set(),
}


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Login rate limiter — sliding window, per-email
#
# P0.7（2026-09-05）：窗口外置到 Redis（多 worker 共享）。此前每个 worker 各持一份
# ``_login_attempts``，"5 次/分钟" 在 8 worker 下实际是 40 次 —— 对一个密码哈希只有
# 120k→600k 迭代、可离线爆破的账户体系，这个放大系数直接决定了爆破成本。
# Redis 不可用时回落为进程内窗口（不劣于外置之前），限流挂了不能变成放行。
# ---------------------------------------------------------------------------
_LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get("AUS_ELE_LOGIN_RATE_LIMIT", "5"))
_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60
_LOGIN_RATE_SCOPE = "login_rl"


def _check_login_rate_limit(email: str) -> None:
    """Raise 429 if the email has exceeded login attempts within the window."""
    allowed, retry_after = get_state_store().register_attempt(
        _LOGIN_RATE_SCOPE,
        email.lower().strip(),
        limit=_login_rate_limit_max(),
        window_seconds=_LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


def _login_rate_limit_max() -> int:
    """调用时读取，而不是只在 import 时读一次。

    外置之后运维改这个值应当立刻生效（这是限流，不是连接池），而模块级常量会把
    变更锁在重启之后。保留常量作为回退值，向后兼容既有直接引用。
    """
    raw = os.environ.get("AUS_ELE_LOGIN_RATE_LIMIT")
    try:
        return int(raw) if raw and raw.strip() else _LOGIN_RATE_LIMIT_MAX_ATTEMPTS
    except ValueError:
        return _LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def _clear_login_rate_limit(email: str) -> None:
    """Clear rate limit state on successful login."""
    get_state_store().clear_attempts(_LOGIN_RATE_SCOPE, email.lower().strip())


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso_datetime(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(normalized)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _jwt_secret() -> str:
    secret = os.environ.get("AUS_ELE_JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "AUS_ELE_JWT_SECRET environment variable is required. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    return secret


def _access_token_ttl_seconds() -> int:
    return int(os.environ.get("AUS_ELE_ACCESS_TOKEN_TTL_SECONDS", "3600"))


def _session_ttl_seconds() -> int:
    return int(os.environ.get("AUS_ELE_SESSION_TTL_SECONDS", str(30 * 24 * 60 * 60)))


def _issue_jwt_access_token(*, token_id: str, principal_id: str, workspace_id: str, session_id: str | None, expires_at: datetime.datetime) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "jti": token_id,
        "sub": principal_id,
        "workspace_id": workspace_id,
        "iat": int(_utc_now().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if session_id:
        payload["session_id"] = session_id
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        ]
    )
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def _decode_and_verify_jwt_access_token(token: str) -> dict:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        actual_signature = _b64url_decode(signature_segment)
        header = json.loads(_b64url_decode(header_segment).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid access token")
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Invalid access token")
    if int(payload.get("exp", 0)) <= int(_utc_now().timestamp()):
        raise HTTPException(status_code=401, detail="Access token expired")
    return payload


def _audit_actor_id(value) -> str | None:
    """审计写入前的 actor 归一：只接受 None 或真实 principal_id 字符串。

    路由函数被测试进程内直调时，``actor_principal_id`` 的默认值是 FastAPI 的
    ``Query(...)`` 占位对象（不是 None），原样写入审计表只会得到一个 PG 类型错误
    → 500。这里把它变成可读的编程错误，防止审计归因被静默丢失。
    """
    if value is None or isinstance(value, str):
        return value or None
    raise TypeError(f"audit actor_principal_id must be str or None, got {type(value).__name__}")


def _write_audit(db, *, actor_principal_id=None, workspace_id=None, action: str, target_type: str, target_id: str, detail_json=None):
    db.insert_audit_log(
        {
            "actor_principal_id": _audit_actor_id(actor_principal_id),
            "workspace_id": workspace_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "detail_json": detail_json or {},
            "created_at": _utc_now_iso(),
        }
    )


def _revoke_principal_auth_context(db, *, principal_id: str, organization_id: str):
    workspaces = db.list_workspaces(organization_id=organization_id)
    workspace_ids = [workspace["workspace_id"] for workspace in workspaces]
    sessions = db.list_auth_sessions_for_principal(
        principal_id,
        organization_id=organization_id,
        workspace_ids=workspace_ids or None,
    )
    for session in sessions:
        if not session.get("revoked"):
            db.upsert_auth_session({**session, "revoked": 1})
            _write_audit(
                db,
                actor_principal_id=principal_id,
                workspace_id=session.get("workspace_id"),
                action="auth.session_revoked",
                target_type="auth_session",
                target_id=session["session_id"],
                detail_json={"auth_method": session.get("auth_method"), "reason": "organization_membership_disabled"},
            )
    tokens = db.list_access_tokens_for_principal(principal_id, workspace_ids=workspace_ids or None)
    for token in tokens:
        if not token.get("revoked"):
            db.upsert_access_token({**token, "revoked": 1})
            _write_audit(
                db,
                actor_principal_id=principal_id,
                workspace_id=token.get("workspace_id"),
                action="access_token.revoked",
                target_type="access_token",
                target_id=token["token_id"],
                detail_json={"reason": "organization_membership_disabled"},
            )


# --- PBKDF2 强度（P0.6，2026-09-05）-----------------------------------------
# 120k 在 2026 年偏低，上调到 600k。**不换算法**：换 argon2/bcrypt 需要全库重哈希
# 而存量没有明文可重算，只能退化成「等用户登录再换」，那与迭代数升级的路径相同，
# 却会引入新依赖与镜像变更。迭代数是可参数化的、可渐进迁移的强度维度。
PBKDF2_LEGACY_ITERATIONS = 120_000
PBKDF2_TARGET_ITERATIONS = 600_000
# 下界钳制到迁移前基线：环境变量写错（少几个 0）会把新哈希算得比存量还弱，
# 而「已按弱值写库」不可逆 —— 之后无法退回强值去验证同一份哈希。
PBKDF2_ITERATIONS_FLOOR = PBKDF2_LEGACY_ITERATIONS


def _pbkdf2_iterations() -> int:
    """当前部署写入新哈希所使用的迭代次数。

    读 AUS_ELE_PBKDF2_ITERATIONS，默认 600k；该默认值同时登记在
    data/assumptions_registry.json（key: auth.pbkdf2_iterations）。
    非数字/缺失一律回默认，不让配置错误变成弱哈希写入。
    """
    raw = os.environ.get("AUS_ELE_PBKDF2_ITERATIONS")
    try:
        requested = int(raw) if raw and raw.strip() else PBKDF2_TARGET_ITERATIONS
    except ValueError:
        requested = PBKDF2_TARGET_ITERATIONS
    return max(PBKDF2_ITERATIONS_FLOOR, requested)


def _stored_iterations(principal: dict | None) -> int:
    """这份 password_hash 当初是用多少次迭代算出来的。

    NULL/脏值/低于基线一律按基线处理：最坏结果只是「多升级一次」，
    不会出现验证不过导致用户被锁在门外，也不会用被篡改的小值去比对。
    """
    try:
        value = int((principal or {}).get("pw_iters"))
    except (TypeError, ValueError):
        return PBKDF2_LEGACY_ITERATIONS
    return value if value >= PBKDF2_ITERATIONS_FLOOR else PBKDF2_LEGACY_ITERATIONS


def _upgrade_password_hash_if_stale(db, principal: dict, password: str) -> dict:
    """登录成功后的透明重哈希（P0.6）。

    时机是硬约束：只有在密码已被验证正确之后才有权改写凭据 —— 这既是唯一能拿到
    明文的时机，也保证不会给未认证账户写入攻击者选择的哈希。
    迭代数不增则不写库（避免每次登录一次无意义 UPDATE）。
    重哈希失败不得影响本次登录（用户已认证），降级为 warning + 审计。
    """
    stored = _stored_iterations(principal)
    target = _pbkdf2_iterations()
    if stored >= target or not _principal_has_password(principal):
        return principal
    salt = principal["password_salt"]
    try:
        refreshed = db.upsert_principal(
            {
                **principal,
                "password_hash": _hash_password(password or "", salt, target),
                "pw_iters": target,
                "updated_at": _utc_now_iso(),
            }
        )
    except Exception as exc:  # noqa: BLE001 — 已认证会话不能因写侧故障被打断
        logger.warning(
            "Password hash upgrade to %d iters failed for %s: %s",
            target,
            principal.get("principal_id"),
            exc,
        )
        return principal
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        action="principal.password_hash_upgraded",
        target_type="principal",
        target_id=principal["principal_id"],
        detail_json={"from_iters": stored, "to_iters": target},
    )
    return refreshed or principal


def _hash_password(password: str, salt: str, iterations: int | None = None) -> str:
    iters = _pbkdf2_iterations() if iterations is None else int(iterations)
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iters).hex()


def _principal_has_password(principal: dict | None) -> bool:
    return bool(principal and principal.get("password_hash") and principal.get("password_salt"))


def _verify_password(password: str, principal: dict) -> bool:
    """定长时间比较，避免把密码比对退化成计时 oracle。

    必须按该 principal 存储的迭代数计算（P0.6）：上调后新哈希用 600k、存量仍是
    120k，写死任一常量都会让另一半账户永远验不过。
    """
    return hmac.compare_digest(
        _hash_password(
            password or "", principal["password_salt"], _stored_iterations(principal)
        ).encode(),
        str(principal["password_hash"]).encode(),
    )


def _assert_password_policy(password: str) -> None:
    if len(password or "") < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")



def _build_actor(db, *, principal_id: str, workspace_id: str, session: dict | None = None, token: dict | None = None) -> dict:
    principal = db.fetch_principal(principal_id)
    workspace = db.fetch_workspace(workspace_id)
    membership = db.fetch_workspace_membership(workspace_id, principal_id)
    if not principal or not workspace or not membership:
        raise HTTPException(status_code=401, detail="Incomplete authentication context")
    actor = {
        "principal": principal,
        "workspace": workspace,
        "membership": membership,
    }
    if session is not None:
        actor["session"] = session
    if token is not None:
        actor["token"] = token
    organization_id = workspace.get("organization_id")
    if organization_id:
        org_membership = db.fetch_organization_membership(organization_id, principal_id)
        if org_membership and org_membership.get("status") != "active":
            raise HTTPException(status_code=401, detail="Inactive organization membership")
        if org_membership is not None:
            actor["organization_membership"] = org_membership
    return actor


def seed_organization(db, *, name: str) -> dict:
    org = db.upsert_organization(
        {
            "organization_id": f"org_{uuid.uuid4().hex[:12]}",
            "name": name,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(db, action="organization.created", target_type="organization", target_id=org["organization_id"], detail_json={"name": name})
    return org


def seed_workspace(db, *, organization_id: str, name: str) -> dict:
    workspace = db.upsert_workspace(
        {
            "workspace_id": f"ws_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "name": name,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        workspace_id=workspace["workspace_id"],
        action="workspace.created",
        target_type="workspace",
        target_id=workspace["workspace_id"],
        detail_json={"name": name, "organization_id": organization_id},
    )
    return workspace


def seed_principal(db, *, email: str, display_name: str) -> dict:
    principal = db.upsert_principal(
        {
            "principal_id": f"pr_{uuid.uuid4().hex[:12]}",
            "email": email,
            "display_name": display_name,
            "password_hash": None,
            "password_salt": None,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(db, actor_principal_id=principal["principal_id"], action="principal.created", target_type="principal", target_id=principal["principal_id"], detail_json={"email": email})
    return principal


def seed_workspace_membership(db, *, workspace_id: str, principal_id: str, role: str) -> dict:
    membership = db.upsert_workspace_membership(
        {
            "membership_id": f"m_{uuid.uuid4().hex[:12]}",
            "workspace_id": workspace_id,
            "principal_id": principal_id,
            "role": role,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="workspace_membership.upserted",
        target_type="workspace_membership",
        target_id=membership["membership_id"],
        detail_json={"principal_id": principal_id, "role": role},
    )
    return membership


def seed_organization_membership(db, *, organization_id: str, principal_id: str, role: str, status: str = "active") -> dict:
    membership = db.upsert_organization_membership(
        {
            "organization_membership_id": f"om_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "principal_id": principal_id,
            "role": role,
            "status": status,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="organization_membership.upserted",
        target_type="organization_membership",
        target_id=membership["organization_membership_id"],
        detail_json={"organization_id": organization_id, "role": role, "status": status},
    )
    return membership


def issue_access_token(db, *, principal_id: str, workspace_id: str, session_id: str | None = None) -> dict:
    expires_at = _utc_now() + datetime.timedelta(seconds=_access_token_ttl_seconds())
    token_id = f"tok_{uuid.uuid4().hex[:12]}"
    jwt_token = _issue_jwt_access_token(
        token_id=token_id,
        principal_id=principal_id,
        workspace_id=workspace_id,
        session_id=session_id,
        expires_at=expires_at,
    )
    token = db.upsert_access_token(
        {
            "token_id": token_id,
            "token": jwt_token,
            "principal_id": principal_id,
            "workspace_id": workspace_id,
            "created_at": _utc_now_iso(),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "revoked": 0,
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="access_token.issued",
        target_type="access_token",
        target_id=token["token_id"],
        detail_json={"workspace_id": workspace_id, "session_id": session_id},
    )
    return {
        **token,
        "token_type": "Bearer",
        "expires_in": _access_token_ttl_seconds(),
    }


def set_principal_password(db, *, principal_id: str, password: str) -> dict:
    principal = db.fetch_principal(principal_id)
    if not principal:
        raise HTTPException(status_code=404, detail="Principal not found")
    salt = secrets.token_hex(16)
    updated = db.upsert_principal(
        {
            **principal,
            "password_salt": salt,
            "password_hash": _hash_password(password, salt),
            "pw_iters": _pbkdf2_iterations(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="principal.password_set",
        target_type="principal",
        target_id=principal_id,
        detail_json={},
    )
    return updated


def change_principal_password(db, *, principal_id: str, current_password: str, new_password: str) -> dict:
    """自助修改密码（2026-08-14）：验证旧密码后设置新密码。

    错误语义与登录一致（401 不泄露细节）；新密码长度校验同邀请接受（≥8 位）。
    """
    principal = db.fetch_principal(principal_id)
    if not _principal_has_password(principal):
        raise HTTPException(status_code=401, detail="Invalid current password")
    if not _verify_password(current_password, principal):
        raise HTTPException(status_code=401, detail="Invalid current password")
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")
    return set_principal_password(db, principal_id=principal_id, password=new_password)


def link_auth_identity(db, *, principal_id: str, provider_key: str, subject: str, email: str,
                       email_verified: bool, provider_type: str = "oidc") -> dict:
    """绑定外部身份。

    ``provider_type`` 刻意可区分（R1.2）：企业 SSO 走 ``"oidc"``（per-org，provider_key
    由组织登记），社交登录走 ``"social"``。两者共用 ``auth_identity`` 表且唯一键是
    ``(provider_type, provider_key, subject)`` —— 如果社交登录也塞进 ``"oidc"``，某个组织
    只要把企业 provider_key 起成 ``google``，同一串 Google subject 就会命中同一条身份记录，
    「个人账户登录」与「企业 SSO 登录」在数据层悄悄合并。分成两个 type 之后这类撞名不可能
    发生，且不需要新表。
    """
    existing = db.fetch_auth_identity_by_subject(provider_type, provider_key, subject)
    if existing:
        return existing
    return db.upsert_auth_identity(
        {
            "auth_identity_id": f"ai_{uuid.uuid4().hex[:12]}",
            "principal_id": principal_id,
            "provider_type": provider_type,
            "provider_key": provider_key,
            "subject": subject,
            "email": email,
            "email_verified": int(bool(email_verified)),
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )


def resolve_principal_for_oidc_claims(db, *, provider_key: str, subject: str, email: str, email_verified: bool,
                                      display_name: str, provider_type: str = "oidc") -> dict:
    existing_identity = db.fetch_auth_identity_by_subject(provider_type, provider_key, subject)
    if existing_identity:
        return {
            "principal": db.fetch_principal(existing_identity["principal_id"]),
            "auth_identity": existing_identity,
        }
    principal = db.fetch_principal_by_email(email)
    created = False
    if principal is None:
        principal = seed_principal(db, email=email, display_name=display_name or email)
        created = True
    identity = link_auth_identity(
        db,
        principal_id=principal["principal_id"],
        provider_key=provider_key,
        subject=subject,
        email=email,
        email_verified=email_verified,
        provider_type=provider_type,
    )
    return {
        "principal": principal,
        "auth_identity": identity,
        # 调用方需要知道这是不是「刚建出来的裸账户」：本函数只建 principal，不建
        # org/ws（那是 onboarding 的职责）。没有这个标记，调用方只能靠猜来决定要不要
        # 给新用户开通工作空间 —— 猜错的表现为「登进来了但任何数据都存不了」。
        "principal_created": created,
    }


def login_with_password(db, *, email: str, password: str, workspace_id: str) -> dict:
    _check_login_rate_limit(email)
    principal = db.fetch_principal_by_email(email)
    if not _principal_has_password(principal):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not _verify_password(password, principal):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    workspace = db.fetch_workspace(workspace_id)
    membership = db.fetch_workspace_membership(workspace_id, principal["principal_id"])
    if not workspace or not membership:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    organization_id = workspace.get("organization_id")
    if organization_id:
        org_membership = db.fetch_organization_membership(organization_id, principal["principal_id"])
        if not org_membership or org_membership.get("status") != "active":
            raise HTTPException(status_code=403, detail="Organization access denied")
    expires_at = _utc_now() + datetime.timedelta(seconds=_session_ttl_seconds())
    session = db.upsert_auth_session(
        {
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "session_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "principal_id": principal["principal_id"],
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "auth_method": "password",
            "created_at": _utc_now_iso(),
            "last_seen_at": _utc_now_iso(),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "revoked": 0,
        }
    )
    access_token = issue_access_token(
        db,
        principal_id=principal["principal_id"],
        workspace_id=workspace_id,
        session_id=session["session_id"],
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        workspace_id=workspace_id,
        action="auth.login",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={"email": email},
    )
    _clear_login_rate_limit(email)
    # 透明升级存量弱哈希（P0.6）：放在限流清除之后，属于「登录已成功」的收尾动作，
    # 失败只记 warning，绝不回滚已签发的会话。
    _upgrade_password_hash_if_stale(db, principal, password)
    return {
        **session,
        "access_token": access_token["token"],
        "token_type": access_token["token_type"],
        "access_token_expires_at": access_token["expires_at"],
        "access_token_expires_in": access_token["expires_in"],
    }


def switch_workspace_session(db, *, principal_id: str, workspace_id: str) -> dict:
    """多工作空间切换（2026-08-14）：已登录用户切换到另一个所属 workspace。

    无需重输密码，但完整校验 workspace/组织成员资格；签发新会话与访问令牌，
    返回结构与 login_with_password 一致（前端 authStore 可直接消费）。
    """
    workspace = db.fetch_workspace(workspace_id)
    membership = db.fetch_workspace_membership(workspace_id, principal_id)
    if not workspace or not membership:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    organization_id = workspace.get("organization_id")
    if organization_id:
        org_membership = db.fetch_organization_membership(organization_id, principal_id)
        if not org_membership or org_membership.get("status") != "active":
            raise HTTPException(status_code=403, detail="Organization access denied")
    expires_at = _utc_now() + datetime.timedelta(seconds=_session_ttl_seconds())
    session = db.upsert_auth_session(
        {
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "session_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "principal_id": principal_id,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "auth_method": "workspace_switch",
            "created_at": _utc_now_iso(),
            "last_seen_at": _utc_now_iso(),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "revoked": 0,
        }
    )
    access_token = issue_access_token(
        db,
        principal_id=principal_id,
        workspace_id=workspace_id,
        session_id=session["session_id"],
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="auth.workspace_switch",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={},
    )
    return {
        **session,
        "access_token": access_token["token"],
        "token_type": access_token["token_type"],
        "access_token_expires_at": access_token["expires_at"],
        "access_token_expires_in": access_token["expires_in"],
    }


def _oidc_session_ttl_seconds() -> int:
    return int(os.environ.get("AUS_ELE_OIDC_SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60)))


def issue_oidc_session(db, *, principal_id: str, organization_id: str, workspace_id: str, auth_identity_id: str, auth_method: str = "oidc") -> dict:
    expires_at = _utc_now() + datetime.timedelta(seconds=_oidc_session_ttl_seconds())
    session = db.upsert_auth_session(
        {
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "session_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "principal_id": principal_id,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "auth_identity_id": auth_identity_id,
            "auth_method": auth_method,
            "created_at": _utc_now_iso(),
            "last_seen_at": _utc_now_iso(),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "revoked": 0,
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="auth.oidc_login",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={"organization_id": organization_id, "auth_identity_id": auth_identity_id},
    )
    return session


def authenticate_org_actor(db, organization_id: str, principal_id: str) -> dict:
    organization = db.fetch_organization(organization_id)
    principal = db.fetch_principal(principal_id)
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not organization or not principal or not membership or membership.get("status") != "active":
        raise HTTPException(status_code=401, detail="Invalid organization actor")
    return {
        "organization": organization,
        "principal": principal,
        "organization_membership": membership,
    }


def build_workspace_access_scope(db, *, organization_id: str, workspace_id: str, principal_id: str) -> dict:
    organization = db.fetch_organization(organization_id)
    workspace = db.fetch_workspace(workspace_id)
    principal = db.fetch_principal(principal_id)
    membership = db.fetch_workspace_membership(workspace_id, principal_id)
    policy = db.fetch_workspace_policy(workspace_id) or {
        "allowed_regions_json": [],
        "allowed_markets_json": [],
    }
    if not organization or not workspace or not principal or not membership:
        raise HTTPException(status_code=401, detail="Invalid workspace scope")
    if workspace["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Workspace organization mismatch")
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "principal_id": principal_id,
        "workspace_role": membership["role"],
        "allowed_regions": list(policy.get("allowed_regions_json") or []),
        "allowed_markets": list(policy.get("allowed_markets_json") or []),
    }


def assert_scope_allows_region_market(scope: dict, *, region: str | None = None, market: str | None = None):
    allowed_regions = set(scope.get("allowed_regions") or [])
    allowed_markets = set(scope.get("allowed_markets") or [])
    if region and allowed_regions and region not in allowed_regions:
        raise HTTPException(status_code=403, detail="Workspace access denied for region")
    if market and allowed_markets and market not in allowed_markets:
        raise HTTPException(status_code=403, detail="Workspace access denied for market")
    return True


def authenticate_access_token(db, token: str | None) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    claims = _decode_and_verify_jwt_access_token(token)
    token_row = db.fetch_access_token_by_value(token)
    if not token_row or token_row.get("revoked"):
        raise HTTPException(status_code=401, detail="Invalid access token")
    expires_at = _parse_iso_datetime(token_row.get("expires_at"))
    if expires_at and expires_at <= _utc_now():
        raise HTTPException(status_code=401, detail="Access token expired")
    if claims.get("sub") != token_row["principal_id"] or claims.get("workspace_id") != token_row["workspace_id"]:
        raise HTTPException(status_code=401, detail="Invalid access token")
    session = None
    session_id = claims.get("session_id")
    if session_id:
        session = db.fetch_auth_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=401, detail="Invalid access token")
        if session.get("revoked"):
            raise HTTPException(status_code=401, detail="Session revoked")
        if session["principal_id"] != token_row["principal_id"] or session["workspace_id"] != token_row["workspace_id"]:
            raise HTTPException(status_code=401, detail="Invalid access token")
        session_expires_at = _parse_iso_datetime(session.get("expires_at"))
        if session_expires_at and session_expires_at <= _utc_now():
            raise HTTPException(status_code=401, detail="Session expired")
    return _build_actor(db, principal_id=token_row["principal_id"], workspace_id=token_row["workspace_id"], token=token_row, session=session)


def authenticate_session_token(db, session_token: str | None) -> dict:
    if not session_token:
        raise HTTPException(status_code=401, detail="Missing session token")
    session = db.fetch_auth_session_by_token(session_token)
    if not session or session.get("revoked"):
        raise HTTPException(status_code=401, detail="Invalid session token")
    expires_at = _parse_iso_datetime(session.get("expires_at"))
    if expires_at and expires_at <= _utc_now():
        raise HTTPException(status_code=401, detail="Session expired")
    return _build_actor(db, principal_id=session["principal_id"], workspace_id=session["workspace_id"], session=session)


def refresh_session_access_token(db, session_token: str) -> dict:
    actor = authenticate_session_token(db, session_token)
    session = actor["session"]
    access_token = issue_access_token(
        db,
        principal_id=session["principal_id"],
        workspace_id=session["workspace_id"],
        session_id=session["session_id"],
    )
    updated_session = db.upsert_auth_session(
        {
            **session,
            "last_seen_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=session["principal_id"],
        workspace_id=session["workspace_id"],
        action="auth.refresh",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={},
    )
    return {
        **updated_session,
        "access_token": access_token["token"],
        "token_type": access_token["token_type"],
        "access_token_expires_at": access_token["expires_at"],
        "access_token_expires_in": access_token["expires_in"],
    }


def logout_session(db, session_token: str):
    session = db.fetch_auth_session_by_token(session_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.upsert_auth_session({**session, "revoked": 1})
    _write_audit(
        db,
        actor_principal_id=session["principal_id"],
        workspace_id=session["workspace_id"],
        action="auth.session_revoked",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={"auth_method": session.get("auth_method")},
    )


def check_organization_permission(actor: dict, permission: str):
    role = actor["organization_membership"]["role"]
    permissions = ORG_ROLE_PERMISSIONS.get(role, set())
    if permission not in permissions:
        raise HTTPException(status_code=403, detail="Organization permission denied")
    return True


def create_membership_invite(
    db,
    *,
    actor: dict,
    organization_id: str,
    workspace_id: str | None,
    target_scope_type: str,
    email: str,
    target_role: str,
    expires_at: str | None,
) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    normalized_email = email.strip().lower()
    existing_pending = db.list_membership_invites(
        organization_id,
        workspace_id=workspace_id,
        status="pending",
        email=normalized_email,
    )
    if existing_pending:
        return existing_pending[0]
    invite = db.upsert_membership_invite(
        {
            "invite_id": f"inv_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_scope_type": target_scope_type,
            "email": normalized_email,
            "target_role": target_role,
            "invite_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "status": "pending",
            "invited_by_principal_id": actor["principal"]["principal_id"],
            "accepted_by_principal_id": None,
            "revoked_by_principal_id": None,
            "expires_at": expires_at,
            "accepted_at": None,
            "revoked_at": None,
            "revoke_reason": None,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="membership_invite.created",
        target_type="membership_invite",
        target_id=invite["invite_id"],
        detail_json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_scope_type": target_scope_type,
            "email": invite["email"],
            "target_role": target_role,
        },
    )
    return invite


def revoke_membership_invite(db, *, actor: dict, invite_id: str, revoke_reason: str | None) -> dict:
    invite = db.fetch_membership_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if actor["organization"]["organization_id"] != invite["organization_id"]:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    if invite.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invite is not revocable")
    updated = db.upsert_membership_invite(
        {
            **invite,
            "status": "revoked",
            "revoked_by_principal_id": actor["principal"]["principal_id"],
            "revoked_at": _utc_now_iso(),
            "revoke_reason": revoke_reason,
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="membership_invite.revoked",
        target_type="membership_invite",
        target_id=invite_id,
        detail_json={"organization_id": invite["organization_id"], "revoke_reason": revoke_reason},
    )
    return updated


def reissue_membership_invite(db, *, actor: dict, invite_id: str, expires_at: str | None) -> dict:
    invite = db.fetch_membership_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if actor["organization"]["organization_id"] != invite["organization_id"]:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    if invite.get("status") == "accepted":
        raise HTTPException(status_code=400, detail="Accepted invite cannot be reissued")
    updated_at = _utc_now_iso()
    updated = db.upsert_membership_invite(
        {
            **invite,
            "invite_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "status": "pending",
            "accepted_by_principal_id": None,
            "revoked_by_principal_id": None,
            "expires_at": expires_at,
            "accepted_at": None,
            "revoked_at": None,
            "revoke_reason": None,
            "updated_at": updated_at,
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="membership_invite.reissued",
        target_type="membership_invite",
        target_id=invite_id,
        detail_json={"organization_id": invite["organization_id"], "expires_at": expires_at},
    )
    return updated


def _grant_organization_workspace_access(
    db,
    *,
    organization_id: str,
    principal_id: str,
    preferred_workspace_id: str | None = None,
    workspace_role: str = "viewer",
) -> dict | None:
    """给组织受邀者补一个工作空间成员身份，返回 ``{workspace, membership, created}``。

    为什么必须补：组织成员身份本身**不可登录**。``account_login`` 在缺省 workspace_id
    时按 ``list_workspace_memberships_by_principal`` 取首个，空列表直接抛 401
    ``Invalid email or password``。于是「只建 org membership」的接受流程会产生一条断头链：
    受邀者看到「邀请已接受」、密码也确实写进去了，然后登录时被告诉「密码错误」，
    并且没有任何 UI 能让他自己选一个工作空间 —— 因为选空间的前提是已登录。

    默认角色 ``viewer`` 而不是 ``member``：``ROLE_PERMISSIONS`` 里没有 ``member`` 这个
    键（合法值是 owner/admin/analyst/viewer/exporter），写错不会报错，只会静默给出一张
    空权限卡。真正的角色由组织管理员事后在工作空间层调整。
    """
    workspaces = db.list_workspaces(organization_id=organization_id)
    if preferred_workspace_id:
        preferred = [w for w in workspaces if w["workspace_id"] == preferred_workspace_id]
        # 首选空间已被删/不属于本组织时回落到其它空间，而不是让邀请失败 ——
        # 受邀者手里的 token 是唯一的入场券，不能因为管理员后来挪过空间就作废。
        workspaces = preferred or workspaces
    for workspace in workspaces:
        existing = db.fetch_workspace_membership(workspace["workspace_id"], principal_id)
        if existing:
            return {"workspace": workspace, "membership": existing, "created": False}
        membership = seed_workspace_membership(
            db,
            workspace_id=workspace["workspace_id"],
            principal_id=principal_id,
            role=workspace_role,
        )
        _write_audit(
            db,
            actor_principal_id=principal_id,
            workspace_id=workspace["workspace_id"],
            action="workspace_membership.granted_on_invite_accept",
            target_type="workspace_membership",
            target_id=membership["membership_id"],
            detail_json={"organization_id": organization_id, "role": workspace_role},
        )
        return {"workspace": workspace, "membership": membership, "created": True}
    return None


def accept_membership_invite(db, *, invite_token: str, display_name: str,
                             password: str | None = None,
                             also_join_workspace: bool = False,
                             workspace_role: str = "viewer") -> dict:
    """接受组织级邀请。

    ``password`` 是 R1.1 补齐的一致性缺口：组织级邀请原先完全不设密码，而工作空间级
    邀请（``accept_workspace_invite``）强制 ``set_principal_password``。开放自助注册后
    这个差异会变成死胡同 —— 经组织邀请进来的账户再去做注册会撞到「邮箱已被注册」，
    而它没有任何密码可用来登录。参数刻意可选（默认 None）以保持既有调用方与测试的
    行为不变；一旦注册入口上线，前端两条邀请接受路径都应当带上密码。

    ``also_join_workspace`` 是 R1.4 补上的断头链修复（默认 False 以保持既有 admin 端点与
    测试的行为不变）：组织级邀请原本只建组织成员身份，而组织成员身份不可登录 —— 详见
    ``_grant_organization_workspace_access``。自助邀请路径必须传 True。
    """
    invite = db.fetch_membership_invite_by_token(invite_token)
    if not invite or invite.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invite is not valid")
    expires_at = _parse_iso_datetime(invite.get("expires_at"))
    if expires_at and expires_at <= _utc_now():
        raise HTTPException(status_code=400, detail="Invite has expired")
    principal = db.fetch_principal_by_email(invite["email"])
    if not principal:
        principal = seed_principal(db, email=invite["email"], display_name=display_name)
    elif display_name and principal.get("display_name") != display_name:
        principal = db.upsert_principal({**principal, "display_name": display_name, "updated_at": _utc_now_iso()})
    if password:
        principal = set_principal_password(db, principal_id=principal["principal_id"], password=password)
    elif not principal.get("password_hash"):
        # 留一条可搜索的迹线：无密码账户只能靠「忘记密码」链路自救，
        # 出问题时这行日志是判断「为什么这个人登不进来」的第一手证据。
        logger.warning(
            "membership invite accepted without a password: principal=%s invite=%s",
            principal["principal_id"], invite["invite_id"])
    accepted_at = _utc_now_iso()
    updated_invite = db.upsert_membership_invite(
        {
            **invite,
            "status": "accepted",
            "accepted_by_principal_id": principal["principal_id"],
            "accepted_at": accepted_at,
            "updated_at": accepted_at,
        }
    )
    org_membership = seed_organization_membership(
        db,
        organization_id=invite["organization_id"],
        principal_id=principal["principal_id"],
        role=invite["target_role"],
        status="active",
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        action="membership_invite.accepted",
        target_type="membership_invite",
        target_id=invite["invite_id"],
        detail_json={"organization_id": invite["organization_id"], "organization_membership_id": org_membership["organization_membership_id"]},
    )
    workspace_grant = None
    if also_join_workspace:
        workspace_grant = _grant_organization_workspace_access(
            db,
            organization_id=invite["organization_id"],
            principal_id=principal["principal_id"],
            preferred_workspace_id=invite.get("workspace_id"),
            workspace_role=workspace_role,
        )
    result = {
        "invite": updated_invite,
        "principal": principal,
        "organization_membership": org_membership,
    }
    if workspace_grant:
        # 与 accept_workspace_invite 同形（都带 workspace.workspace_id），这样前端
        # 「接受完用邮箱+密码自动登录」那套逻辑不必为组织级另写一份落地代码。
        result["workspace"] = workspace_grant["workspace"]
        result["workspace_membership"] = workspace_grant["membership"]
    elif also_join_workspace:
        # 组织下一个工作空间都没有：邀请本身仍然成功（org membership 已建），但必须让
        # 调用方看得见「这个人登录后会是 403 无空间」，否则它只会以客服工单的形式出现。
        result["workspace_access_ready"] = False
    return result


# ---------------------------------------------------------------------------
# 组织域名信任锚（P0.3，2026-09-05）
# ---------------------------------------------------------------------------
# 原缺陷：任何 org_owner 都能登记任意域名，而 ``join_mode=domain_auto_join_org``
# 会直接授予活跃组织成员资格 —— 登记 ``gmail.com`` 等于对全体 Gmail 用户开放入组织。
# ``verified_at`` 列早已存在却从未被任何代码读取，本轮起它是唯一的授权前提。
# 参数登记：data/assumptions_registry.json → domain_verification_required_for_auto_join

PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com",
        "icloud.com", "qq.com", "163.com", "126.com", "foxmail.com",
        "proton.me", "protonmail.com",
    }
)

DNS_VERIFICATION_RECORD_PREFIX = "_aus-ele-verify."
DNS_VERIFICATION_VALUE_PREFIX = "aus-ele-verify="
DOMAIN_VERIFICATION_MAILBOXES = ("postmaster", "admin", "webmaster", "hostmaster")
DOMAIN_VERIFICATION_METHODS = ("dns_txt", "email")
# 域名加入模式白名单：避免拼错的值意外获得 auto_join 语义
ORGANIZATION_DOMAIN_JOIN_MODES = ("invite_only", "domain_auto_join_org")
# 挑战有效期：15 分钟。过期的 token 必须重新发起，避免长期挂着可用凭据。
DOMAIN_VERIFICATION_TTL_SECONDS = 15 * 60

_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])$")


class DomainVerificationUnavailable(RuntimeError):
    """验证手段在当前部署下不可用（缺 dnspython / 无 DNS 出口 / 解析超时）。

    路由层必须映射为 5xx 而非放行 —— fail-closed 是本模块的硬约束。
    """


def is_public_email_domain(domain: str) -> bool:
    """按末两级标签判定，使 ``mail.gmail.com`` 无法绕过黑名单。

    已知局限：不处理 ``user.co.uk`` 一类两段公共后缀（本黑名单不含此类）。
    """
    value = (domain or "").strip().lower().rstrip(".")
    labels = value.split(".")
    if len(labels) < 2:
        return value in PUBLIC_EMAIL_DOMAINS
    return ".".join(labels[-2:]) in PUBLIC_EMAIL_DOMAINS


def normalize_organization_domain(raw: str) -> str:
    """域名登记归一 + 合法性/黑名单校验（公共域名禁止登记，含子域形式）。"""
    value = (raw or "").strip().lower().rstrip(".")
    if not value or len(value) > 253 or any(ch in value for ch in (" ", "@", "/", "*", "_")):
        raise HTTPException(status_code=400, detail="Invalid domain")
    labels = value.split(".")
    if len(labels) < 2:
        raise HTTPException(status_code=400, detail="Invalid domain")
    if not all(_DOMAIN_LABEL_RE.match(label) for label in labels):
        raise HTTPException(status_code=400, detail="Invalid domain")
    if is_public_email_domain(value):
        raise HTTPException(
            status_code=400,
            detail="Public email domains cannot be registered as an organization domain",
        )
    return value


def _require_domain_row(db, *, organization_id: str, domain_id: str) -> dict:
    row = db.fetch_organization_domain(domain_id)
    if not row or row["organization_id"] != organization_id:
        # 「不存在」与「不属于本组织」合并为 404，避免域名 ID 成为跨组织探测 oracle
        raise HTTPException(status_code=404, detail="Organization domain not found")
    return row


def _parse_iso(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _verification_challenge_age_seconds(row: dict) -> float | None:
    requested_at = _parse_iso(row.get("verification_requested_at"))
    if requested_at is None:
        return None
    delta = datetime.datetime.now(datetime.timezone.utc) - requested_at
    return delta.total_seconds()


def resolve_txt_records(name: str) -> list[str]:
    """默认 DNS TXT 解析器。缺依赖或解析失败一律抛 DomainVerificationUnavailable。"""
    try:
        import dns.resolver  # type: ignore
    except ImportError as exc:  # pragma: no cover — 取决于部署
        raise DomainVerificationUnavailable(f"dns resolver unavailable: {exc}") from exc
    try:
        answers = dns.resolver.resolve(name, "TXT")
    except Exception as exc:  # noqa: BLE001 — NXDOMAIN/超时/网络均归一为「不可用」
        raise DomainVerificationUnavailable(f"DNS lookup failed for {name}: {exc}") from exc
    records: list[str] = []
    for item in answers:
        chunks = getattr(item, "strings", None)
        if chunks is None:
            chunks = [bytes(item)]
        for chunk in chunks:
            records.append(chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else str(chunk))
    return records


def begin_domain_verification(
    db,
    *,
    organization_id: str,
    domain_id: str,
    method: str = "dns_txt",
    mailer=None,
    actor_principal_id: str | None = None,
) -> dict:
    """发起域名所有权挑战，返回该方法的验证指引。

    安全要点：``method="email"`` 时 token **只进邮箱、不回 API**。否则「能登记域名」
    就等价于「能读到验证 token」，邮件通道形同虚设。
    """
    actor_principal_id = actor_principal_id if isinstance(actor_principal_id, str) and actor_principal_id else None
    normalized_method = (method or "").strip().lower()
    if normalized_method not in DOMAIN_VERIFICATION_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported verification method")
    row = _require_domain_row(db, organization_id=organization_id, domain_id=domain_id)
    if row["verified"]:
        return {
            "domain_id": row["domain_id"],
            "domain": row["domain"],
            "method": normalized_method,
            "already_verified": True,
            "verified_at": row["verified_at"],
        }

    token = secrets.token_urlsafe(24)
    now = _utc_now_iso()
    payload = {
        "domain_id": row["domain_id"],
        "organization_id": row["organization_id"],
        "domain": row["domain"],
        "verified_at": row.get("verified_at"),
        "join_mode": row["join_mode"],
        "created_at": row["created_at"],
        "updated_at": now,
        "verification_token": token,
        "verification_requested_at": now,
    }

    if normalized_method == "dns_txt":
        record_name = f"{DNS_VERIFICATION_RECORD_PREFIX}{row['domain']}"
        db.upsert_organization_domain(payload)
        _write_audit(
            db,
            actor_principal_id=actor_principal_id,
            action="organization_domain.verification_requested",
            target_type="organization_domain",
            target_id=row["domain_id"],
            detail_json={"organization_id": organization_id, "domain": row["domain"], "method": "dns_txt"},
        )
        return {
            "domain_id": row["domain_id"],
            "domain": row["domain"],
            "method": "dns_txt",
            "expires_in_seconds": DOMAIN_VERIFICATION_TTL_SECONDS,
            "dns": {
                "record_type": "TXT",
                "record_name": record_name,
                "record_value": f"{DNS_VERIFICATION_VALUE_PREFIX}{token}",
            },
        }

    targets = [f"{mailbox}@{row['domain']}" for mailbox in DOMAIN_VERIFICATION_MAILBOXES]
    send = mailer
    if send is None:
        from services.email_sender import send_email as send  # noqa: F811 — 惰性导入，便于测试注入
    db.upsert_organization_domain(payload)
    results = []
    for target in targets:
        try:
            results.append(send(to=target,
                               subject=f"Verify {row['domain']} for your organization",
                               body=(
                                   f"Verification code for domain {row['domain']}:\n\n"
                                   f"    {token}\n\n"
                                   f"Enter this code in the organization domain settings within "
                                   f"{DOMAIN_VERIFICATION_TTL_SECONDS // 60} minutes.\n"
                                   f"If you did not request this, ignore this email.\n"
                               )))
        except Exception as exc:  # noqa: BLE001 — 单个地址失败不影响其余
            logger.warning("domain verification email failed for %s: %s", target, exc)
            results.append({"delivered": False, "degraded": True, "reason": str(exc)[:200]})
    delivered = [item for item in results if isinstance(item, dict) and item.get("delivered")]
    if not delivered:
        # 撤销已下发的挑战，避免留着无人可取的有效凭据
        db.upsert_organization_domain({**payload, "verification_token": None, "verification_requested_at": None})
        raise HTTPException(
            status_code=503,
            detail="Email verification is unavailable right now. Use DNS TXT verification instead.",
        )
    _write_audit(
        db,
        actor_principal_id=actor_principal_id,
        action="organization_domain.verification_requested",
        target_type="organization_domain",
        target_id=row["domain_id"],
        detail_json={"organization_id": organization_id, "domain": row["domain"], "method": "email"},
    )
    return {
        "domain_id": row["domain_id"],
        "domain": row["domain"],
        "method": "email",
        "expires_in_seconds": DOMAIN_VERIFICATION_TTL_SECONDS,
        "email": {"targets": targets, "delivered_count": len(delivered)},
    }


def verify_organization_domain(
    db,
    *,
    organization_id: str,
    domain_id: str,
    method: str,
    token: str | None = None,
    resolver=None,
    actor_principal_id: str | None = None,
) -> dict:
    """校验挑战凭据并置 ``verified_at``。任何失败都不改变现有状态（fail-closed）。"""
    normalized_method = (method or "").strip().lower()
    if normalized_method not in DOMAIN_VERIFICATION_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported verification method")
    row = _require_domain_row(db, organization_id=organization_id, domain_id=domain_id)
    if row["verified"]:
        return row

    stored = row.get("verification_token")
    if not stored:
        raise HTTPException(status_code=403, detail="Domain verification has not been started")
    age = _verification_challenge_age_seconds(row)
    if age is None or age > DOMAIN_VERIFICATION_TTL_SECONDS:
        raise HTTPException(status_code=403, detail="Domain verification code expired. Request a new one.")

    if normalized_method == "dns_txt":
        record_name = f"{DNS_VERIFICATION_RECORD_PREFIX}{row['domain']}"
        expected = f"{DNS_VERIFICATION_VALUE_PREFIX}{stored}"
        lookup = resolver or resolve_txt_records
        try:
            records = lookup(record_name) or []
        except DomainVerificationUnavailable as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — 解析器异常不得变成放行
            raise HTTPException(status_code=501, detail=f"DNS verification unavailable: {exc}") from exc
        if not any(hmac.compare_digest(expected, str(record)) for record in records):
            raise HTTPException(status_code=403, detail="Domain verification failed: expected DNS TXT record not found")
    else:
        if not token:
            raise HTTPException(status_code=422, detail="Verification code is required")
        if not hmac.compare_digest(stored, token.strip()):
            raise HTTPException(status_code=403, detail="Domain verification failed: incorrect code")

    now = _utc_now_iso()
    verified = db.upsert_organization_domain(
        {
            **row,
            "verified_at": now,
            "verification_token": None,  # 一次性凭据用后即焚，防离线重放
            "verification_requested_at": None,
            "updated_at": now,
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor_principal_id if isinstance(actor_principal_id, str) and actor_principal_id else None,
        action="organization_domain.verified",
        target_type="organization_domain",
        target_id=domain_id,
        detail_json={"organization_id": organization_id, "domain": row["domain"], "method": normalized_method},
    )
    return verified


def require_joinable_organization_domain(db, *, organization_id: str, email: str) -> dict:
    """域名能否作为「入组织授权锚」的唯一判定入口（P0.3）。

    顺序刻意把所有权验证放在 auto-join 判定之前：未验证域名即便配了 auto_join 也
    不得产生任何成员资格。公共域名额外兜底存量黑名单启用前的旧行。
    """
    normalized_email = (email or "").strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=400, detail="Invalid email")
    domain = normalized_email.split("@", 1)[-1]
    domain_record = db.fetch_organization_domain_by_name(domain)
    if not domain_record or domain_record["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization domain mismatch")
    if is_public_email_domain(domain):
        raise HTTPException(status_code=403, detail="Public email domains cannot grant organization access")
    if domain_record.get("join_mode") != "domain_auto_join_org":
        raise HTTPException(status_code=403, detail="Organization invite required")
    if not domain_record.get("verified"):
        raise HTTPException(
            status_code=403,
            detail="Organization domain is not verified. Auto-join requires domain ownership verification.",
        )
    return domain_record


def register_organization_domain(
    db,
    *,
    organization_id: str,
    domain: str,
    join_mode: str = "invite_only",
    domain_id: str | None = None,
    verified_at: str | None = None,
    actor_principal_id: str | None = None,
) -> dict:
    """登记/更新组织域名（唯一生产入口，P0.3）。

    三道保护：
      1. 域名归一 + 合法性 + 公共邮箱域名黑名单（含子域）；
      2. 同一域名已归属别的组织 → 409（含「转让 owner 时把已验证域名拖走」）；
      3. ``join_mode`` 白名单，避免拼错值意外落到 auto_join 语义。
    新登记的域名一律 ``verified_at=None``，必须另走验证流程才能用于 auto_join。
    """
    if not db.fetch_organization(organization_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    normalized_domain = normalize_organization_domain(domain)
    normalized_join_mode = (join_mode or "").strip().lower()
    if normalized_join_mode not in ORGANIZATION_DOMAIN_JOIN_MODES:
        raise HTTPException(status_code=422, detail="Unsupported domain join mode")

    if domain_id:
        existing_by_id = db.fetch_organization_domain(domain_id)
        if existing_by_id and existing_by_id["organization_id"] != organization_id:
            raise HTTPException(status_code=409, detail="Domain belongs to another organization")

    clash = db.fetch_organization_domain_by_name(normalized_domain)
    if clash and (clash["organization_id"] != organization_id or (domain_id and clash["domain_id"] != domain_id)):
        raise HTTPException(status_code=409, detail="Domain already registered by another organization")

    row = db.fetch_organization_domain(domain_id) if domain_id else None
    now = _utc_now_iso()
    record = {
        "domain_id": domain_id or f"dom_{uuid.uuid4().hex[:12]}",
        "organization_id": organization_id,
        "domain": normalized_domain,
        # 只有「同组织 + 同域名字符串」的更新才允许保留 verified_at（由 db 层再校验一次）
        "verified_at": verified_at if verified_at is not None else (row or {}).get("verified_at"),
        "join_mode": normalized_join_mode,
        "created_at": (row or {}).get("created_at") or now,
        "updated_at": now,
        "verification_token": (row or {}).get("verification_token"),
        "verification_requested_at": (row or {}).get("verification_requested_at"),
    }
    saved = db.upsert_organization_domain(record)
    _write_audit(
        db,
        # 路由层在进程内直调时该参数会是 FastAPI 的 Query 占位对象，必须归一为字符串
        actor_principal_id=actor_principal_id if isinstance(actor_principal_id, str) and actor_principal_id else None,
        action="organization_domain.registered",
        target_type="organization_domain",
        target_id=saved["domain_id"],
        detail_json={
            "organization_id": organization_id,
            "domain": normalized_domain,
            "join_mode": normalized_join_mode,
            "verified": saved.get("verified"),
        },
    )
    return saved


def ensure_organization_membership_from_domain_policy(
    db,
    *,
    organization_id: str,
    principal_id: str,
    email: str,
) -> tuple[dict, dict, bool]:
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=400, detail="Invalid email")
    domain = normalized_email.split("@", 1)[-1]
    domain_record = db.fetch_organization_domain_by_name(domain)
    if not domain_record or domain_record["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization domain mismatch")

    membership = db.fetch_organization_membership(organization_id, principal_id)
    if membership:
        if membership.get("status") != "active":
            raise HTTPException(status_code=403, detail="Organization access denied")
        return membership, domain_record, False

    # 新建成员资格 = 授权事件，必须过完整的域名信任锚（P0.3）。
    # 既有成员资格不在此处被回收：它的授予可能来自邀请而非域名，撤销域名不应
    # 连带把合法受邀用户锁在门外（回收是独立的治理动作）。
    require_joinable_organization_domain(db, organization_id=organization_id, email=normalized_email)

    membership = seed_organization_membership(
        db,
        organization_id=organization_id,
        principal_id=principal_id,
        role="org_member",
        status="active",
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="organization_membership.auto_joined",
        target_type="organization_membership",
        target_id=membership["organization_membership_id"],
        detail_json={"organization_id": organization_id, "domain": domain},
    )
    return membership, domain_record, True


def _list_principal_workspace_memberships_in_organization(db, *, organization_id: str, principal_id: str) -> list[dict]:
    items = []
    for workspace in db.list_workspaces(organization_id=organization_id):
        membership = db.fetch_workspace_membership(workspace["workspace_id"], principal_id)
        if membership:
            items.append(
                {
                    "workspace": workspace,
                    "membership": membership,
                }
            )
    return items


def join_organization_by_domain(
    db,
    *,
    organization_id: str,
    email: str,
    display_name: str,
    password: str,
) -> dict:
    organization = db.fetch_organization(organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=400, detail="Invalid email")

    # 信任锚先于任何写操作（P0.3）：未验证 / 公共 / 非本组织的域名不会创建 principal
    require_joinable_organization_domain(db, organization_id=organization_id, email=normalized_email)

    principal = db.fetch_principal_by_email(normalized_email)
    if principal is None:
        # 新 principal：域名已通过信任锚，此时才允许落库（避免为不可加入的域名
        # 留下垃圾 principal 行 —— 注册接口成为数据放大器）
        _assert_password_policy(password)
        principal = seed_principal(db, email=normalized_email, display_name=display_name or normalized_email)
        principal = set_principal_password(db, principal_id=principal["principal_id"], password=password)
    else:
        if not _principal_has_password(principal):
            # P0.4 修复：原实现是 `if principal.password_hash and principal.password_salt:`
            # 才校验密码 —— 没有密码的 principal（OAuth / 邀请链路产物）对**任意**
            # password 直接放行，并在下面把攻击者选择的密码写进账户 = 账户接管。
            _write_audit(
                db,
                actor_principal_id=principal["principal_id"],
                action="auth.domain_join_denied",
                target_type="principal",
                target_id=principal["principal_id"],
                detail_json={"reason": "passwordless_principal", "organization_id": organization_id},
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "This account has no password set. Sign in with your original method, "
                    "or set a password from your account page first."
                ),
            )
        if not _verify_password(password, principal):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if display_name and principal.get("display_name") != display_name:
            principal = db.upsert_principal({**principal, "display_name": display_name, "updated_at": _utc_now_iso()})

    org_membership, domain_record, auto_joined = ensure_organization_membership_from_domain_policy(
        db,
        organization_id=organization_id,
        principal_id=principal["principal_id"],
        email=normalized_email,
    )
    workspace_memberships = _list_principal_workspace_memberships_in_organization(
        db,
        organization_id=organization_id,
        principal_id=principal["principal_id"],
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        action="auth.domain_join",
        target_type="organization",
        target_id=organization_id,
        detail_json={
            "domain": domain_record["domain"],
            "auto_joined": auto_joined,
            "workspace_access_ready": bool(workspace_memberships),
        },
    )
    return {
        "organization": organization,
        "principal": principal,
        "organization_membership": org_membership,
        "workspace_memberships": workspace_memberships,
        "workspace_access_ready": bool(workspace_memberships),
    }


def suspend_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    if membership.get("role") == "org_owner":
        raise HTTPException(status_code=400, detail="Org owner cannot be suspended")
    updated = db.upsert_organization_membership({**membership, "status": "suspended", "updated_at": _utc_now_iso()})
    _revoke_principal_auth_context(db, principal_id=principal_id, organization_id=organization_id)
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.suspended",
        target_type="organization_membership",
        target_id=updated["organization_membership_id"],
        detail_json={"organization_id": organization_id, "principal_id": principal_id},
    )
    return updated


def reactivate_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    updated = db.upsert_organization_membership({**membership, "status": "active", "updated_at": _utc_now_iso()})
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.reactivated",
        target_type="organization_membership",
        target_id=updated["organization_membership_id"],
        detail_json={"organization_id": organization_id, "principal_id": principal_id},
    )
    return updated


def remove_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    if membership.get("role") == "org_owner":
        raise HTTPException(status_code=400, detail="Org owner cannot be removed")
    updated = db.upsert_organization_membership({**membership, "status": "removed", "updated_at": _utc_now_iso()})
    _revoke_principal_auth_context(db, principal_id=principal_id, organization_id=organization_id)
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.removed",
        target_type="organization_membership",
        target_id=updated["organization_membership_id"],
        detail_json={"organization_id": organization_id, "principal_id": principal_id},
    )
    return updated


def transfer_organization_owner(db, *, actor: dict, organization_id: str, new_owner_principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    if actor["organization_membership"]["role"] != "org_owner":
        raise HTTPException(status_code=403, detail="Only org owner can transfer ownership")
    previous_owner = db.fetch_organization_membership(organization_id, actor["principal"]["principal_id"])
    new_owner = db.fetch_organization_membership(organization_id, new_owner_principal_id)
    if not previous_owner or not new_owner:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    updated_previous = db.upsert_organization_membership(
        {**previous_owner, "role": "org_admin", "updated_at": _utc_now_iso()}
    )
    updated_new = db.upsert_organization_membership(
        {**new_owner, "role": "org_owner", "status": "active", "updated_at": _utc_now_iso()}
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.owner_transferred",
        target_type="organization",
        target_id=organization_id,
        detail_json={"previous_owner_principal_id": actor["principal"]["principal_id"], "new_owner_principal_id": new_owner_principal_id},
    )
    return {"previous_owner": updated_previous, "new_owner": updated_new}


def create_workspace_invite(db, *, actor: dict, workspace_id: str, email: str, role: str) -> dict:
    if actor["workspace"]["workspace_id"] != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    check_workspace_permission(actor, "member_manage")
    invite = db.upsert_workspace_invite(
        {
            "invite_id": f"inv_{uuid.uuid4().hex[:12]}",
            "workspace_id": workspace_id,
            "email": email.strip().lower(),
            "role": role,
            "invite_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "invited_by_principal_id": actor["principal"]["principal_id"],
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "revoked": 0,
            "accepted_at": None,
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        workspace_id=workspace_id,
        action="workspace_invite.created",
        target_type="workspace_invite",
        target_id=invite["invite_id"],
        detail_json={"email": invite["email"], "role": role},
    )
    return invite


def revoke_workspace_invite(db, *, actor: dict, invite_id: str) -> dict:
    invite = db.fetch_workspace_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if actor["workspace"]["workspace_id"] != invite["workspace_id"]:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    check_workspace_permission(actor, "member_manage")
    updated = db.upsert_workspace_invite(
        {
            **invite,
            "revoked": 1,
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        workspace_id=invite["workspace_id"],
        action="workspace_invite.revoked",
        target_type="workspace_invite",
        target_id=invite_id,
        detail_json={"email": invite["email"]},
    )
    return updated


def accept_workspace_invite(db, *, invite_token: str, display_name: str, password: str) -> dict:
    invite = db.fetch_workspace_invite_by_token(invite_token)
    if not invite or invite.get("revoked") or invite.get("accepted_at"):
        raise HTTPException(status_code=400, detail="Invite is not valid")
    principal = db.fetch_principal_by_email(invite["email"])
    if not principal:
        principal = seed_principal(db, email=invite["email"], display_name=display_name)
    elif display_name and principal.get("display_name") != display_name:
        principal = db.upsert_principal({**principal, "display_name": display_name, "updated_at": _utc_now_iso()})
    principal = set_principal_password(db, principal_id=principal["principal_id"], password=password)
    membership = seed_workspace_membership(
        db,
        workspace_id=invite["workspace_id"],
        principal_id=principal["principal_id"],
        role=invite["role"],
    )
    updated_invite = db.upsert_workspace_invite(
        {
            **invite,
            "accepted_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        workspace_id=invite["workspace_id"],
        action="workspace_invite.accepted",
        target_type="workspace_invite",
        target_id=invite["invite_id"],
        detail_json={"membership_id": membership["membership_id"]},
    )
    return {
        "invite": updated_invite,
        "principal": principal,
        "workspace": db.fetch_workspace(invite["workspace_id"]),
        "membership": membership,
    }


def check_workspace_permission(actor: dict, permission: str):
    role = actor["membership"]["role"]
    permissions = ROLE_PERMISSIONS.get(role, set())
    if permission not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied")
    return True
