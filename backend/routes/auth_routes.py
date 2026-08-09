"""Web 会话引导认证（补齐前端认证缺口，2026-08-08；同源门控修订，2026-08-09）。

背景：agent 写端点（run/run-async/chat-stream/history）自 P0 加固后要求
JWT Bearer，但 web 前端此前没有任何令牌获取/附加逻辑，导致 agent UI 全部 401
（"Missing authorization header"）。本模块为 web UI 提供会话引导端点。

门控策略（2026-08-09 修订，取代此前“强制 secret”门控）：

1. **同站点门控（默认路径）**：携带 ``Origin``/``Referer`` 且与请求主机名
   匹配（忽略端口，兼容 vite dev 代理与生产直连 ``:8085``）的 web 请求
   自动签发低权限短 token。浏览器不允许脚本伪造 Origin 头，跨站页面
   无法通过；命中失败即 403（fail-closed）。
2. **可选显式共享密钥**：环境变量 ``AUS_ELE_WEB_BOOTSTRAP_SECRET`` 配置时，
   携带匹配 ``X-Bootstrap-Secret`` 的请求直接放行（覆盖无 Origin 的
   docker compose 同主机/CLI/健康检查调用方）；未配置时不再强制（避免
   漏配 env 引发 503 及下游级联 401）。
3. **显式允许名单**：``AUS_ELE_WEB_ALLOWED_ORIGINS``（逗号分隔完整 origin）
   支持前后端分离部署的显式放行。

此前强制 secret 门控要求后端 env 与前端构建变量两处严格同步，任一侧
漏配/重启即必现 503（"Bootstrap secret not configured"）与下游 401，
且该 secret 本就嵌入浏览器包、对 CWE-306 防护有限，故改为本策略。

- 签发短期 access token（principal=web-session），复用 access_control 的
  签发与审计链路（upsert_access_token + audit access_token.issued）。
- 该端点是 OIDC 人工登录接入前的权宜方案；安全 posture 说明见任务记录 §16.4-3。
"""

from __future__ import annotations

import datetime
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 引导身份固定 ID（upsert 幂等，避免每次请求新建 org/ws/principal）
_BOOTSTRAP_ORG = "org_webbootstrap"
_BOOTSTRAP_WS = "ws_default"
_BOOTSTRAP_PR = "pr_websession"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _allowed_origins() -> set[str]:
    raw = os.environ.get("AUS_ELE_WEB_ALLOWED_ORIGINS", "")
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}


def _same_site(request: Request) -> bool:
    """同源/同站点门控：Origin(或 Referer) 主机名与请求 Host 主机名一致。

    忽略端口以兼容三种部署形态：vite dev 代理（Host 被改写为
    127.0.0.1:8085）、生产直连 ``:8085``（Origin 无端口）、nginx 反代。
    Origin 为浏览器强制头，跨站脚本无法伪造；localhost/127.0.0.1
    开发来源视为放行（Origin 头本身不可伪造，仅限本机浏览器）。
    """
    origin = (request.headers.get("origin") or "").strip()
    referer = (request.headers.get("referer") or "").strip()
    origin_value = origin or referer
    if not origin_value:
        return False

    if origin_value.rstrip("/") in _allowed_origins():
        return True

    try:
        parsed = urlparse(origin_value)
    except ValueError:
        return False
    origin_host = parsed.hostname
    if not origin_host:
        return False
    if origin_host in {"localhost", "127.0.0.1"}:
        return True

    host_header = (request.headers.get("x-forwarded-host")
                   or request.headers.get("host") or "")
    if not host_header:
        return False
    request_host = host_header.split(",")[0].split(":")[0].strip().lower()
    return origin_host.lower() == request_host


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
    request: Request,
    x_bootstrap_secret: str | None = Header(default=None),
) -> dict:
    """Issue a short-lived access token for the web UI (bootstrap session).

    放行条件（任一即可）：显式共享密钥匹配；同站点 Origin/Referer 门控。
    两者都不满足时 fail-closed（403）。不再依赖强制 secret（避免漏配
    env 导致 503 + 下游 401 的脆弱链路）。
    """
    expected = os.environ.get("AUS_ELE_WEB_BOOTSTRAP_SECRET", "").strip()
    secret_ok = bool(expected) and (x_bootstrap_secret or "").strip() == expected

    if not secret_ok and not _same_site(request):
        raise HTTPException(
            status_code=403,
            detail=(
                "Web session bootstrap requires a same-site Origin/Referer "
                "or a valid bootstrap secret"
            ),
        )

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
