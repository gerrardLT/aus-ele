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
4. **签发限流 + 审计日志**（L3 加固）：Origin 头仅浏览器内不可伪造，
   上述门控只防浏览器介导的跨站攻击；对自设 Origin 的非浏览器调用方，
   以按 IP 滑动窗口限流（AUS_ELE_WEB_SESSION_RATE_LIMIT，默认 30 次/分钟，
   超限 429）+ 签发/拒绝审计日志收敛滥用面。

此前强制 secret 门控要求后端 env 与前端构建变量两处严格同步，任一侧
漏配/重启即必现 503（"Bootstrap secret not configured"）与下游 401，
且该 secret 本就嵌入浏览器包、对 CWE-306 防护有限，故改为本策略。

- 签发短期 access token（principal=web-session），复用 access_control 的
  签发与审计链路（upsert_access_token + audit access_token.issued）。
- 该端点是 OIDC 人工登录接入前的权宜方案；安全 posture 说明见任务记录 §16.4-3。
"""

from __future__ import annotations

import datetime
import logging
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 引导身份固定 ID（upsert 幂等，避免每次请求新建 org/ws/principal）
# principal_id 与 access_control.BOOTSTRAP_PRINCIPAL_ID 同源：账户写端点的匿名守卫
# （P0.1）按该常量判定，两处漂移会让守卫静默失效（有测试锁定，见
# tests/test_bootstrap_privilege_guard.py）。
from access_control import BOOTSTRAP_PRINCIPAL_ID
from shared_state import get_state_store

_BOOTSTRAP_ORG = "org_webbootstrap"
_BOOTSTRAP_WS = "ws_default"
_BOOTSTRAP_PR = BOOTSTRAP_PRINCIPAL_ID

# ── 签发限流（L3 加固，2026-08-09；P0.7 外置 2026-09-05）──────────────────
# Origin 门控只防浏览器介导的跨站请求，非浏览器调用方可自设 Origin；
# 叠加按 IP 滑动窗口限流，限制无凭据签发的滥用面（与 access_control 的
# 登录限流同款机制）。窗口存放已外置到 shared_state（Redis + 进程内回落），
# 不再依赖 worker 数。
_BOOTSTRAP_RATE_LIMIT_MAX = int(os.environ.get("AUS_ELE_WEB_SESSION_RATE_LIMIT", "30"))
_BOOTSTRAP_RATE_LIMIT_WINDOW_SECONDS = int(
    os.environ.get("AUS_ELE_WEB_SESSION_RATE_LIMIT_WINDOW", "60")
)
_BOOTSTRAP_RATE_SCOPE = "web_session_bootstrap_rl"


def _client_ip(request: Request) -> str:
    """取调用方 IP。

    优先 X-Real-IP：nginx 反代以 ``$remote_addr`` 覆写（可信）。
    不用 X-Forwarded-For 首段——它可被客户端伪造从而绕过限流（CWE-348）；
    无代理时回落 ASGI 对端地址。
    """
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    client = getattr(request, "client", None)
    return getattr(client, "host", "") or "unknown"


def _check_bootstrap_rate_limit(ip: str) -> None:
    """滑动窗口限流：超限抛 429。

    P0.7（2026-09-05）：窗口外置到 Redis，多 worker 共享。原先每个 worker 各持一份
    ``_bootstrap_attempts`` → 上限按 worker 数线性放大（30/分钟在 8 worker 下实际
    是 240/分钟，等于没有）；而且 check-then-append 之间没有锁，同 worker 并发也能
    穿过窗口。Redis 不可用时由 shared_state 回落为进程内窗口，行为不劣于外置之前。

    限流键仍取 ``_client_ip``（优先 X-Real-IP、刻意不用 X-Forwarded-For 首段，
    CWE-348）：外置不改变键的选取，否则会把可伪造性一起写进共享存储。
    """
    allowed, retry_after = get_state_store().register_attempt(
        _BOOTSTRAP_RATE_SCOPE,
        ip,
        limit=_BOOTSTRAP_RATE_LIMIT_MAX,
        window_seconds=_BOOTSTRAP_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many web-session bootstrap requests",
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _bootstrap_role() -> str:
    """匿名引导身份的 workspace 角色（P0.2，2026-09-05）。

    默认 ``viewer``（权限集为空）。历史实现硬编码 ``owner``，使匿名访客在
    ``ws_default`` 上获得 org_manage / workspace_manage / member_manage /
    export / read_audit 全套权限位 → 可读他人审计日志（含邮箱）、可自升套餐。

    回滚零代码：设 ``AUS_ELE_BOOTSTRAP_ROLE=owner`` 重启即可回到旧行为。
    非法值回落 viewer（fail-closed，不因配错而意外提权）。

    注：不需要「一次性降权 UPDATE」——``upsert_workspace_membership`` 是
    ``ON CONFLICT(workspace_id, principal_id) DO UPDATE SET role=excluded.role``
    （database.py:3517-3519），既有行会在下一次 bootstrap 请求时被自动对齐。
    """
    from access_control import ROLE_PERMISSIONS

    raw = (os.environ.get("AUS_ELE_BOOTSTRAP_ROLE") or "viewer").strip().lower()
    if raw not in ROLE_PERMISSIONS:
        logger.warning(
            "AUS_ELE_BOOTSTRAP_ROLE=%r is not a known role, falling back to viewer", raw
        )
        return "viewer"
    return raw


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
    """幂等创建引导身份链：org → workspace → principal → membership。

    role 由 ``_bootstrap_role()`` 决定（默认 viewer）。因为 ``authenticate_access_token``
    每次请求都从 membership 现读角色，降权对已签发令牌**立即生效**，无需等 token 过期。
    """
    now = _now_iso()
    target_role = _bootstrap_role()
    existing = db.fetch_workspace_membership(_BOOTSTRAP_WS, _BOOTSTRAP_PR)
    if existing and existing.get("role") != target_role:
        logger.info(
            "bootstrap membership role realigned: %s -> %s",
            existing.get("role"), target_role,
        )
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
         "principal_id": _BOOTSTRAP_PR, "role": target_role,
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

    安全边界（L3 加固，2026-08-09）：Origin 头仅在浏览器内不可伪造，
    同源门控防的是浏览器介导的跨站攻击；非浏览器调用方可自设 Origin，
    故叠加按 IP 滑动窗口限流（超限 429）+ 签发审计日志收敛滥用面。
    签发的是低权限短 token（web-session 引导身份），非管理员凭据。
    """
    ip = _client_ip(request)
    _check_bootstrap_rate_limit(ip)

    expected = os.environ.get("AUS_ELE_WEB_BOOTSTRAP_SECRET", "").strip()
    secret_ok = bool(expected) and (x_bootstrap_secret or "").strip() == expected

    if not secret_ok and not _same_site(request):
        logger.warning(
            "web-session bootstrap denied: ip=%s origin=%r", ip,
            request.headers.get("origin"),
        )
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
    logger.info(
        "web-session bootstrap issued: ip=%s origin=%r via=%s",
        ip, request.headers.get("origin"), "secret" if secret_ok else "same-site",
    )
    return {
        "token": issued["token"],
        "token_type": issued.get("token_type", "Bearer"),
        "expires_in": issued.get("expires_in"),
    }
