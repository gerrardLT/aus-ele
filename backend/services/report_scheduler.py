"""报告定时订阅投递（P2 报告中心下半场，2026-08-14）。

调度器每日调用 dispatch_due_report_subscriptions：
- monthly 订阅：当天 == day_of_month 时发送上月报告
- weekly 订阅：当天星期 == day_of_week 时发送当月快照
投递优先邮件（SMTP 未配置/失败时降级写站内通知），best-effort 不阻断其余订阅。
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid

logger = logging.getLogger(__name__)

_DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _previous_month(now: datetime.datetime) -> tuple[int, str]:
    first = now.replace(day=1)
    last_month_end = first - datetime.timedelta(days=1)
    return last_month_end.year, f"{last_month_end.month:02d}"


def _is_due(sub: dict, now: datetime.datetime) -> bool:
    frequency = (sub.get("frequency") or "monthly").lower()
    if frequency == "monthly":
        dom = sub.get("day_of_month")
        if dom is None:
            return False
        # 月末钳制：订阅 31 日在 30 天月份于最后一天触发
        import calendar

        last_day = calendar.monthrange(now.year, now.month)[1]
        return now.day == min(int(dom), last_day)
    if frequency == "weekly":
        dow = (sub.get("day_of_week") or "").lower()[:3]
        return dow in _DOW_KEYS and _DOW_KEYS[now.weekday()] == dow
    return False


def _compose_report_email(sub: dict, payload: dict) -> tuple[str, str]:
    title = sub["title"]
    region = sub["region"]
    body_lines = [
        f"订阅报告：{title}",
        f"市场/区域：{sub.get('market', 'NEM')} / {region}",
        f"生成时间：{_utc_now_iso()}",
        "",
        "完整 JSON 载荷：",
        json.dumps(payload, ensure_ascii=False, indent=2)[:20000],
    ]
    return f"[AEMO Intelligence] {title}（{region}）", "\n".join(body_lines)


def dispatch_due_report_subscriptions(db, *, now: datetime.datetime | None = None) -> dict:
    """检查全部启用订阅，到期则生成报告并投递。返回统计。"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stats = {"checked": 0, "due": 0, "sent_email": 0, "degraded_inapp": 0, "failed": 0}
    try:
        subscriptions = db.list_enabled_report_subscriptions()
    except Exception as exc:  # noqa: BLE001 — 表不存在等场景静默退出
        logger.debug("report subscription dispatch skipped: %s", exc)
        return stats

    from reports import generate_report_payload
    from services.email_sender import send_email, smtp_configured

    for sub in subscriptions:
        stats["checked"] += 1
        if not _is_due(sub, now):
            continue
        # 同一天不重复发送（调度器重启/多次触发保护）
        last = (sub.get("last_sent_at") or "")[:10]
        if last == now.strftime("%Y-%m-%d"):
            continue
        stats["due"] += 1
        try:
            year, month = _previous_month(now)
            payload = generate_report_payload(
                db,
                report_type="monthly_market_report",
                year=year,
                region=sub["region"],
                month=month if (sub.get("frequency") or "monthly") == "monthly" else None,
                organization_id=None,
                workspace_id=sub["workspace_id"],
            )
            subject, body = _compose_report_email(sub, payload)
            recipient = sub.get("email")
            delivered = False
            if recipient and smtp_configured():
                result = send_email(to=recipient, subject=subject, body=body)
                delivered = bool(result.get("delivered"))
            if delivered:
                stats["sent_email"] += 1
            else:
                # 降级：写站内通知，避免订阅静默失效
                db.insert_notification(
                    {
                        "notification_id": f"ntf_{uuid.uuid4().hex[:16]}",
                        "workspace_id": sub["workspace_id"],
                        "principal_id": sub["principal_id"],
                        "title": f"订阅报告已生成：{sub['title']}",
                        "body": {
                            "region": sub["region"],
                            "note": "邮件未配置或发送失败，报告已保存到报告中心",
                        },
                        "link": "/reports",
                        "created_at": _utc_now_iso(),
                    }
                )
                stats["degraded_inapp"] += 1
            # 无论渠道均落库一份保存报告（报告中心可查）
            db.insert_saved_report(
                {
                    "report_id": f"rpt_{uuid.uuid4().hex[:16]}",
                    "workspace_id": sub["workspace_id"],
                    "title": f"{sub['title']}（{year}-{month} 自动）",
                    "market": sub.get("market", "NEM"),
                    "region": sub["region"],
                    "year": year,
                    "payload": payload,
                    "created_by": sub["principal_id"],
                    "created_at": _utc_now_iso(),
                }
            )
            db.mark_report_subscription_sent(sub["subscription_id"], _utc_now_iso())
        except Exception as exc:  # noqa: BLE001 — 单条失败不阻断其余
            stats["failed"] += 1
            logger.warning("report subscription dispatch failed (%s): %s", sub.get("subscription_id"), exc)

    if stats["due"]:
        logger.info("report subscription dispatch: %s", stats)
    return stats
