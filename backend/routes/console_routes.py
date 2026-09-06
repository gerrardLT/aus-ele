"""公测运营控制台（R5.5，2026-09-06）：激活漏斗、留存与反馈只读指标。

三条来自 Spec §163 的硬约束，逐条决定了这里的形状：

1. **零新表**。所有指标都由既有表（``principal_identity`` / ``agent_execution_log`` /
   ``saved_report`` / ``user_preference`` / ``feedback`` / ``workspace_membership``）的计数
   组合而来。为「看激活率」新建一张聚合表意味着多一条会失真的链路的和一个需要回填的历史，
   而公测期真正要回答的问题（用户注册后有没有跑第一次分析）用现有表一次查询就能回答。
   ``asset_project`` 是 R4 才建的表：它不存在时本模块**不会**把「查不到」报成「零个项目」，
   而是把该数据源标成 ``available: false`` + 值为 ``null``（见 ``_source_availability``）。让 0 冒充真实
   测量结果是运营面板最危险的一类 bug —— 读的人会以为产品零使用。

2. **不加进 ``admin_routes.py``**。那个文件里每个端点都是 ``import server as _server`` 的
   委托，加进来只会继续加深「路由层依赖热文件」这条耦合链（见该文件 docstring）。

3. **只读、可缓存、绝不触发重算**。这里没有任何指标会去调 ``compute_quality_snapshots``
   一类现算函数（同 R6.3 StatusPage 的判据）：控制台是被反复刷新的地方，一次全表扫描
   配上一个手快的运营就足以把读路径拖垮。故所有查询都是计数/取列，且整体有一个进程内
   TTL 缓存。

鉴权：平台侧没有「超级管理员」这个角色（``ROLE_PERMISSIONS`` / ``ORG_ROLE_PERMISSIONS``
都是组织/工作空间内的角色），所以这里不假装存在。用显式运维白名单
``AUS_ELE_CONSOLE_OPERATORS``（逗号分隔的 principal_id 或 email，大小写不敏感）：

* 白名单为空 → 503「未启用」：默认失败关闭，且与「你没权限」可区分，便于排障；
* 已登录但不在白名单 → 403；
* 匿名 bootstrap 身份（``pr_websession``）→ 401/403，永远拿不到全站指标。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from access_control import assert_human_actor
from deps import get_db
from routes.account_routes import _get_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/console", tags=["console"])

ALLOWLIST_ENV = "AUS_ELE_CONSOLE_OPERATORS"

# 指标全是聚合计数，60s 的陈旧对运营判断无影响，却能挡住「刷新十次 = 十次全站扫描」。
# 做进程内而非 Redis：这是只读展示数据，没有跨 worker 一致性要求（不像限流计数必须全局），
# 而多个 worker 各自最多旧 60s 完全可接受 —— 反过来，把它塞进共享缓存要额外约定 key 形状，
# 收益只有省几次 COUNT(*)。
_METRICS_TTL_SECONDS = 60.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}

# 数据源清单：name -> (table, 说明)。缺表不是错误，但必须被看见。
_DATA_SOURCES = {
    "accounts": ("principal_identity", "注册账户与邮箱验证状态"),
    "agent_runs": ("agent_execution_log", "天枢运行记录（激活的核心判据）"),
    "saved_reports": ("saved_report", "保存的分析报告"),
    "preferences": ("user_preference", "用户偏好写入（含引导进度）"),
    "feedback": ("feedback", "站内反馈"),
    "memberships": ("workspace_membership", "成员关系"),
    "projects": ("asset_project", "投资项目库（R4 建表，未到则记 null）"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cutoff(days: int) -> str:
    return _iso(_utc_now() - timedelta(days=days))


def _table_exists(conn, table: str) -> bool:
    conn.row_factory = True
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = ?",
        (table,),
    ).fetchone()
    return bool(row)


def _operator_allowlist() -> set[str]:
    raw = os.environ.get(ALLOWLIST_ENV) or ""
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _require_console_operator(actor: dict = Depends(_get_actor)) -> dict:
    """控制台读权限：人类身份 + 在运维白名单里。白名单未配置时报 503 而不是放行。"""
    assert_human_actor(actor, action="console.access_denied")
    allowlist = _operator_allowlist()
    if not allowlist:
        raise HTTPException(
            status_code=503,
            detail=f"{ALLOWLIST_ENV} is not configured; console metrics are disabled",
        )
    principal = actor.get("principal") or {}
    identities = {
        str(principal.get("principal_id") or "").lower(),
        str(principal.get("email") or "").lower(),
    }
    if not (identities & allowlist):
        raise HTTPException(status_code=403, detail="Not a console operator")
    return actor


def _scalar(conn, sql: str, params: tuple = (), default: Any = None) -> Any:
    try:
        row = conn.execute(sql, params).fetchone()
    except Exception as exc:  # noqa: BLE001 - 单个指标失败不能让整个控制台 500
        logger.warning("Console metric query failed (%s): %s", sql.split()[0:4], exc)
        return default
    return row[0] if row else default


def _rows(conn, sql: str, params: tuple = (), default: Any = None) -> Any:
    """``_scalar`` 的多行版：查询失败时回 ``default``（默认 None），让上层把该项标成不可用。

    口径必须和 ``_scalar`` 一致，否则「一个指标挂了」在两条代码路径上表现不同：一条静默
    降级、一条 500，而 500 的那条会让人以为控制台整个坏了去重启服务。
    """
    try:
        return list(conn.execute(sql, params).fetchall())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Console cohort query failed (%s): %s", sql.split()[0:4], exc)
        return default


def _activation_funnel(db, cutoff: str) -> tuple[list[dict], dict[str, Any]]:
    """注册 → 验证 → 首次天枢运行 → 第二次回来 → 留存动作（存报告 / 设偏好）。

    **整条漏斗都按「窗口内注册的同期群」算**，不是全量账户：混着算会得到一个随账户基数
    增长而自动下滑的激活率，读的人会以为产品在退步，而真相只是老账户在分母里越积越多。
    全量账户数另外放在 ``accounts.total_all_time``。

    每一级给出 ``of_total`` 与 ``of_previous`` 两个比率：只看 of_total 会把「注册后没验证」
    和「验证了但没跑分析」混成一个数字，而这两件事要采取的动作完全不同（前者改邮件链路，
    后者改新手引导）。
    """
    with db.get_connection() as conn:
        conn.row_factory = True
        counts = {
            "accounts_total_all_time": _scalar(conn, "SELECT COUNT(*) FROM principal_identity", default=0),
            "signed_up_in_window": _scalar(
                conn, "SELECT COUNT(*) FROM principal_identity WHERE created_at >= ?", (cutoff,), default=0
            ),
            "email_verified_in_window": _scalar(
                conn,
                "SELECT COUNT(*) FROM principal_identity WHERE created_at >= ? AND email_verified_at IS NOT NULL",
                (cutoff,),
                default=0,
            ),
        }
        runs_available = _table_exists(conn, "agent_execution_log")
        counts["agent_runs_available"] = runs_available
        cohort_runs = (
            "FROM agent_execution_log a JOIN principal_identity p ON p.principal_id = a.principal_id "
            "WHERE p.created_at >= ? AND a.principal_id IS NOT NULL"
        )
        if runs_available:
            counts["first_run_in_window"] = _scalar(
                conn, f"SELECT COUNT(DISTINCT a.principal_id) {cohort_runs}", (cutoff,), default=0
            )
            # 「回来过」= 同期群里跑过 ≥2 次的人。按人去重而不是按次数：一个人跑 50 次和
            # 50 个人各跑 1 次在总次数上一样，但只有后者算激活。
            counts["repeat_run_in_window"] = _scalar(
                conn,
                f"SELECT COUNT(*) FROM (SELECT a.principal_id {cohort_runs} "
                "GROUP BY a.principal_id HAVING COUNT(*) > 1) returned",
                (cutoff,),
                default=0,
            )
        else:
            counts["first_run_in_window"] = None
            counts["repeat_run_in_window"] = None

        kept_rows = _scalar(
            conn,
            "SELECT COUNT(DISTINCT p.principal_id) FROM principal_identity p "
            "WHERE p.created_at >= ? AND ( "
            "  EXISTS (SELECT 1 FROM saved_report r WHERE r.created_by = p.principal_id) "
            "  OR EXISTS (SELECT 1 FROM user_preference up WHERE up.principal_id = p.principal_id))",
            (cutoff,),
            default=None,
        )
        counts["kept_artifact_in_window"] = kept_rows

    stages = [
        {"stage": "signed_up", "label_zh": "完成注册", "count": counts["signed_up_in_window"]},
        {"stage": "email_verified", "label_zh": "验证邮箱", "count": counts["email_verified_in_window"]},
        {"stage": "first_agent_run", "label_zh": "跑过一次天枢分析", "count": counts["first_run_in_window"]},
        {"stage": "repeat_run", "label_zh": "第二次回来跑分析", "count": counts["repeat_run_in_window"]},
        {"stage": "kept_artifact", "label_zh": "存下报告或设过偏好", "count": counts["kept_artifact_in_window"]},
    ]
    previous: Optional[int] = None
    total = counts["signed_up_in_window"]
    for stage in stages:
        value = stage["count"]
        stage["of_total"] = round(value / total, 3) if value is not None and total else None
        # 上一级为 None（数据源缺失）或 0 时，本级的转化率必须是 None。把它当成 0 继续算
        # 会得到「0/0」或「跳过一级」的数字，而控制台上的每一个数字都会被当成决策依据。
        stage["of_previous"] = round(value / previous, 3) if value is not None and previous else None
        previous = value
    return stages, counts


def _weekly_cohorts(db, weeks: int) -> dict:
    """按注册周分组，看该周注册的人里有多少在**下一周**还有天枢运行。

    次周回访是公测期最该盯的单一指标：它比 DAU 更难被一次运营拉新冲淡，而「有没有人第二周
    还来」直接决定这个产品是工具还是一次性报告。
    """
    with db.get_connection() as conn:
        conn.row_factory = True
        if not _table_exists(conn, "agent_execution_log"):
            return {"available": False, "cohorts": [], "note": "agent_execution_log 尚未创建"}
        rows = _rows(
            conn,
            "SELECT principal_id, MIN(created_at) AS signed_up_at FROM principal_identity "
            "GROUP BY principal_id HAVING MIN(created_at) >= ?",
            (_cutoff(weeks * 7 + 7),),
            default=None,
        )
        runs = _rows(
            conn,
            # ``created_at::text`` 不是笔误：agent_execution_log.created_at 是 TIMESTAMPTZ
            # （routes/agent_routes.py:710），直接 substr 会被 PG 判成「不存在该签名的函数」。
            "SELECT DISTINCT principal_id, substr(created_at::text, 1, 10) AS day FROM agent_execution_log "
            "WHERE principal_id IS NOT NULL AND created_at >= ?",
            (_cutoff(weeks * 7 + 14),),
            default=None,
        )
    if runs is None or rows is None:
        # 「这一周没人回来」和「那条查询挂了」在面板上必须是两件事：前者改产品，后者修数据链路。
        return {"available": False, "cohorts": [], "note": "周留存查询失败，指标不可用（不是零回访）"}

    run_days: dict[str, set[str]] = {}
    for row in runs:
        run_days.setdefault(row["principal_id"], set()).add(str(row["day"])[:10])

    signups: dict[str, list[str]] = {}
    for row in rows:
        signups.setdefault(_week_key(row["signed_up_at"]), []).append(row["principal_id"])

    out = []
    for cohort_week in sorted(signups):
        next_week = _shift_week(cohort_week, 1)
        members = signups[cohort_week]
        returned = sum(1 for pid in members if _week_key_in(next_week, run_days.get(pid, ())))
        out.append({
            "cohort_week": cohort_week,
            "signups": len(members),
            "returned_next_week": returned,
            "return_rate": round(returned / len(members), 3) if members else None,
        })
    return {"available": True, "cohorts": out[-weeks:], "note": None}


def _week_key(day: str) -> str:
    """ISO 周（``YYYY-Www``）。用 ISO 而不是「第 N 天 ÷ 7」：后者会把同一周的人拆到两个桶里，
    而周留存看板上出现两个半边周就会让人怀疑数据在飘。"""
    try:
        if hasattr(day, "date"):  # TIMESTAMPTZ 列经 psycopg 回来是 datetime，不是 str
            parsed = datetime(day.year, day.month, day.day)
        else:
            parsed = datetime.strptime(str(day)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return "unknown"
    iso = parsed.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _shift_week(week_key: str, delta: int) -> str:
    if week_key == "unknown":
        return "unknown"
    year, _, week = week_key.partition("-W")
    monday = datetime.fromisocalendar(int(year), int(week), 1) + timedelta(weeks=delta)
    iso = monday.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _week_key_in(week_key: str, days) -> bool:
    return any(_week_key(d) == week_key for d in days)


def _engagement(db, days: int) -> dict:
    with db.get_connection() as conn:
        conn.row_factory = True
        cutoff = _cutoff(days)
        if not _table_exists(conn, "agent_execution_log"):
            return {"available": False, "note": "agent_execution_log 尚未创建"}
        runs = _scalar(conn, "SELECT COUNT(*) FROM agent_execution_log WHERE created_at >= ?", (cutoff,), default=0)
        failures = _scalar(
            conn,
            "SELECT COUNT(*) FROM agent_execution_log WHERE created_at >= ? "
            "AND status IS NOT NULL AND status NOT IN ('completed', 'success', 'ok')",
            (cutoff,),
            default=0,
        )
        actors = _scalar(
            conn,
            "SELECT COUNT(DISTINCT principal_id) FROM agent_execution_log WHERE created_at >= ? AND principal_id IS NOT NULL",
            (cutoff,),
            default=0,
        )
        active_days = _scalar(
            conn,
            "SELECT COUNT(DISTINCT substr(created_at::text, 1, 10)) FROM agent_execution_log WHERE created_at >= ?",
            (cutoff,),
            default=0,
        )
        return {
            "available": True,
            "window_days": days,
            # 参与度是**全站窗口量**，和上面那条按同期群算的漏斗刻意不是同一个口径：
            # 「这一周跑了多少次分析」要包含老用户的复购，否则会把活跃产品读成死的。
            # 把 scope 写在响应里，是因为不写的话前端一定会把两个口径的数拼在一起除。
            "scope": "all_accounts_in_window",
            "agent_runs": runs,
            "agent_runs_failed": failures,
            "failure_rate": round(failures / runs, 3) if runs else None,
            "distinct_runners": actors,
            "days_with_activity": active_days,
        }


def _source_availability(db) -> list[dict]:
    with db.get_connection() as conn:
        conn.row_factory = True
        return [
            {
                "name": name,
                "table": table,
                "description": description,
                "available": _table_exists(conn, table),
            }
            for name, (table, description) in _DATA_SOURCES.items()
        ]


def _cached(key: str, producer):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _METRICS_TTL_SECONDS:
            return {**hit[1], "cached": True}
    payload = producer()
    with _cache_lock:
        _cache[key] = (now, payload)
    return {**payload, "cached": False}


@router.get("/activation")
def get_activation_metrics(
    days: int = Query(30, ge=7, le=180),
    weeks: int = Query(8, ge=2, le=26),
    actor: dict = Depends(_require_console_operator),
) -> dict:
    """激活漏斗 + 参与度 + 周留存。只读既有表，零新表（Spec §163）。"""
    return _cached(f"activation:{days}:{weeks}", lambda: _build_activation(get_db(), days, weeks))


def _build_activation(db, days: int, weeks: int) -> dict:
    cutoff = _cutoff(days)
    stages, counts = _activation_funnel(db, cutoff)
    sources = _source_availability(db)
    missing = {s["name"] for s in sources if not s["available"]}
    with db.get_connection() as conn:
        conn.row_factory = True
        pending_deletion = None
        deletion_table_present = _table_exists(conn, "account_deletion")
        if deletion_table_present:
            pending_deletion = _scalar(
                conn, "SELECT COUNT(*) FROM account_deletion WHERE status = 'scheduled'", default=None
            )
        organizations = _scalar(conn, "SELECT COUNT(*) FROM organization", default=0)
        workspaces = _scalar(conn, "SELECT COUNT(*) FROM workspace", default=0)
    engagement = _engagement(db, days)
    retention = _weekly_cohorts(db, weeks)
    return {
        "generated_at": _iso(_utc_now()),
        "window_days": days,
        "window_weeks": weeks,
        "accounts": {
            # ``total`` 是全量基数（要看注册池有多大），``signed_up_in_window`` 才是漏斗分母
            # （要看这一批新用户的激活情况）。两者刻意分开命名：都叫 total 迟早有人拿错分母。
            "total": counts["accounts_total_all_time"],
            "signed_up_in_window": counts["signed_up_in_window"],
            "email_verified_in_window": counts["email_verified_in_window"],
            "organizations": organizations,
            "workspaces": workspaces,
            "pending_deletion": pending_deletion,
        },
        "activation_funnel": stages,
        "engagement": engagement,
        "retention": retention,
        "data_sources": sources,
        "caveats": _caveats(missing, deletion_table_present, engagement, retention),
    }


def _caveats(
    missing: set[str], deletion_table_present: bool, engagement: dict, retention: dict
) -> list[str]:
    """面板上每一个 null 都必须在这里有一句解释。

    「查不到」与「真的是零」在界面上长得一样，而它们的运营含义相反：前者要去建表/接数据，
    后者要去改产品。这一条是 R6.3 StatusPage 同一个判据的复用。
    """
    notes: list[str] = []
    if "projects" in missing:
        notes.append("asset_project 表尚未创建（R4）：项目相关指标为 null，不是零")
    if "agent_runs" in missing:
        notes.append("agent_execution_log 不可用：激活漏斗第 3、4 级为 null，不是零")
    if not deletion_table_present:
        notes.append("account_deletion 表不可用：待删除账户计数为 null")
    if "saved_reports" in missing:
        notes.append("saved_report 表不可用：留存动作一级只看偏好写入")
    notes.append("email_verified_at 列之前的存量账户一律计为未验证，历史验证率偏低是预期的")
    if not engagement.get("available"):
        notes.append("engagement 不可用：窗口内运行量为 null，不是零")
    if not retention.get("available"):
        notes.append(f"周留存不可用：{retention.get('note') or '查询失败'}，不是零回访")
    notes.append(
        "激活漏斗整条按 window_days 内注册的同期群计算（分母是 signed_up_in_window，不是 accounts.total）；"
        "engagement 是全站窗口量，两者口径不同，不可互除"
    )
    return notes


@router.get("/feedback")
def list_recent_feedback(
    limit: int = Query(20, ge=1, le=200),
    actor: dict = Depends(_require_console_operator),
) -> dict:
    """最近的站内反馈（Spec R5「用户反馈第一」的读取侧；写入沿用 POST /api/v1/feedback）。

    反馈正文是说不出手的用户内容，但这里正是给运营看的地方 —— 因此**不做脱敏**，改为
    把「这是 PII、会被审计」写在响应里，并留一条审计日志。
    """
    db = get_db()
    with db.get_connection() as conn:
        conn.row_factory = True
        if not _table_exists(conn, "feedback"):
            return {"items": [], "available": False, "note": "feedback 表尚未创建"}
        rows = conn.execute(
            "SELECT feedback_id, email, workspace_id, message, created_at "
            "FROM feedback ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    principal_id = (actor.get("principal") or {}).get("principal_id")
    _audit_console_read(db, principal_id=principal_id, action="console.feedback_read", rows=len(rows))
    return {
        "items": [dict(row) for row in rows],
        "available": True,
        "count": len(rows),
        "pii_notice": "反馈含用户邮箱与原文，读取动作已记入审计日志",
    }


def _audit_console_read(db, *, principal_id: Optional[str], action: str, rows: int) -> None:
    """控制台读敏感数据要留痕：谁能看到全部用户反馈，本身就是一个需要被审计的能力。"""
    try:
        from access_control import _write_audit

        _write_audit(
            db,
            actor_principal_id=principal_id,
            action=action,
            target_type="console",
            target_id="feedback",
            detail_json=str(rows),
        )
    except Exception as exc:  # noqa: BLE001 - 审计写失败不应让已授权的读请求变成 500
        logger.warning("Console audit write failed (%s): %s", action, exc)


@router.get("/sources")
def list_data_sources(actor: dict = Depends(_require_console_operator)) -> dict:
    """数据源可用性清单（排障入口：先确认哪张表不存在，再谈指标为什么是 null）。"""
    return {
        "generated_at": _iso(_utc_now()),
        "sources": _source_availability(get_db()),
    }
