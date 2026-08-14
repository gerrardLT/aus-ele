"""SMTP 邮件发送（P2 告警邮件渠道，2026-08-14）。

环境变量（AGENT_ALERT_* 优先，兼容 SMTP_* 简写）：
- AGENT_ALERT_SMTP_HOST / SMTP_HOST
- AGENT_ALERT_SMTP_PORT / SMTP_PORT（465 = 隐式 SSL；其余端口走 SMTP）
- AGENT_ALERT_SMTP_USE_TLS / SMTP_USE_TLS（非 465 时：true=STARTTLS 必须成功，
  否则降级不发明文；false=明文，仅限可信内网）
- AGENT_ALERT_SMTP_USER / SMTP_USER
- AGENT_ALERT_SMTP_PASSWORD / SMTP_PASSWORD（163 为客户端授权码，非登录密码）
- AGENT_ALERT_SMTP_FROM / SMTP_FROM

安全约束（2026-08-14 审计修复）：要求 STARTTLS 而服务器不支持时直接失败降级，
绝不回退明文登录（避免凭据明文传输）。

HOST 或 FROM 缺失 → send_email 返回降级标记，调用方负责降级（如改写站内通知）。
发送超时 10s，best-effort 不抛异常。
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 10


def _env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def smtp_configured() -> bool:
    return bool(_env("AGENT_ALERT_SMTP_HOST", "SMTP_HOST") and _env("AGENT_ALERT_SMTP_FROM", "SMTP_FROM"))


def send_email(*, to: str, subject: str, body: str) -> dict:
    """发送邮件；未配置或失败时返回降级标记（不抛异常）。"""
    host = _env("AGENT_ALERT_SMTP_HOST", "SMTP_HOST")
    sender = _env("AGENT_ALERT_SMTP_FROM", "SMTP_FROM")
    if not host or not sender or not to:
        return {"delivered": False, "degraded": True, "reason": "smtp_not_configured"}
    try:
        port = int(_env("AGENT_ALERT_SMTP_PORT", "SMTP_PORT") or "465")
        use_tls = _env("AGENT_ALERT_SMTP_USE_TLS", "SMTP_USE_TLS").strip().lower() != "false"
        user = _env("AGENT_ALERT_SMTP_USER", "SMTP_USER")
        password = _env("AGENT_ALERT_SMTP_PASSWORD", "SMTP_PASSWORD")

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to

        if port == 465:
            # 465 = 隐式 SSL（163 等），不走 STARTTLS
            with smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(sender, [to], msg.as_string())
        else:
            # 其余端口：SMTP + STARTTLS（use_tls）或显式明文（仅限可信内网）
            with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as server:
                server.ehlo()
                if use_tls:
                    # STARTTLS 必须成功：不支持则抛异常走外层降级，
                    # 绝不回退明文登录（审计修复 2026-08-14）
                    server.starttls()
                    server.ehlo()
                if user and password:
                    server.login(user, password)
                server.sendmail(sender, [to], msg.as_string())
        return {"delivered": True, "degraded": False}
    except Exception as exc:  # noqa: BLE001 — best-effort，失败降级
        logger.warning("email send failed (to=%s): %s", to, exc)
        return {"delivered": False, "degraded": True, "reason": str(exc)[:200]}
