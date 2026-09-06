"""账户数据权利服务（R1.7，2026-09-06）：自助导出 + 软删除 + 30 天宽限。

对应 Spec 批次 R1 第 7 项。三件事各自的设计理由：

1. **导出是白名单，不是 ``SELECT *``**。账户能拿走的必须是「自己的数据」，且绝不能顺手
   把凭据带走。库里有多张表直接存着**活的**登录凭据：``auth_session.session_token``、
   ``access_token.token``（未过期且未撤销时就是一枚可用的 JWT）、
   ``email_verification.token_hash`` / ``password_reset.token_hash``（离线可猜的短令牌
   哈希）、``membership_invite.invite_token``（拿它就能加入别人的组织）、
   ``external_api_client.api_key``。一个「导出你的一切」端点若按 ``*`` 实现，等于把
   这些串通过一条新的 HTTPS 响应递给（可能已经被他人拿到会话的）调用方，并且在下载的
   JSON 文件里长期留存 —— 落地在磁盘上的凭据比在线凭据危险得多。
   所以下面 ``EXPORT_SCOPE`` 的每一项都显式写 ``exclude``，且**默认拒绝未知表**：
   新增表不会自动进导出，必须有人显式判断它算不算用户数据。

2. **删除是软删除 + 宽限期，宽限期内可撤销**。理由与 Google 账户删除同构：误触发的
   不可逆操作需要一个反悔窗口。区别在于本模块**立即撤销全部会话与令牌** —— 因为「我已
   要求删除我的数据」与「这个会话还能继续读取我的数据」不能同时为真；而允许重新登录是
   故意的（撤销删除请求只能靠登录后点取消，登录不了就等于没有宽限期）。

3. **owner 必须先移交组织**。``principal_identity`` 行被物理删除后，``organization`` 会
   留下一个没有任何成员的孤儿组织：既没人能管理它，也没有人能删除它。所以只有在申请人
   不再是任何「还有别的活跃成员」组织的所有者时才放行；只剩自己一个人的组织可以直接删
   （连带把该组织自己的 workspace 行交给 purge 处理）。

宽限天数登记在 ``data/assumptions_registry.json``（受 AGENTS.md 假设登记纪律约束）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

# GDPR Art.17 / 澳洲 APP 侧的通行做法：给一个明确、可解释的反悔窗口。
# 改这个值必须同步改隐私页第 5 条（web/src/lib/dataRights.js 写死了「30 天」）。
DEFAULT_GRACE_DAYS = 30

# 导出中必须剔除的列名（跨表同名统一处理，见 EXPORT_SCOPE）。
# 分成两类是因为它们的风险机制不同，注释里说清楚，避免后人「顺手放行」其中一类。
CREDENTIAL_COLUMNS = frozenset(
    {
        "session_token",  # 活的续期凭据
        "token",  # access_token.token = 未过期即可用的 JWT
        "token_hash",  # 邮箱验证 / 密码重置的一次性令牌哈希
        "invite_token",  # 组织/工作空间邀请凭据
        "api_key",  # 外部 API 凭据
        "verification_token",  # 域名验证 TXT 值
        "password_hash",  # 即使已加盐迭代，也不该出现在用户的下载文件里
        "password_salt",
        "pw_iters",
    }
)

# 导出中必须剔除的内部列。``artifact_path`` 是服务端绝对路径：下载端点自己都拒绝直接
# 信任库里的这个值（见 routes/data_rights_routes.py 里的「路径不受信」分支），把同一个值
# 写进用户下载的 JSON 等于一边防路径穿越一边把它公布出去。而且它对用户毫无意义 ——
# 拿不到文件系统的人看到路径只会以为那是一个可以打开的链接。
#
# 这里同时删掉了上一版的一个 ``ORG_ONLY_COLUMNS``：它声明「organization_id / workspace_id
# 全部排除」，但没有任何代码引用它，而导出文件里实际带着这两列。一个读起来像安全控制、
# 实际什么都不做的常量，比没有这个常量更危险。
INTERNAL_COLUMNS = frozenset({"artifact_path"})

EXCLUDED_EXPORT_COLUMNS = CREDENTIAL_COLUMNS | INTERNAL_COLUMNS

# 导出范围：(表名, 该表里指向申请人的列, 章节名)。
# 章节名用 snake_case 而不是表名，是为了在前端与下载文件里稳定 —— 表以后拆分或改名时
# 用户看到的结构不必跟着变。
EXPORT_SCOPE: tuple[tuple[str, str, str], ...] = (
    ("principal_identity", "principal_id", "account"),
    ("auth_identity", "principal_id", "linked_identities"),
    ("auth_session", "principal_id", "sessions"),
    ("access_token", "principal_id", "access_tokens"),
    ("user_preference", "principal_id", "preferences"),
    ("email_verification", "principal_id", "email_verification_challenges"),
    ("password_reset", "principal_id", "password_resets"),
    ("organization_membership", "principal_id", "organization_memberships"),
    ("workspace_membership", "principal_id", "workspace_memberships"),
    ("membership_invite", "accepted_by_principal_id", "accepted_invites"),
    ("membership_invite", "invited_by_principal_id", "invites_sent_by_me"),
    ("workspace_invite", "invited_by_principal_id", "workspace_invites_sent_by_me"),
    ("agent_execution_log", "principal_id", "agent_queries"),
    ("notification", "principal_id", "notifications"),
    ("report_subscription", "principal_id", "report_subscriptions"),
    ("saved_report", "created_by", "saved_reports"),
    ("audit_log", "actor_principal_id", "audit_trail"),
    # R1.7 自身的两张流水表也属于「关于这个人的数据」：导出历史与删除排期都是用户行使权
    # 利的记录，权利主体有权拿回。它们在 purge 时也一并删除（由 PURGE_TARGETS 派生保证）。
    # 注意自指：本次导出的那一行会以它被读取时的状态（running）出现在文件里，因为状态是
    # 写完 artifact 之后才更新的 —— 这是诚实的快照，不是 bug。
    ("account_data_export", "principal_id", "export_requests"),
    ("account_deletion_request", "principal_id", "deletion_requests"),
)

# purge 时要物理删除的 (表, 列) —— 直接由 EXPORT_SCOPE 派生，避免两份清单分叉：
# 「能导出的」与「会被删掉的」必须是同一个集合，否则删完还剩下一份没人负责的副本。
PURGE_TARGETS: tuple[tuple[str, str], ...] = tuple((t, c) for t, c, _ in EXPORT_SCOPE)


class DataRightsUnavailable(RuntimeError):
    """基类，方便路由层用一个 except 收口。"""


class DeletionAlreadyPending(DataRightsUnavailable):
    def __init__(self, request: dict):
        super().__init__("该账户已有待执行的删除请求")
        self.request = request


class DeletionBlockedByOwnership(DataRightsUnavailable):
    """申请人仍是「有其它活跃成员」组织的所有者 —— 必须先移交。"""

    def __init__(self, organizations: list[dict]):
        super().__init__("请先将组织所有权移交后再申请删除账户")
        self.organizations = organizations


class ExportNotFound(DataRightsUnavailable):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _select_dicts(conn, sql: str, params=()) -> list[dict]:
    """在本连接上以 dict 行模式跑一条 SELECT。

    ``DatabaseManager`` 默认返回位置元组（仓内既有代码靠 ``row[0]`` 或手写列名映射取值），
    而本模块要整行原样交给用户下载 —— 手写 17 张表的列映射正是最容易漏列的地方，漏掉的
    那一列在导出文件里静默消失，没人会发现。所以统一开 dict 模式取整行。
    """
    conn.row_factory = True
    return [dict(row) for row in conn.execute(sql, params).fetchall()]



# ---------------------------------------------------------------------------
# 表结构（惰性建表，照 database.py 的 ensure_*_table 先例；DDL 只用 TEXT/INTEGER/REAL）
# ---------------------------------------------------------------------------

EXPORT_TABLE = "account_data_export"
DELETION_TABLE = "account_deletion_request"


def ensure_data_rights_tables(db) -> None:
    """建 R1.7 的两张新表。

    为什么不复用 ``job_run`` 存导出状态：作业记录会被 ``reset_job_tables`` 清掉，也会被
    队列保留策略回收，而「我导出过什么」是用户数据权利的一部分，得活到自己的账户被删。
    """
    with db.get_connection() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {EXPORT_TABLE} (
                export_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_id TEXT,
                artifact_path TEXT,
                section_counts_json TEXT,
                completed_at TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DELETION_TABLE} (
                deletion_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                scheduled_delete_at TEXT NOT NULL,
                status TEXT NOT NULL,
                grace_days INTEGER NOT NULL,
                cancelled_at TEXT,
                executed_at TEXT,
                revoke_session_count INTEGER,
                revoke_token_count INTEGER
            )
            """
        )
        conn.commit()


def lake_root_dir() -> str:
    """artifact lake 的根目录（下载端点用它校验路径没有越界）。

    与 ``deps.get_lake`` 读同一个环境变量、同样的缺省值。刻意不直接取 ``get_lake().root_dir``：
    那样会为了拿一个路径而实例化 lake，而 ``get_lake`` 是 lru_cache 单例 —— 测试里一旦在
    改过 ``AUS_ELE_LAKE_ROOT`` 之前先碰过它，路径就会被钉死在旧值上。
    """
    import os
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    return str(Path(os.environ.get("AUS_ELE_LAKE_ROOT", str(repo_root / "data_lake"))).resolve())


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------



def _redacted_columns(db, table: str) -> list[str]:
    """返回该表可导出的列名（剔除凭据/内部列与该表不存在的列）。

    表是白名单（``EXPORT_SCOPE``），列是黑名单 —— 两者方向相反是有意的：新表出现必须显式
    登记才会被导出，而新列默认随表带出。误放行一个凭据列的代价远大于误剔除一个普通列，
    所以黑名单方向只在「按列名统一剔除」这一类风险上生效。
    """
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ? "
            "ORDER BY ordinal_position",
            (table,),
        ).fetchall()
    return [r[0] for r in rows if r[0] not in EXCLUDED_EXPORT_COLUMNS]


def fetch_account_rows(db, principal_id: str) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """按 ``EXPORT_SCOPE`` 逐表取该 principal 的行。

    返回 ``(sections, section_tables)``：章节名 → 行列表，以及章节名 → 来源表（前端下载
    文件里要能看出某段数据来自哪张表，否则出了问题无法向用户解释）。

    单表失败不会让整次导出失败 —— 记 ``error`` 行而不是抛异常。原因：导出是用户行权手段，
    「因为 notification 表有一次瞬时超时所以你拿不到自己的账户资料」是不可接受的；但
    静默少一段同样不可接受，所以缺的那段以显式标记出现。
    """
    sections: dict[str, list[dict]] = {}
    section_tables: dict[str, str] = {}
    for table, column, section in EXPORT_SCOPE:
        section_tables[section] = table
        try:
            columns = _redacted_columns(db, table)
            if not columns:
                sections[section] = [{"_export_status": "table_unavailable"}]
                continue
            projection = ", ".join(f'"{c}"' for c in columns)
            with db.get_connection() as conn:
                rows = conn.execute(
                    f'SELECT {projection} FROM "{table}" WHERE "{column}" = ? '  # noqa: S608 - 列名来自白名单常量
                    "ORDER BY 1",
                    (principal_id,),
                ).fetchall()
            sections[section] = [dict(zip(columns, r, strict=False)) for r in rows]
        except Exception as exc:  # noqa: BLE001 - 见 docstring：单表失败不得拖垮整次导出
            logger.warning("Export section %s failed: %s", section, exc)
            sections[section] = [{"_export_status": "error", "_detail": type(exc).__name__}]
    return sections, section_tables


def build_export_payload(db, principal_id: str) -> dict:
    """组装下载文件的内容（纯 JSON —— ``storage_lake.write_artifact`` 只吃 JSON）。"""
    sections, section_tables = fetch_account_rows(db, principal_id)
    profile = sections.get("account", [{}])[0] if sections.get("account") else {}
    return {
        "schema_version": 1,
        "generated_at": _iso(_utc_now()),
        "subject": {
            "principal_id": principal_id,
            "email": profile.get("email"),
            "display_name": profile.get("display_name"),
        },
        "columns_excluded": sorted(EXCLUDED_EXPORT_COLUMNS),
        "sections": sections,
        "section_source_tables": section_tables,
        "section_counts": {name: len(rows) for name, rows in sections.items()},
    }


def create_export_record(db, *, principal_id: str) -> dict:
    """登记一次导出请求（status=queued），返回行。"""
    ensure_data_rights_tables(db)
    record = {
        "export_id": _new_id("exp"),
        "principal_id": principal_id,
        "requested_at": _iso(_utc_now()),
        "status": "queued",
        "artifact_id": None,
        "artifact_path": None,
        "section_counts_json": None,
        "completed_at": None,
        "error": None,
    }
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO {EXPORT_TABLE} (export_id, principal_id, requested_at, status) "
            "VALUES (?, ?, ?, ?)",
            (record["export_id"], principal_id, record["requested_at"], "queued"),
        )
        conn.commit()
    return record


def run_export_job(db, *, export_id: str, lake=None) -> dict:
    """执行导出：写 artifact 并回写状态。由 job handler 调用，也可直接调（测试/运维）。

    artifact 落在 ``data_lake/`` 的 derived 层，路径由 lake 返回并记在本表里 —— 记路径
    是为了 purge 时能把这个含个人数据的文件一起删掉；不记就会在账户消失后留下一份
    无人认领的完整副本。
    """
    ensure_data_rights_tables(db)
    row = _fetch_row(db, EXPORT_TABLE, "export_id", export_id)
    if row is None:
        raise ExportNotFound(f"export_id {export_id} 不存在")
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE {EXPORT_TABLE} SET status = ? WHERE export_id = ?", ("running", export_id)
        )
        conn.commit()

    try:
        payload = build_export_payload(db, row["principal_id"])
        if lake is None:
            from deps import get_lake

            lake = get_lake()
        artifact = lake.write_artifact(
            layer="derived",
            namespace="account_data_export",
            partition=f"principal_id={row['principal_id']}",
            payload=payload,
            metadata={"principal_id": row["principal_id"], "export_id": export_id},
        )
        result = _update_export(
            db,
            export_id,
            status="completed",
            artifact_id=artifact["artifact_id"],
            artifact_path=artifact["payload_path"],
            section_counts_json=json.dumps(payload["section_counts"]),
            completed_at=_iso(_utc_now()),
        )
        # 只记数量不记内容：日志里出现用户查询文本就等于开了一条绕过 API 的数据出口。
        logger.info("Account export %s completed sections=%s", export_id, payload["section_counts"])
        return result
    except Exception as exc:  # noqa: BLE001 - 作业失败要落到行上，否则用户永远看到 queued
        logger.exception("Account export %s failed", export_id)
        return _update_export(
            db, export_id, status="failed", error=f"{type(exc).__name__}: {exc}"
        )


def _update_export(db, export_id: str, **fields) -> dict:
    assignments = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [export_id]
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE {EXPORT_TABLE} SET {assignments} WHERE export_id = ?", tuple(values)
        )
        conn.commit()
    return _fetch_row(db, EXPORT_TABLE, "export_id", export_id)


def _fetch_row(db, table: str, key_column: str, key_value: str) -> dict | None:
    with db.get_connection() as conn:
        rows = _select_dicts(conn, f'SELECT * FROM "{table}" WHERE "{key_column}" = ?', (key_value,))  # noqa: S608
    return rows[0] if rows else None


def get_export(db, *, principal_id: str, export_id: str | None = None) -> dict | None:
    """取某次导出，或该 principal 最近一次。只能取自己的 —— 由调用方传 principal_id 收敛。"""
    ensure_data_rights_tables(db)
    with db.get_connection() as conn:
        if export_id:
            rows = _select_dicts(
                conn,
                f"SELECT * FROM {EXPORT_TABLE} WHERE export_id = ? AND principal_id = ?",
                (export_id, principal_id),
            )
        else:
            rows = _select_dicts(
                conn,
                f"SELECT * FROM {EXPORT_TABLE} WHERE principal_id = ? "
                "ORDER BY requested_at DESC LIMIT 1",
                (principal_id,),
            )
    return rows[0] if rows else None



# ---------------------------------------------------------------------------
# 删除（软删 → 宽限 → 物理清除）
# ---------------------------------------------------------------------------


def find_owned_organizations_blocking_deletion(db, principal_id: str) -> list[dict]:
    """列出「申请人是 owner 且组织里还有别的活跃成员」的组织。

    活跃成员数按 ``organization_membership.status = 'active'`` 计，且排除申请人自己 ——
    只剩申请人一人的组织不算阻塞：删掉它不会留下孤儿。
    """
    with db.get_connection() as conn:
        rows = _select_dicts(
            conn,
            f"""
            SELECT om.organization_id, o.name,
                   (SELECT COUNT(*) FROM {db.ORGANIZATION_MEMBERSHIP_TABLE} other
                     WHERE other.organization_id = om.organization_id
                       AND other.status = 'active'
                       AND other.principal_id <> om.principal_id) AS other_active_members
              FROM {db.ORGANIZATION_MEMBERSHIP_TABLE} om
              JOIN organization o ON o.organization_id = om.organization_id
             WHERE om.principal_id = ? AND om.role = 'org_owner' AND om.status = 'active'
            """,
            (principal_id,),
        )
    blocking = []
    for row in rows:
        if int(row.get("other_active_members") or 0) > 0:
            blocking.append(
                {
                    "organization_id": row["organization_id"],
                    "name": row.get("name"),
                    "other_active_members": int(row["other_active_members"]),
                }
            )
    return blocking



def request_account_deletion(db, *, principal_id: str, grace_days: int = DEFAULT_GRACE_DAYS) -> dict:
    """受理删除请求：立即撤销全部会话与令牌，并排定宽限期后的物理清除。"""
    if grace_days < 1:
        # 宽限期 <1 天等于「可撤销」只是纸面承诺 —— 一次网络抖动就能让它不可逆。
        # 与其静默按 0 处理，不如拒绝：这个参数来自配置，配错要在部署期炸出来。
        raise ValueError("grace_days 必须 >= 1")
    ensure_data_rights_tables(db)
    existing = get_deletion_request(db, principal_id=principal_id)
    if existing and existing["status"] == "pending":
        raise DeletionAlreadyPending(existing)

    blocking = find_owned_organizations_blocking_deletion(db, principal_id)
    if blocking:
        raise DeletionBlockedByOwnership(blocking)

    now = _utc_now()
    session_count = db.revoke_auth_sessions_by_principal(principal_id)
    token_count = db.revoke_access_tokens_by_principal(principal_id)
    record = {
        "deletion_id": _new_id("del"),
        "principal_id": principal_id,
        "requested_at": _iso(now),
        "scheduled_delete_at": _iso(now + timedelta(days=grace_days)),
        "status": "pending",
        "grace_days": grace_days,
        "cancelled_at": None,
        "executed_at": None,
        "revoke_session_count": session_count,
        "revoke_token_count": token_count,
    }
    with db.get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO {DELETION_TABLE} (deletion_id, principal_id, requested_at,
                scheduled_delete_at, status, grace_days, revoke_session_count, revoke_token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["deletion_id"],
                principal_id,
                record["requested_at"],
                record["scheduled_delete_at"],
                "pending",
                grace_days,
                session_count,
                token_count,
            ),
        )
        conn.commit()
    from access_control import _write_audit

    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="account.deletion_requested",
        target_type="principal",
        target_id=principal_id,
        detail_json={
            "scheduled_delete_at": record["scheduled_delete_at"],
            "grace_days": grace_days,
            "revoked_sessions": session_count,
            "revoked_tokens": token_count,
        },
    )
    return record


def get_deletion_request(db, *, principal_id: str) -> dict | None:
    ensure_data_rights_tables(db)
    with db.get_connection() as conn:
        rows = _select_dicts(
            conn,
            f"SELECT * FROM {DELETION_TABLE} WHERE principal_id = ? "
            "ORDER BY requested_at DESC LIMIT 1",
            (principal_id,),
        )
    return rows[0] if rows else None



def cancel_account_deletion(db, *, principal_id: str) -> dict:
    """撤销删除请求。幂等语义刻意保留给路由层判断：这里只认 pending。"""
    ensure_data_rights_tables(db)
    row = get_deletion_request(db, principal_id=principal_id)
    if row is None or row["status"] != "pending":
        raise DeletionAlreadyPending(row or {})
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE {DELETION_TABLE} SET status = ?, cancelled_at = ? WHERE deletion_id = ?",
            ("cancelled", _iso(_utc_now()), row["deletion_id"]),
        )
        conn.commit()
    from access_control import _write_audit

    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="account.deletion_cancelled",
        target_type="principal",
        target_id=principal_id,
        detail_json={"deletion_id": row["deletion_id"]},
    )
    return _fetch_row(db, DELETION_TABLE, "deletion_id", row["deletion_id"])


def list_due_deletions(db, *, now: datetime | None = None) -> list[dict]:
    ensure_data_rights_tables(db)
    moment = _iso(now or _utc_now())
    with db.get_connection() as conn:
        return _select_dicts(
            conn,
            f"SELECT * FROM {DELETION_TABLE} WHERE status = ? AND scheduled_delete_at <= ? "
            "ORDER BY scheduled_delete_at",
            ("pending", moment),
        )



def purge_account(db, *, principal_id: str) -> dict[str, int]:
    """物理清除该 principal 的行。

    顺序：先子表后 ``principal_identity``。库里没有 FK（``ensure_*`` 建表时不带
    REFERENCES），所以 CASCADE 靠不住，必须自己按 PURGE_TARGETS 逐张删 —— 这也是
    PURGE_TARGETS 必须由 EXPORT_SCOPE 派生的原因：漏一张就是一个删不干净的账户。
    """
    ensure_data_rights_tables(db)
    deleted: dict[str, int] = {}
    with db.get_connection() as conn:
        for table, column in PURGE_TARGETS:
            if table == "principal_identity":
                continue  # 最后单独删，见 docstring
            cur = conn.execute(f'DELETE FROM "{table}" WHERE "{column}" = ?', (principal_id,))
            deleted[table] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        # 导出产物文件也要删：它本身就是一次完整导出，留着等于删除失败。
        lake_rows = conn.execute(
            f"SELECT export_id, artifact_path FROM {EXPORT_TABLE} WHERE principal_id = ?",
            (principal_id,),
        ).fetchall()
        conn.execute(f"DELETE FROM {EXPORT_TABLE} WHERE principal_id = ?", (principal_id,))
        conn.execute(f"DELETE FROM {DELETION_TABLE} WHERE principal_id = ?", (principal_id,))
        cur = conn.execute(
            "DELETE FROM principal_identity WHERE principal_id = ?", (principal_id,)
        )
        deleted["principal_identity"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()
    for _export_id, path in lake_rows:
        _unlink_artifact(path)
    return deleted


def _unlink_artifact(path: str | None) -> None:
    if not path:
        return
    from pathlib import Path

    try:
        Path(path).unlink(missing_ok=True)
        # 同名 .meta.json 是 lake 写的第二份文件，漏掉它就留下一份带 principal_id 的墓碑。
        Path(path).with_name(Path(path).stem + ".meta.json").unlink(missing_ok=True)
    except OSError as exc:  # noqa: BLE001 - 文件删不掉不该回滚数据库删除
        logger.warning("Failed to unlink export artifact %s: %s", path, exc)


def execute_due_deletions(db, *, now: datetime | None = None) -> list[dict]:
    """把宽限期已过的请求真正执行掉。由周期作业调用，也可手工跑。"""
    results = []
    for row in list_due_deletions(db, now=now):
        principal_id = row["principal_id"]
        try:
            deleted = purge_account(db, principal_id=principal_id)
            # 删除请求行本身也已被 purge_account 清掉，所以审计流水是唯一的执行凭证 ——
            # 少了它，「这个人到底删没删」在库里就查无实据。
            from access_control import _write_audit

            _write_audit(
                db,
                actor_principal_id=None,
                action="account.deletion_executed",
                target_type="principal",
                target_id=principal_id,
                detail_json={"deletion_id": row["deletion_id"], "deleted_rows": deleted},
            )
            results.append({"principal_id": principal_id, "status": "executed", "deleted": deleted})
        except Exception as exc:  # noqa: BLE001 - 单个账户失败不得中断整轮清除
            logger.exception("Purge failed for %s", principal_id)
            results.append({"principal_id": principal_id, "status": "failed", "error": str(exc)})
    return results
