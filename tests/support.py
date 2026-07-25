import os
import sys

_TEST_ENV_LOADED = False


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
