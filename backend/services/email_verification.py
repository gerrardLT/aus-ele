"""邮箱验证链路（R1.1 自助注册，2026-09-06）。

安全要点（逐条都是本模块的硬约束）：

1. **库里只存 token 的 SHA-256**，不存明文 —— 与既有 ``password_reset`` 表同族同法。
   验证 token 是「谁控制这个邮箱」的证明物，数据库只读权限不该等价于账户接管能力。
2. **token 绝不出现在 API 响应或日志里**。``request_verification`` 的返回值刻意不含
   链接：否则「能触发重发」就等于「能读到验证链接」，邮件通道形同虚设（同 P0.3 对
   域名验证 token 的处置）。
3. **重发作废旧挑战**（见 ``db.insert_email_verification``）：被放弃的旧链接不该继续有效。
4. **SMTP 未配置不得锁死注册**：``AUS_ELE_AUTO_VERIFY_WHEN_NO_SMTP`` 为 true 时直接置
   已验证并审计（开发/内网自测环境）；为 false 时返回 degraded，由前端 banner 提示，
   账户仍可用（软限制只作用于新端点）。两个分支都必须 ``logger.warning``，
   因为「degraded 静默」正是 ``email_sender`` best-effort 语义最容易埋人的地方。
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import secrets
import uuid

from brand import BRAND_NAME_EN, BRAND_NAME_ZH, BRAND_TAGLINE_ZH, subject as email_subject
from env_flags import env_flag, env_int

logger = logging.getLogger(__name__)

# 参数登记：data/assumptions_registry.json → smtp_missing_auto_verify / email_link_base_url
DEFAULT_VERIFY_TTL_SECONDS = 24 * 60 * 60
DEV_BASE_URL = "http://localhost:5173"
AUTO_VERIFY_ENV = "AUS_ELE_AUTO_VERIFY_WHEN_NO_SMTP"
# 前端验证页（VerifyEmailPage.jsx）路径，与 lib/pageRouter.js 的分支一一对应。
VERIFICATION_PATH = "/verify-email"


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(moment: datetime.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def verify_ttl_seconds() -> int:
    # 下界 5 分钟：配成 0/负数会让每一封验证邮件在发出的瞬间就过期，
    # 表现为「用户点链接永远失败」这种极难归因的故障。
    return env_int("AUS_ELE_EMAIL_VERIFY_TTL_SECONDS", DEFAULT_VERIFY_TTL_SECONDS, floor=300)


def public_base_url() -> str:
    """邮件内链接的绝对前缀。生产必须显式配置，否则链接指向 localhost（见登记表 boundary）。"""
    return (os.environ.get("AUS_ELE_PUBLIC_BASE_URL") or DEV_BASE_URL).strip().rstrip("/")


def build_verification_url(token: str) -> str:
    return f"{public_base_url()}{VERIFICATION_PATH}?token={token}"


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def auto_verify_when_no_smtp() -> bool:
    return env_flag(AUTO_VERIFY_ENV, True)


def is_email_verified(principal: dict | None) -> bool:
    return bool((principal or {}).get("email_verified_at"))


def request_verification(db, *, principal: dict, mailer=None, actor_principal_id: str | None = None) -> dict:
    """为某个 principal 发起邮箱验证。

    ``mailer`` 可注入（测试用）；缺省取 ``services.email_sender.send_email``。
    返回 dict 刻意不含 token/url，字段为：
    ``{status, delivered, degraded, auto_verified, expires_at}``，
    其中 ``status`` ∈ {sent, auto_verified, not_configured, send_failed}。
    """
    principal_id = principal["principal_id"]
    email = (principal.get("email") or "").strip().lower()
    if not email:
        raise ValueError("principal has no email to verify")

    from services.email_sender import send_email, smtp_configured

    sender = mailer or send_email

    if not smtp_configured():
        if auto_verify_when_no_smtp():
            _mark_verified(db, principal_id=principal_id, actor_principal_id=principal_id,
                           action="principal.email_auto_verified_no_smtp",
                           detail={"reason": "smtp_not_configured"})
            logger.warning(
                "SMTP not configured; auto-verified email for %s because %s is true. "
                "Set %s=false in production.", principal_id, AUTO_VERIFY_ENV, AUTO_VERIFY_ENV)
            return {"status": "auto_verified", "delivered": False, "degraded": True,
                    "auto_verified": True, "expires_at": None}
        logger.warning("SMTP not configured and %s is false; verification email skipped for %s",
                       AUTO_VERIFY_ENV, principal_id)
        return {"status": "not_configured", "delivered": False, "degraded": True,
                "auto_verified": False, "expires_at": None}

    token = secrets.token_urlsafe(32)
    now = _utc_now()
    expires_at = now + datetime.timedelta(seconds=verify_ttl_seconds())
    db.insert_email_verification(
        {
            "verification_id": f"emv_{uuid.uuid4().hex[:12]}",
            "principal_id": principal_id,
            "email": email,
            "token_hash": hash_token(token),
            "requested_at": _iso(now),
            "expires_at": _iso(expires_at),
            "used_at": None,
        }
    )
    _write_audit(db, actor_principal_id=actor_principal_id or principal_id,
                 action="principal.email_verification_requested",
                 target_type="principal", target_id=principal_id,
                 detail_json={"email": email, "expires_at": _iso(expires_at)})

    result = _send_with_guard(sender, to=email, token=token)
    if result["delivered"]:
        return {"status": "sent", "delivered": True, "degraded": False,
                "auto_verified": False, "expires_at": _iso(expires_at)}

    # 发信失败：把刚登记的挑战一起作废，不留着无人可取的有效凭据（同 P0.3 处置）。
    outstanding = db.fetch_email_verification_by_token_hash(hash_token(token))
    if outstanding and not outstanding.get("used_at"):
        db.mark_email_verification_used(outstanding["verification_id"], _iso(_utc_now()))
    logger.warning("verification email undelivered for %s: degraded=%s reason=%s",
                   principal_id, result["degraded"], result.get("reason"))
    return {"status": "send_failed", "delivered": False, "degraded": bool(result["degraded"]),
            "auto_verified": False, "expires_at": None, "reason": result.get("reason")}


def _send_with_guard(sender, *, to: str, token: str) -> dict:
    """调用 mailer 并**强制检查 degraded**。

    ``email_sender.send_email`` 是 best-effort、永不抛异常的：只看有没有抛异常会把
    「一封都没发出去」判成成功。这里把返回值当成唯一的成功依据（异常只是额外一层）。
    """
    subject = email_subject("请验证你的邮箱地址")
    body = (
        f"你注册了{BRAND_NAME_ZH}（{BRAND_NAME_EN}）{BRAND_TAGLINE_ZH}账户。\n"
        f"请在 {_human_ttl(verify_ttl_seconds())} 内点击以下链接完成邮箱验证：\n"
        f"{build_verification_url(token)}\n"
        "若链接无法点击，请完整复制到浏览器地址栏。\n"
        "若非本人操作，请忽略本邮件，账户在验证前不会保存任何项目。"
    )
    try:
        result = sender(to=to, subject=subject, body=body)
    except Exception as exc:  # noqa: BLE001 — 与 email_sender 同语义：不发信不影响账户可用
        logger.warning("verification mailer raised: %s", exc)
        return {"delivered": False, "degraded": True, "reason": str(exc)[:200]}
    if not isinstance(result, dict):
        return {"delivered": False, "degraded": True, "reason": "mailer returned non-dict"}
    return {
        "delivered": bool(result.get("delivered")),
        "degraded": bool(result.get("degraded")),
        "reason": result.get("reason"),
    }


def _human_ttl(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600} 小时"
    return f"{max(1, seconds // 60)} 分钟"


def complete_verification(db, *, token: str, request_ip: str | None = None) -> dict:
    """消费一次性链接，置 ``email_verified_at``。返回 ``{principal_id, email_verified_at}``。

    失败一律 400 且用同一句话：token 无效 / 已使用 / 已过期 / 邮箱已变更 不做区分。
    链接是用户从邮件里复制来的，区分失败原因只会被用来探测哪些 token 曾存在过。
    """
    from fastapi import HTTPException

    record = db.fetch_email_verification_by_token_hash(hash_token(token))
    invalid = HTTPException(status_code=400, detail="Invalid or expired verification link")
    if not record or record.get("used_at"):
        raise invalid
    try:
        expires_at = datetime.datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        # 脏值按不可用处理（fail-closed）：读不出过期时间就等于无法证明它还在有效期内。
        raise invalid from None
    if expires_at <= _utc_now():
        raise invalid

    principal = db.fetch_principal(record["principal_id"])
    if not principal:
        raise invalid
    current_email = (principal.get("email") or "").strip().lower()
    if current_email != (record["email"] or "").strip().lower():
        # 挑战绑定发起时的邮箱：改过邮箱后旧链接必须失效，否则「验 a@x.com」能给
        # 后来改成 b@y.com 的账户盖上已验证章。
        raise invalid

    now_iso = _iso(_utc_now())
    db.mark_email_verification_used(record["verification_id"], now_iso)
    db.mark_principal_email_verified(record["principal_id"], now_iso)
    _write_audit(db, actor_principal_id=record["principal_id"],
                 action="principal.email_verified",
                 target_type="principal", target_id=record["principal_id"],
                 detail_json={"email": record["email"], "request_ip": request_ip})
    logger.info("email verified: principal=%s", record["principal_id"])
    return {"principal_id": record["principal_id"], "email_verified_at": now_iso}


def _write_audit(db, *, actor_principal_id: str | None, action: str, target_type: str,
                 target_id: str, detail_json: dict | None = None) -> None:
    """审计写入委托给 access_control._write_audit（单一事实来源，避免两份归一逻辑）。

    惰性 import：本模块会被 access_control 的下游导入，顶层反向 import 有循环风险。
    """
    from access_control import _write_audit as _ac_write_audit

    _ac_write_audit(db, actor_principal_id=actor_principal_id, action=action,
                    target_type=target_type, target_id=target_id, detail_json=detail_json or {})


def _mark_verified(db, *, principal_id: str, actor_principal_id: str | None, action: str,
                   detail: dict) -> None:
    now_iso = _iso(_utc_now())
    db.mark_principal_email_verified(principal_id, now_iso)
    _write_audit(db, actor_principal_id=actor_principal_id, action=action,
                 target_type="principal", target_id=principal_id, detail_json=detail)
