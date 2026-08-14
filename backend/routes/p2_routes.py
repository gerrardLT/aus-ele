"""P2 留存增值路由（2026-08-14）。

承载：站内通知、保存报告、用户偏好（保存视图）、反馈、审计查询。
鉴权模式与 account_routes 一致：HTTPBearer + authenticate_access_token 全链
校验 + _assert_workspace 防水平越权。server.py 零改动（routes 模块化注册）。
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from typing import Literal

from deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["p2"])

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_actor(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    from access_control import authenticate_access_token

    return authenticate_access_token(get_db(), credentials.credentials)


def _assert_workspace(actor: dict, workspace_id: str) -> None:
    if actor.get("workspace", {}).get("workspace_id") != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Notifications（站内通知，P2-1）
# ---------------------------------------------------------------------------


@router.get("/notify")
def list_notifications(
    workspace_id: str,
    limit: int = Query(50, ge=1, le=200),
    actor: dict = Depends(_get_actor),
):
    _assert_workspace(actor, workspace_id)
    db = get_db()
    # 自动清理（2026-08-14）：惰性删除 90 天前通知，best-effort
    try:
        db.purge_expired_notifications()
    except Exception as exc:  # noqa: BLE001
        logger.debug("notification purge skipped: %s", exc)
    return {"items": db.list_notifications_by_workspace(workspace_id, limit=limit)}


@router.get("/notify/unread-count")
def unread_count(workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    return {"unread": get_db().count_unread_notifications(workspace_id)}


@router.post("/notify/{notification_id}/read")
def mark_read(notification_id: str, workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    ok = get_db().mark_notification_read(notification_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"notification_id": notification_id, "read": True}


@router.post("/notify/read-all")
def mark_all_read(workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    return {"marked": get_db().mark_all_notifications_read(workspace_id)}


# ---------------------------------------------------------------------------
# Alert rules toggle（P2-1；server.py 的 create 端点每次生成新 rule_id，
# 无更新路径，此处补按 rule_id 的启停透传，避免重复建规则）
# ---------------------------------------------------------------------------


class AlertRuleToggleRequest(BaseModel):
    workspace_id: str
    enabled: bool


class AlertRuleCreateRequest(BaseModel):
    """鉴权版规则创建（审计修复 2026-08-14：既有 POST /api/alerts/rules 无鉴权，
    与 inapp 投递组合可跨租户注入通知；前端改用本端点）。"""

    workspace_id: str
    name: str = Field(..., min_length=1, max_length=200)
    rule_type: str
    market: str = "NEM"
    region_or_zone: str | None = None
    config: dict = Field(default_factory=dict)
    channel_type: str
    channel_target: str = ""


_VALID_RULE_TYPES = {"price_threshold", "data_freshness", "wem_fcas_scarcity"}
_VALID_CHANNEL_TYPES = {"webhook", "inapp", "email"}


@router.post("/alerts/rules")
def create_alert_rule_v1(body: AlertRuleCreateRequest, actor: dict = Depends(_get_actor)):
    """创建告警规则（鉴权 + workspace 一致性 + owner/admin 门槛）。"""
    _assert_workspace(actor, body.workspace_id)
    if actor["membership"]["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can create alert rules")
    if body.rule_type not in _VALID_RULE_TYPES:
        raise HTTPException(status_code=422, detail=f"rule_type must be one of {sorted(_VALID_RULE_TYPES)}")
    if body.channel_type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(status_code=422, detail=f"channel_type must be one of {sorted(_VALID_CHANNEL_TYPES)}")
    import uuid as _uuid

    db = get_db()
    now_iso = _utc_now_iso()
    return db.upsert_alert_rule(
        {
            "rule_id": f"al_{_uuid.uuid4().hex[:12]}",
            "name": body.name.strip(),
            "rule_type": body.rule_type,
            "market": body.market,
            "region_or_zone": body.region_or_zone,
            "config": body.config,
            "channel_type": body.channel_type,
            "channel_target": body.channel_target,
            "enabled": True,
            "organization_id": actor.get("workspace", {}).get("organization_id"),
            "workspace_id": body.workspace_id,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
    )


@router.post("/alerts/rules/{rule_id}/toggle")
def toggle_alert_rule(rule_id: str, body: AlertRuleToggleRequest, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, body.workspace_id)
    if actor["membership"]["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can manage alert rules")
    db = get_db()
    rule = db.fetch_alert_rule(rule_id)
    if not rule or rule.get("workspace_id") != body.workspace_id:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    updated = {**rule, "enabled": body.enabled, "updated_at": _utc_now_iso()}
    return db.upsert_alert_rule(updated)


# ---------------------------------------------------------------------------
# Saved reports（报告中心，P2-2）
# ---------------------------------------------------------------------------


class ReportSaveRequest(BaseModel):
    workspace_id: str
    title: str = Field(..., min_length=1, max_length=200)
    # 白名单：非法类型直接 422，避免 reports.py ValueError 裸 500（审计修复）
    report_type: Literal["monthly_market_report", "investment_memo_draft"] = "monthly_market_report"
    market: str = Field("NEM")
    region: str = Field(..., description="区域，如 NSW1")
    year: int = Field(..., ge=2015, le=2100)
    month: str | None = None


@router.post("/reports/save")
def save_report(body: ReportSaveRequest, actor: dict = Depends(_get_actor)):
    """生成并保存报告：包装既有 reports.generate_report_payload 落库。"""
    _assert_workspace(actor, body.workspace_id)
    from reports import generate_report_payload

    db = get_db()
    payload = generate_report_payload(
        db,
        report_type=body.report_type,
        year=body.year,
        region=body.region,
        month=body.month,
        organization_id=actor.get("workspace", {}).get("organization_id"),
        workspace_id=body.workspace_id,
    )
    report_id = f"rpt_{uuid.uuid4().hex[:16]}"
    db.insert_saved_report(
        {
            "report_id": report_id,
            "workspace_id": body.workspace_id,
            "title": body.title.strip(),
            "market": body.market,
            "region": body.region,
            "year": body.year,
            "payload": payload,
            "created_by": actor["principal"]["principal_id"],
            "created_at": _utc_now_iso(),
        }
    )
    return {"report_id": report_id, "title": body.title.strip()}


@router.get("/reports/saved")
def list_saved(workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    return {"items": get_db().list_saved_reports(workspace_id)}


@router.get("/reports/saved/{report_id}")
def get_saved(report_id: str, workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    report = get_db().fetch_saved_report(report_id)
    if not report or report["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.delete("/reports/saved/{report_id}")
def delete_saved(report_id: str, workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    if actor["membership"]["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete reports")
    ok = get_db().delete_saved_report(report_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report_id": report_id, "deleted": True}


# ---------------------------------------------------------------------------
# Report subscriptions（报告定时订阅，2026-08-14）
# ---------------------------------------------------------------------------


class ReportSubscriptionRequest(BaseModel):
    workspace_id: str
    subscription_id: str | None = None
    title: str = Field(..., min_length=1, max_length=200)
    market: str = "NEM"
    region: str = Field(..., description="区域，如 NSW1")
    frequency: Literal["monthly", "weekly"] = "monthly"
    day_of_month: int | None = Field(None, ge=1, le=31, description="monthly：每月几号")
    day_of_week: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] | None = Field(None, description="weekly：星期几")
    email: str | None = Field(None, max_length=254, description="收件邮箱，缺省用账户邮箱")
    enabled: bool = True


@router.get("/reports/subscriptions")
def list_report_subscriptions(workspace_id: str, actor: dict = Depends(_get_actor)):
    """我在本 workspace 的报告订阅。"""
    _assert_workspace(actor, workspace_id)
    items = get_db().list_report_subscriptions(
        workspace_id, principal_id=actor["principal"]["principal_id"]
    )
    return {"items": items}


@router.post("/reports/subscriptions")
def upsert_report_subscription(body: ReportSubscriptionRequest, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, body.workspace_id)
    if body.frequency == "monthly" and body.day_of_month is None:
        raise HTTPException(status_code=422, detail="monthly subscription requires day_of_month")
    if body.frequency == "weekly" and body.day_of_week is None:
        raise HTTPException(status_code=422, detail="weekly subscription requires day_of_week")
    db = get_db()
    record = {
        "subscription_id": body.subscription_id or f"rsub_{uuid.uuid4().hex[:16]}",
        "workspace_id": body.workspace_id,
        "principal_id": actor["principal"]["principal_id"],
        "title": body.title.strip(),
        "market": body.market,
        "region": body.region,
        "frequency": body.frequency,
        "day_of_month": body.day_of_month,
        "day_of_week": body.day_of_week,
        "email": body.email or actor["principal"].get("email"),
        "enabled": body.enabled,
        "last_sent_at": None,
        "created_at": _utc_now_iso(),
    }
    if body.subscription_id:
        existing = db.fetch_report_subscription(body.subscription_id)
        if not existing or existing["workspace_id"] != body.workspace_id:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if existing["principal_id"] != actor["principal"]["principal_id"]:
            raise HTTPException(status_code=403, detail="Cannot modify another user's subscription")
        record["last_sent_at"] = existing.get("last_sent_at")
        record["created_at"] = existing.get("created_at") or record["created_at"]
    return db.upsert_report_subscription(record)


@router.delete("/reports/subscriptions/{subscription_id}")
def delete_report_subscription(subscription_id: str, workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    db = get_db()
    existing = db.fetch_report_subscription(subscription_id)
    if not existing or existing["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if existing["principal_id"] != actor["principal"]["principal_id"] \
            and actor["membership"]["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Cannot delete another user's subscription")
    db.delete_report_subscription(subscription_id, workspace_id)
    return {"subscription_id": subscription_id, "deleted": True}


# ---------------------------------------------------------------------------
# Preferences（保存视图等个性化，P2-6）
# ---------------------------------------------------------------------------

_PREFERENCE_KEYS = {"saved_views", "favorite_regions"}


class PreferenceValueRequest(BaseModel):
    workspace_id: str
    value: dict = Field(default_factory=dict)


@router.get("/preferences/{key}")
def get_preference(key: str, workspace_id: str, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, workspace_id)
    if key not in _PREFERENCE_KEYS:
        raise HTTPException(status_code=422, detail=f"key must be one of {sorted(_PREFERENCE_KEYS)}")
    pref = get_db().fetch_user_preference(
        workspace_id, actor["principal"]["principal_id"], key
    )
    return {"key": key, "value": (pref or {}).get("value") or {}}


@router.put("/preferences/{key}")
def put_preference(key: str, body: PreferenceValueRequest, actor: dict = Depends(_get_actor)):
    _assert_workspace(actor, body.workspace_id)
    if key not in _PREFERENCE_KEYS:
        raise HTTPException(status_code=422, detail=f"key must be one of {sorted(_PREFERENCE_KEYS)}")
    # 防超大 payload（保存视图为小 JSON）
    if len(json.dumps(body.value, ensure_ascii=False)) > 64 * 1024:
        raise HTTPException(status_code=422, detail="Preference value too large")
    get_db().upsert_user_preference(
        {
            "preference_id": f"pref_{uuid.uuid4().hex[:16]}",
            "workspace_id": body.workspace_id,
            "principal_id": actor["principal"]["principal_id"],
            "key": key,
            "value": body.value,
            "updated_at": _utc_now_iso(),
        }
    )
    return {"key": key, "saved": True}


# ---------------------------------------------------------------------------
# Feedback（帮助与反馈，P2-4）
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    email: str | None = Field(None, max_length=254)
    message: str = Field(..., min_length=1, max_length=4000)
    workspace_id: str | None = None


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest, actor: dict = Depends(_get_actor)):
    # 审计修复：workspace_id 提供时必须与令牌一致，防跨租户挂账
    actor_ws = actor.get("workspace", {}).get("workspace_id")
    if body.workspace_id and body.workspace_id != actor_ws:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    db = get_db()
    feedback_id = f"fb_{uuid.uuid4().hex[:16]}"
    db.insert_feedback(
        {
            "feedback_id": feedback_id,
            "email": body.email or actor["principal"].get("email"),
            "workspace_id": body.workspace_id or actor_ws,
            "message": body.message.strip(),
            "created_at": _utc_now_iso(),
        }
    )
    # SMTP 配置存在时转发给运营邮箱（best-effort）
    feedback_to = os.getenv("FEEDBACK_TO")
    from services.email_sender import smtp_configured

    if feedback_to and smtp_configured():
        try:
            from services.email_sender import send_email

            send_email(
                to=feedback_to,
                subject=f"[用户反馈] {actor['principal'].get('email') or 'anonymous'}",
                body=body.message.strip(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("feedback email forward skipped: %s", exc)
    return {"feedback_id": feedback_id, "received": True}


# ---------------------------------------------------------------------------
# Audit（审计 UI，P2-5；只读，仅 owner/admin）
# ---------------------------------------------------------------------------


@router.get("/audit")
def list_audit(
    workspace_id: str,
    limit: int = Query(200, ge=1, le=500),
    actor: dict = Depends(_get_actor),
):
    _assert_workspace(actor, workspace_id)
    if actor["membership"]["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can view audit logs")
    rows = get_db().fetch_audit_logs(workspace_id=workspace_id, limit=limit)
    # 只返回摘要字段，不透出 detail_json 明细（可能含敏感内容）
    return {
        "items": [
            {
                "audit_id": row["audit_id"],
                "actor_principal_id": row["actor_principal_id"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    }
