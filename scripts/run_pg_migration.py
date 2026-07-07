#!/usr/bin/env python3
"""
One-click SQLite to PostgreSQL migration runner.

Starts the PostgreSQL container, waits for it to be healthy,
then runs the data migration script.

Usage:
    python scripts/run_pg_migration.py [--prod] [--dry-run]

Options:
    --prod      Use docker-compose.prod.yml instead of docker-compose.yml
    --dry-run   Show migration plan without executing

Requirements: docker compose must be available on PATH.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time


def run_cmd(cmd: list[str], check: bool = True, env: dict | None = None) -> int:
    """Run a command and return exit code."""
    merged_env = {**os.environ, **(env or {})}
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, env=merged_env)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result.returncode


def wait_for_pg(host: str, port: int, timeout: int = 60) -> bool:
    """Wait for PostgreSQL to become available."""
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(2)
            print("  Waiting for PostgreSQL...", flush=True)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite to PostgreSQL migration runner")
    parser.add_argument("--prod", action="store_true", help="Use docker-compose.prod.yml")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--skip-docker", action="store_true", help="Skip docker compose (PG already running)")
    args = parser.parse_args()

    # Load .env
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(repo_root, ".env.prod" if args.prod else ".env")

    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    pg_host = os.environ.get("AUS_ELE_PG_HOST", "localhost")
    pg_port = int(os.environ.get("AUS_ELE_PG_PORT", "5432"))
    pg_db = os.environ.get("AUS_ELE_PG_DATABASE", "aemo_data")
    pg_user = os.environ.get("AUS_ELE_PG_USER", "aemo")
    pg_pass = os.environ.get("AUS_ELE_PG_PASSWORD", "")

    if not pg_pass:
        print("ERROR: AUS_ELE_PG_PASSWORD not set. Add it to .env or .env.prod")
        return 1

    # Docker compose file
    compose_file = "docker-compose.prod.yml" if args.prod else "docker-compose.yml"
    compose_cmd = ["docker", "compose", "-f", compose_file]

    print("=" * 60)
    print("SQLite -> PostgreSQL Migration")
    print("=" * 60)
    print(f"  Compose file: {compose_file}")
    print(f"  PG Host:      {pg_host}:{pg_port}")
    print(f"  PG Database:  {pg_db}")
    print(f"  PG User:      {pg_user}")
    print(f"  Dry run:      {args.dry_run}")
    print(f"  Skip docker:  {args.skip_docker}")

    # Step 1: Start PostgreSQL container
    if not args.skip_docker:
        print("\n--- Step 1: Starting PostgreSQL container ---")
        run_cmd(compose_cmd + ["up", "-d", "postgres"])

        # Use the host-mapped port for health check
        host_port = int(os.environ.get("PG_HOST_PORT", "15432"))
        print(f"\n--- Step 2: Waiting for PostgreSQL (localhost:{host_port}) ---")
        if not wait_for_pg("localhost", host_port, timeout=60):
            print("ERROR: PostgreSQL did not become ready in 60 seconds")
            return 1
        print("PostgreSQL is ready!")
    else:
        print("\n--- Skipping Docker (PG already running) ---")

    # Step 3: Run migration
    print("\n--- Step 3: Running data migration ---")
    source_db = os.path.join(repo_root, "data", "aemo_data.db")
    if not os.path.exists(source_db):
        print(f"ERROR: Source database not found: {source_db}")
        return 1

    dsn = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    migration_cmd = [
        sys.executable,
        os.path.join(repo_root, "scripts", "migrate_sqlite_to_pg.py"),
        "--source-db", source_db,
        "--target-dsn", dsn,
        "--batch-size", "5000",
    ]
    if args.dry_run:
        migration_cmd.append("--dry-run")

    exit_code = run_cmd(migration_cmd, check=False)
    if exit_code != 0:
        print(f"\nMigration failed with exit code {exit_code}")
        return 1

    # Step 4: Restart services
    if not args.skip_docker and not args.dry_run:
        print("\n--- Step 4: Restarting all services ---")
        run_cmd(compose_cmd + ["up", "-d"])
        print("\nAll services restarted!")

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Check logs: docker compose logs backend")
    print("  2. Verify API: curl http://localhost:18085/api/health")
    print("  3. Open browser: http://localhost:18080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
