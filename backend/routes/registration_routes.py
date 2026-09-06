"""自助注册与邮箱验证 API（R1.1，2026-09-06）。

- POST /api/v1/register            建账户 + 首个 org/ws，直接签发会话（201）
- POST /api/v1/register/verify     消费邮件链接里的 token
- POST /api/v1/register/resend     重发验证邮件（防枚举：恒定响应）
- GET  /api/v1/register/status     已登录视角的验证状态（前端 banner 数据源）

为什么注册后立刻签发会话（而不是「验证完才能用」）：计划把未验证的约束定为**软限制**，
只作用于新端点 + 前端 banner，并明写「绝不改 authenticate_access_token」。硬要验证后才
发令牌就等于改鉴权主链的语义，会把 SMTP 故障放大成全平台不可用。因此这里发的是与普通
登录完全同形的会话，未验证状态由 ``email_verified_at`` 单独表达。

紧急回滚（C 类，零代码）：``AUS_ELE_ENABLE_SELF_SERVICE_REGISTER=false`` 重启 → 注册与
重发一律 403，既有账户的登录/验证不受影响（验证端点保持可用，否则已发出的链接作废）。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from deps import get_db
from env_flags import env_flag, env_int
from routes.account_routes import _get_actor
from routes.auth_routes import _client_ip
from shared_state import get_state_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/register", tags=["registration"])

_REGISTER_ENABLED_ENV = "AUS_ELE_ENABLE_SELF_SERVICE_REGISTER"
_REGISTER_SCOPE = "register_rl"
_RESEND_EMAIL_SCOPE = "resend_verify_email_rl"
_RESEND_IP_SCOPE = "resend_verify_ip_rl"
# 阈值一律在调用时读（P0.6/P0.7 学到的同一课）：只在 import 时读一次的配置，测试无法
# 在 patch.dict 后生效，运行期也失去不发版调参的能力。
_REGISTER_IP_LIMIT_DEFAULT = 10
_REGISTER_IP_WINDOW_SECONDS = 3600
# 单 IP 建号上限：10/小时。公测期真实用户一人一号，这个量对 NAT/企业出口也够；
# 它同时是「拿免费额度批量建号」这条最划算路径的唯一收敛点。
_RESEND_EMAIL_LIMIT_DEFAULT = 3
_RESEND_EMAIL_WINDOW_SECONDS = 900  # 单邮箱重发上限：3 次 / 15 分钟，邮件通道的直接防线
_RESEND_IP_LIMIT_DEFAULT = 20
_RESEND_IP_WINDOW_SECONDS = 3600


def _register_ip_limit() -> int:
    return env_int("AUS_ELE_REGISTER_IP_LIMIT", _REGISTER_IP_LIMIT_DEFAULT, floor=1)


def _resend_email_limit() -> int:
    return env_int("AUS_ELE_RESEND_VERIFY_LIMIT", _RESEND_EMAIL_LIMIT_DEFAULT, floor=1)


def _resend_ip_limit() -> int:
    return env_int("AUS_ELE_RESEND_VERIFY_IP_LIMIT", _RESEND_IP_LIMIT_DEFAULT, floor=1)


def _assert_registration_open() -> None:
    if not env_flag(_REGISTER_ENABLED_ENV, True):
        raise HTTPException(
            status_code=403,
            detail="Self-service registration is temporarily unavailable",
        )


def _enforce_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int, detail: str) -> None:
    """限流一律走 shared_state（P0.7 已建立的外置窗口）。

    新入口不再新增进程内 dict —— 那正是 P0.7 清掉的那一类缺陷（按 worker 数放大、
    check-then-append 之间的 TOCTOU、撞限路径也照加导致键无限累积）。
    """
    allowed, retry_after = get_state_store().register_attempt(
        scope, key, limit=limit, window_seconds=window_seconds
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=254, description="登录邮箱")
    password: str = Field(..., description="密码（注册按密码策略校验）")
    display_name: str = Field(..., min_length=1, max_length=120, description="显示名")
    organization_name: Optional[str] = Field(None, max_length=160, description="组织名，缺省按显示名生成")


class VerifyRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=200, description="邮件链接中的 token")


class ResendRequest(BaseModel):
    email: str = Field(..., max_length=254, description="账户邮箱")


@router.post("", status_code=201)
def create_account(body: RegisterRequest, request: Request = None):
    """开放自助注册：邮箱 + 密码 + 显示名 → 账户 + org + workspace + 已登录会话。

    响应刻意复用 ``login_with_password`` 的返回形状，前端不必为注册单独写一套
    token 落地逻辑（也就不会出现「注册链路忘记写 session_token」这类分叉）。
    """
    from services import email_verification, onboarding, password_policy
    from access_control import login_with_password

    _assert_registration_open()
    ip = _client_ip(request) if request is not None else "unknown"
    _enforce_rate_limit(
        scope=_REGISTER_SCOPE, key=ip,
        limit=_register_ip_limit(), window_seconds=_REGISTER_IP_WINDOW_SECONDS,
        detail="Too many registrations from this address. Please try again later.",
    )

    db = get_db()
    email = onboarding.normalize_email(body.email)
    display_name = body.display_name.strip()
    password_policy.assert_registration_password(
        password=body.password, email=email, display_name=display_name
    )
    # 占用检查必须在密码策略之后：先拒弱密码，可以避免弱密码尝试被用来枚举邮箱。
    onboarding.assert_email_available(db, email)
    provisioned = onboarding.provision_account(
        db, email=email, display_name=display_name, password=body.password,
        organization_name=(body.organization_name or "").strip() or None,
    )
    principal = provisioned["principal"]

    verification = email_verification.request_verification(db, principal=principal)
    session = login_with_password(db, email=email, password=body.password,
                                  workspace_id=provisioned["workspace"]["workspace_id"])
    # 重新读一次 principal：request_verification 可能已经落库（SMTP 缺失时直接自动验证），
    # 用 provision 时那份旧 dict 判断会把「已验证」报成未验证，前端 banner 就常驻不去。
    fresh = db.fetch_principal(principal["principal_id"]) or {}
    email_verified_at = fresh.get("email_verified_at")
    logger.info("account registered: principal=%s ws=%s verify=%s",
                principal["principal_id"], provisioned["workspace"]["workspace_id"],
                verification["status"])
    return {
        **session,
        "email": email,
        "email_verified_at": email_verified_at,
        "email_verified": bool(email_verified_at),
        "verification_status": verification["status"],
    }


@router.post("/verify")
def verify_email(body: VerifyRequest, request: Request = None):
    """消费验证链接。无需登录（用户此刻还没有会话时也要能验证）。

    不设限流：token 是 32 字节 urlsafe 随机值、只有 24 小时有效期，且库里比对的是
    SHA-256 摘要 —— 爆破不可行；而真正的攻击面（拿到他人邮件链接）限流也拦不住。
    """
    from services import email_verification

    result = email_verification.complete_verification(
        get_db(), token=body.token.strip(),
        request_ip=_client_ip(request) if request is not None else None,
    )
    principal = get_db().fetch_principal(result["principal_id"]) or {}
    return {
        "verified": True,
        "email": principal.get("email"),
        "email_verified_at": result["email_verified_at"],
    }


@router.post("/resend", status_code=202)
def resend_verification(body: ResendRequest, request: Request = None):
    """重发验证邮件。无论邮箱是否存在都返回同一个 202（防邮箱枚举）。"""
    from services import email_verification

    _assert_registration_open()
    db = get_db()
    email = (body.email or "").strip().lower()
    ip = _client_ip(request) if request is not None else "unknown"
    # IP 维度先查：它拦的是「拿一份邮箱列表批量灌邮件」，与单邮箱上限正交。
    _enforce_rate_limit(
        scope=_RESEND_IP_SCOPE, key=ip,
        limit=_resend_ip_limit(), window_seconds=_RESEND_IP_WINDOW_SECONDS,
        detail="Too many verification emails. Please try again later.",
    )
    _enforce_rate_limit(
        scope=_RESEND_EMAIL_SCOPE, key=email,
        limit=_resend_email_limit(), window_seconds=_RESEND_EMAIL_WINDOW_SECONDS,
        detail="Too many verification emails for this address. Please try again later.",
    )
    principal = db.fetch_principal_by_email(email) if email else None
    if principal and not email_verification.is_email_verified(principal):
        # 返回值只用于日志；任何字段都不进响应，避免「已发送」与「已验证」的差异
        # 变成邮箱存在性与验证状态的探测口。
        email_verification.request_verification(db, principal=principal)
    return {"accepted": True}


@router.get("/status")
def verification_status(actor: dict = Depends(_get_actor)):
    """当前会话的验证状态（前端 banner 与「去验证」入口的数据源）。

    用 Bearer 令牌而不是邮箱做输入：本端点只服务于已登录用户，且不接受任何
    标识符参数 → 它天然没有枚举面。
    ``_get_actor`` 从 account_routes 复用而不是再抄第三份（p2_routes 已有一份）：
    Bearer → actor 的解析里含 401 语义，多份实现迟早在这些码上分叉。
    """
    principal = actor["principal"]
    return {
        "email": principal.get("email"),
        "email_verified_at": principal.get("email_verified_at"),
        "email_verified": bool(principal.get("email_verified_at")),
        "workspace_id": actor["workspace"]["workspace_id"],
        "organization_id": actor["workspace"].get("organization_id"),
    }


__all__ = [
    "router",
    "create_account",
    "verify_email",
    "resend_verification",
    "verification_status",
]
