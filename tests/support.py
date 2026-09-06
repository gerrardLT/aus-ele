import os
import sys
import types

_TEST_ENV_LOADED = False


def stub_optional_dep(name: str, **attrs):
    """Inject a stand-in module for *name* **only when the real package is absent**.

    为什么需要这个函数（2026-09-05 R0 基线定位）：28 个测试文件里写着

        sys.modules.setdefault("pulp", types.SimpleNamespace())

    而 ``setdefault`` 判的是「键是否已在 sys.modules 里」，不是「包是否装了」。
    在 ``python -m unittest discover`` 单进程跑全量时，第一个执行的测试文件会在
    ``pulp`` 尚未被导入的瞬间插入桩 → 此后整个进程内 ``import pulp`` 永远拿到
    ``SimpleNamespace``，于是真实引擎全线崩塌（观测到 24+12+8+6 例
    ``'SimpleNamespace' object has no attribute 'LpProblem'/'pv'/'npv'``）。
    这些红项与被测代码无关，纯粹是测试基建互相投毒。

    本函数先用 ``importlib.util.find_spec`` 判断真实可得性：可得 → 什么都不做
    （让正常 import 生效）；不可得 → 才注入桩，并支持显式补齐属性。
    """
    if name in sys.modules:
        return sys.modules[name]
    import importlib.util

    try:
        available = importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        available = False
    if available:
        return None
    stub = types.SimpleNamespace(**attrs)
    sys.modules[name] = stub
    return stub


def load_test_env():
    """Load the repo ``.env`` into ``os.environ`` without overriding existing vars.

    Backend tests need PostgreSQL connection settings (``AUS_ELE_PG_*``). Locally
    these live in ``.env``, which the test runner does not auto-load; CI provides
    them explicitly and ships no ``.env`` file, so this is a no-op there. A minimal
    parser is used to avoid a hard dependency on ``python-dotenv``. Idempotent.
    """
    global _TEST_ENV_LOADED
    if _TEST_ENV_LOADED:
        return
    _TEST_ENV_LOADED = True
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def ensure_repo_import_paths():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for relative_path in ("backend", "scrapers"):
        path = os.path.join(repo_root, relative_path)
        if path not in sys.path:
            sys.path.insert(0, path)
    load_test_env()


def reset_pg_tables(db, *table_names):
    """TRUNCATE the named tables (``RESTART IDENTITY CASCADE``) if they exist.

    Every ``DatabaseManager`` shares a single PostgreSQL database (``db_path`` is
    ignored and the connection always targets ``AUS_ELE_PG_DATABASE``), so rows
    seeded by a previous test run leak into the next and break count/usage
    assertions. Tests call this in ``setUp`` to start from a clean slate. Missing
    tables are skipped. Works under both ``unittest`` and ``pytest``.
    """
    if not table_names:
        return
    with db.get_connection() as conn:
        cur = conn.cursor()
        for table in table_names:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            if cur.fetchone() is not None:
                cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
        conn.commit()


# RBAC / 认证链路的全部表（子表在前，CASCADE 才不会留下悬空行）
ACCESS_CONTROL_TABLES = (
    "email_verification",  # R1.1：引用 principal，必须在父表之前
    # R1.7（2026-09-06）：导出记录里存着 artifact 绝对路径、删除记录存着排期时间，
    # 两者都按 principal_id 收敛。不清会让「最近一次导出」断言数到上一轮的行，
    # 也会让「已有待执行删除请求」的 409 分支在第二次运行时假绿。
    "account_data_export",
    "account_deletion_request",
    "audit_log",
    "access_token",
    "auth_session",
    "auth_identity",
    "workspace_membership",
    "organization_membership",
    "workspace_invite",
    "membership_invite",
    "organization_domain",
    "oidc_provider",
    "principal_identity",
    "workspace",
    "organization",
)


def reset_access_control_tables(db):
    """清空 RBAC/认证表，让访问控制类测试从确定状态起跑。

    动机（2026-09-05 R0 基线定位，第三类根因）：``DatabaseManager`` 为 PG-only 且
    所有测试**共享同一个库**，而 ``test_access_control.py`` / ``test_oidc_auth.py``
    用的是硬编码邮箱（``owner@example.com`` 等）→ 第二次运行必撞
    ``principal_identity_email_key``；``fetch_audit_logs()`` 的计数断言还会数到历史
    残留（观测到 ``100 != 1``）。这些红项与被测代码无关。

    只清认证/RBAC 表，不动行情与分析数据；bootstrap 身份由
    ``auth_routes._ensure_bootstrap_identity`` 惰性重建，因此清库不影响匿名体验。
    """
    reset_pg_tables(db, *ACCESS_CONTROL_TABLES)


# 任务队列 + 其事件日志。子表在前，CASCADE 才不会留下悬空行。
JOB_STATE_TABLES = (
    "job_event_log",
    "job_run",
)


def reset_job_tables(db):
    """清空任务队列表，让队列类测试从确定状态起跑。

    动机（2026-09-06 R0b 定位，第四类根因 —— 与认证表同源但机制不同）：
    ``JobOrchestrator.run_once()`` 认领的是**库里任何** status='queued' 的任务，
    不区分是谁入队的。PG-only 共享库下，上一轮运行残留的 queued 任务会被下一轮的
    ``run_once()`` 认领，而该测试的 ``JobRegistry`` 只注册了自己的 job_type →
    ``KeyError: Unsupported job_type: report_generate``；``test_run_once_can_be_restricted_
    to_specific_queue_names`` 则拿到别人的 ``job_id`` 而断言不等。观测到 11 例红，
    全部与被测代码无关。

    只清队列与其事件日志；行情/分析数据（``trading_price_*``、``fingrid_timeseries``、
    ``predispatch_*`` 等）是真实种子数据，绝不可清。
    """
    reset_pg_tables(db, *JOB_STATE_TABLES)


def offline_state_store():
    """构造一个永远走进程内回落的 ``SharedStateStore``（P0.7 测试确定性用）。

    不连 Redis：否则「本机有没有起 Redis」会改变限流语义，测试变成环境依赖，
    而且在共享 Redis 上互相污染计数窗口。
    """
    from shared_state import SharedStateStore

    class _OfflineCache:
        prefix = "test_offline"

        def _get_client(self):
            return None

        def _record_failure(self):
            pass

        def _full_key(self, scope, key):
            return f"{scope}:{key}"

        def get_json(self, scope, key):
            return None

        def set_json(self, scope, key, value, ttl_seconds):
            pass

    return SharedStateStore(cache=_OfflineCache())

