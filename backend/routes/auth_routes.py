"""Web 会话引导认证（补齐前端认证缺口，2026-08-08）。

背景：agent 写端点（run/run-async/chat-stream/history）自 P0 加固后要求
JWT Bearer，但 web 前端此前没有任何令牌获取/附加逻辑，导致 agent UI 全部 401
（"Missing authorization header"）。本模块为 web UI 提供会话引导端点：

- 若设置环境变量 ``AUS_ELE_WEB_BOOTSTRAP_SECRET``，请求必须携带匹配的
  ``X-Bootstrap-Secret`` 头（生产可由边缘层注入或构建期嵌入 VITE_ 变量）；
  未设置时视为内网/开发环境直接签发（仍写审计日志）。
- 签发短期 access token（principal=web-session），复用 access_control 的
  签发与审计链路（upsert_access_token + audit access_token.issued）。
- 该端点是 OIDC 人工登录接入前的权宜方案；安全 posture 说明见任务记录 §16.4-3。
"""

from __future__ import annotations

import datetime
import os

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 引导身份固定 ID（upsert 幂等，避免每次请求新建 org/ws/principal）
_BOOTSTRAP_ORG = "org_webbootstrap"
_BOOTSTRAP_WS = "ws_default"
_BOOTSTRAP_PR = "pr_websession"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_bootstrap_identity(db) -> None:
    """幂等创建引导身份链：org → workspace → principal → membership。"""
    now = _now_iso()
    db.upsert_organization(
        {"organization_id": _BOOTSTRAP_ORG, "name": "web-bootstrap",
         "created_at": now, "updated_at": now}
    )
    db.upsert_workspace(
        {"workspace_id": _BOOTSTRAP_WS, "organization_id": _BOOTSTRAP_ORG,
         "name": "default", "created_at": now, "updated_at": now}
    )
    db.upsert_principal(
        {"principal_id": _BOOTSTRAP_PR, "email": "web-session@local",
         "display_name": "Web Session (bootstrap)", "password_hash": None,
         "password_salt": None, "created_at": now, "updated_at": now}
    )
    db.upsert_workspace_membership(
        {"membership_id": "m_webbootstrap", "workspace_id": _BOOTSTRAP_WS,
         "principal_id": _BOOTSTRAP_PR, "role": "owner",
         "created_at": now, "updated_at": now}
    )


@router.post("/web-session")
def create_web_session(
    x_bootstrap_secret: str | None = Header(default=None),
) -> dict:
    """Issue a short-lived access token for the web UI (bootstrap session)."""
    expected = os.environ.get("AUS_ELE_WEB_BOOTSTRAP_SECRET", "").strip()
    if expected and (x_bootstrap_secret or "") != expected:
        raise HTTPException(status_code=403, detail="Bootstrap secret mismatch")

    from access_control import issue_access_token
    from deps import get_db

    db = get_db()
    _ensure_bootstrap_identity(db)
    issued = issue_access_token(
        db, principal_id=_BOOTSTRAP_PR, workspace_id=_BOOTSTRAP_WS
    )
    return {
        "token": issued["token"],
        "token_type": issued.get("token_type", "Bearer"),
        "expires_in": issued.get("expires_in"),
    }
