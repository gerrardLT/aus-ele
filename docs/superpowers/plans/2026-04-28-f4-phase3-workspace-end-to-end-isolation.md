# F4 Phase 3 Workspace End-to-End Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce workspace isolation as a system invariant across query paths, cache keys, derived-data storage, and artifact access so that no tenant-visible result can leak across `organization_id / workspace_id` boundaries.

**Architecture:** Introduce a unified `AccessScope` object at the access-control layer, then thread it into business-query helpers, cache-key construction, and stored derived-data records. Keep workspace policy evaluation centralized and move from route-local checks to service-adjacent scope enforcement while preserving the current repo structure.

**Tech Stack:** FastAPI, SQLite via `DatabaseManager`, RedisResponseCache wrapper, Python `unittest`, existing job/artifact framework, existing external API v1 routes, existing analysis cache and response cache paths

---

## File Structure

### Existing files to modify

- `backend/access_control.py`
  - add `AccessScope` builder and workspace-scope validation helpers
- `backend/database.py`
  - add `organization_id / workspace_id` to tenant-derived storage where missing
  - extend analysis-cache and alert/report helper methods
- `backend/server.py`
  - thread scope into query/cache/storage code paths
  - unify internal and `/api/v1/*` access checks
- `backend/storage_lake.py`
  - ensure artifact metadata carries org/workspace scope and is retrievable by scope
- `backend/job_framework.py`
  - preserve scope metadata through job enqueue, completion, and artifact writing
- `backend/reports.py`
  - preserve workspace scope in generated report payload metadata
- `backend/alerts.py`
  - require workspace scope for alert rule evaluation and state access where tenant-owned

### New files to create

- `tests/test_workspace_scope.py`
  - unit tests for `AccessScope` resolution and policy enforcement
- `tests/test_workspace_cache_isolation.py`
  - tests for response-cache and analysis-cache workspace separation
- `tests/test_workspace_storage_isolation.py`
  - tests for alerts/reports/artifacts/job-derived data scope persistence

### Existing tests to keep green

- `tests/test_workspace_isolation.py`
- `tests/test_external_api_v1.py`
- `tests/test_external_api_v1_routes.py`
- `tests/test_job_framework.py`
- `tests/test_job_queue_routes.py`
- `tests/test_reports_api.py`
- `tests/test_access_control.py`
- `tests/test_access_control_routes.py`

---

### Task 1: Add AccessScope Resolution and Query-Guard Helpers

**Files:**
- Create: `tests/test_workspace_scope.py`
- Modify: `backend/access_control.py`

- [ ] **Step 1: Write the failing AccessScope tests**

```python
import os
import tempfile
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from access_control import (
    build_workspace_access_scope,
    assert_scope_allows_region_market,
    seed_organization,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
)
from database import DatabaseManager


class WorkspaceScopeTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.organization = seed_organization(self.db, name="Acme")
        self.principal = seed_principal(self.db, email="owner@acme.com", display_name="Owner")
        self.workspace = seed_workspace(self.db, organization_id=self.organization["organization_id"], name="Primary")
        seed_workspace_membership(self.db, workspace_id=self.workspace["workspace_id"], principal_id=self.principal["principal_id"], role="owner")
        self.db.upsert_workspace_policy(
            {
                "workspace_id": self.workspace["workspace_id"],
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_build_workspace_access_scope_contains_workspace_policy(self):
        scope = build_workspace_access_scope(
            self.db,
            organization_id=self.organization["organization_id"],
            workspace_id=self.workspace["workspace_id"],
            principal_id=self.principal["principal_id"],
        )
        self.assertEqual(scope["workspace_id"], self.workspace["workspace_id"])
        self.assertIn("NSW1", scope["allowed_regions"])
        self.assertIn("NEM", scope["allowed_markets"])

    def test_assert_scope_allows_region_market_rejects_outside_policy(self):
        scope = build_workspace_access_scope(
            self.db,
            organization_id=self.organization["organization_id"],
            workspace_id=self.workspace["workspace_id"],
            principal_id=self.principal["principal_id"],
        )
        with self.assertRaises(HTTPException) as ctx:
            assert_scope_allows_region_market(scope, region="QLD1", market="NEM")
        self.assertEqual(ctx.exception.status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_scope -v`

Expected: FAIL with missing `build_workspace_access_scope` or `assert_scope_allows_region_market`.

- [ ] **Step 3: Write minimal AccessScope implementation**

```python
# backend/access_control.py

def build_workspace_access_scope(db, *, organization_id: str, workspace_id: str, principal_id: str) -> dict:
    organization = db.fetch_organization(organization_id)
    workspace = db.fetch_workspace(workspace_id)
    principal = db.fetch_principal(principal_id)
    membership = db.fetch_workspace_membership(workspace_id, principal_id)
    policy = db.fetch_workspace_policy(workspace_id) or {
        "allowed_regions_json": [],
        "allowed_markets_json": [],
    }
    if not organization or not workspace or not principal or not membership:
        raise HTTPException(status_code=401, detail="Invalid workspace scope")
    if workspace["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Workspace organization mismatch")
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "principal_id": principal_id,
        "workspace_role": membership["role"],
        "allowed_regions": list(policy.get("allowed_regions_json") or []),
        "allowed_markets": list(policy.get("allowed_markets_json") or []),
    }


def assert_scope_allows_region_market(scope: dict, *, region: str | None = None, market: str | None = None):
    allowed_regions = set(scope.get("allowed_regions") or [])
    allowed_markets = set(scope.get("allowed_markets") or [])
    if region and allowed_regions and region not in allowed_regions:
        raise HTTPException(status_code=403, detail="Workspace access denied for region")
    if market and allowed_markets and market not in allowed_markets:
        raise HTTPException(status_code=403, detail="Workspace access denied for market")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_scope -v`

Expected: PASS with both AccessScope tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/access_control.py tests/test_workspace_scope.py
git commit -m "feat: add workspace access scope helpers"
```

---

### Task 2: Add Workspace Scope to Response-Cache Keys

**Files:**
- Create: `tests/test_workspace_cache_isolation.py`
- Modify: `backend/server.py`

- [ ] **Step 1: Write the failing response-cache isolation tests**

```python
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


class WorkspaceResponseCacheIsolationTests(unittest.TestCase):
    def test_scope_cache_payload_includes_org_and_workspace(self):
        payload = server._scope_cache_payload(
            {
                "year": 2026,
                "region": "NSW1",
            },
            organization_id="org_a",
            workspace_id="ws_a",
        )
        self.assertEqual(payload["organization_id"], "org_a")
        self.assertEqual(payload["workspace_id"], "ws_a")

    def test_same_business_payload_different_workspace_produces_different_cache_key(self):
        payload_a = server._scope_cache_payload({"year": 2026, "region": "NSW1"}, organization_id="org_a", workspace_id="ws_a")
        payload_b = server._scope_cache_payload({"year": 2026, "region": "NSW1"}, organization_id="org_a", workspace_id="ws_b")
        self.assertNotEqual(server._stable_cache_key(payload_a), server._stable_cache_key(payload_b))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_cache_isolation.WorkspaceResponseCacheIsolationTests -v`

Expected: FAIL with missing `_scope_cache_payload`.

- [ ] **Step 3: Write minimal scope-aware cache-payload implementation**

```python
# backend/server.py

def _scope_cache_payload(payload: dict, *, organization_id: str | None, workspace_id: str | None) -> dict:
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        **payload,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_cache_isolation.WorkspaceResponseCacheIsolationTests -v`

Expected: PASS with both response-cache isolation tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/server.py tests/test_workspace_cache_isolation.py
git commit -m "feat: add scope-aware response cache payloads"
```

---

### Task 3: Thread Workspace Scope Through Business Response Caches

**Files:**
- Modify: `backend/server.py`
- Modify: `tests/test_workspace_cache_isolation.py`

- [ ] **Step 1: Write the failing scoped-cache helper tests**

```python
def test_fetch_response_cache_uses_scoped_payload(self):
    payload = server._scope_cache_payload({"region": "NSW1", "year": 2026}, organization_id="org_a", workspace_id="ws_a")
    cache_key = server._stable_cache_key(payload)
    self.assertIn("org_a", str(payload))
    self.assertIn("ws_a", str(payload))
    self.assertTrue(cache_key)

def test_analysis_cache_payload_can_be_scoped(self):
    payload = server._scope_analysis_payload(
        {"region": "NSW1", "backtest_years": [2025, 2026]},
        organization_id="org_a",
        workspace_id="ws_a",
    )
    self.assertEqual(payload["organization_id"], "org_a")
    self.assertEqual(payload["workspace_id"], "ws_a")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_cache_isolation -v`

Expected: FAIL with missing `_scope_analysis_payload`.

- [ ] **Step 3: Write minimal scoped analysis payload implementation and use it in cache paths**

```python
# backend/server.py

def _scope_analysis_payload(payload: dict, *, organization_id: str | None, workspace_id: str | None) -> dict:
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        **payload,
    }

# Example patch shape for existing cache payload creation:
cache_payload = _scope_cache_payload(
    {
        "year": year,
        "region": region,
        "limit": limit,
    },
    organization_id=client.get("organization_id"),
    workspace_id=client.get("workspace_id"),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_cache_isolation -v`

Expected: PASS with scoped payload tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/server.py tests/test_workspace_cache_isolation.py
git commit -m "feat: thread scope through cache payload builders"
```

---

### Task 4: Add Workspace Scope to Analysis Cache Storage

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/server.py`
- Modify: `tests/test_workspace_cache_isolation.py`

- [ ] **Step 1: Write the failing analysis-cache storage tests**

```python
from database import DatabaseManager

def test_analysis_cache_round_trip_preserves_workspace_scope(self):
    db = DatabaseManager(self.db_path)
    db.upsert_analysis_cache(
        scope="investment_response_v2",
        cache_key="key-1",
        data_version="version-1",
        response_payload={"npv": 1},
        organization_id="org_a",
        workspace_id="ws_a",
    )
    row = db.fetch_analysis_cache(
        scope="investment_response_v2",
        cache_key="key-1",
        data_version="version-1",
        organization_id="org_a",
        workspace_id="ws_a",
    )
    self.assertEqual(row["organization_id"], "org_a")
    self.assertEqual(row["workspace_id"], "ws_a")

def test_analysis_cache_lookup_does_not_cross_workspace(self):
    db = DatabaseManager(self.db_path)
    db.upsert_analysis_cache(
        scope="investment_response_v2",
        cache_key="key-1",
        data_version="version-1",
        response_payload={"npv": 1},
        organization_id="org_a",
        workspace_id="ws_a",
    )
    row = db.fetch_analysis_cache(
        scope="investment_response_v2",
        cache_key="key-1",
        data_version="version-1",
        organization_id="org_a",
        workspace_id="ws_b",
    )
    self.assertIsNone(row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_cache_isolation -v`

Expected: FAIL because analysis-cache helpers do not accept or enforce `organization_id` and `workspace_id`.

- [ ] **Step 3: Write minimal analysis-cache scope implementation**

```python
# backend/database.py

def ensure_analysis_cache_table(self, conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.ANALYSIS_CACHE_TABLE} (
            scope TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            data_version TEXT NOT NULL,
            organization_id TEXT,
            workspace_id TEXT,
            response_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (scope, cache_key, data_version, organization_id, workspace_id)
        )
    """)
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_cache_isolation -v`

Expected: PASS with analysis-cache storage tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/server.py tests/test_workspace_cache_isolation.py
git commit -m "feat: add workspace scope to analysis cache"
```

---

### Task 5: Add Workspace Scope to Alerts and Report-Derived Storage

**Files:**
- Create: `tests/test_workspace_storage_isolation.py`
- Modify: `backend/database.py`
- Modify: `backend/alerts.py`
- Modify: `backend/reports.py`
- Modify: `backend/server.py`

- [ ] **Step 1: Write the failing tenant-derived storage tests**

```python
import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager


class WorkspaceStorageIsolationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_alert_rule_round_trip_preserves_workspace_scope(self):
        saved = self.db.upsert_alert_rule(
            {
                "rule_id": "rule_1",
                "name": "Spike",
                "rule_type": "price_threshold",
                "market": "NEM",
                "region_or_zone": "NSW1",
                "config": {},
                "channel_type": "webhook",
                "channel_target": "https://example.com",
                "enabled": True,
                "organization_id": "org_a",
                "workspace_id": "ws_a",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.assertEqual(saved["organization_id"], "org_a")
        self.assertEqual(saved["workspace_id"], "ws_a")

    def test_fetch_alert_rules_does_not_cross_workspace(self):
        self.db.upsert_alert_rule(
            {
                "rule_id": "rule_1",
                "name": "Spike",
                "rule_type": "price_threshold",
                "market": "NEM",
                "region_or_zone": "NSW1",
                "config": {},
                "channel_type": "webhook",
                "channel_target": "https://example.com",
                "enabled": True,
                "organization_id": "org_a",
                "workspace_id": "ws_a",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        items = self.db.fetch_alert_rules(workspace_id="ws_b")
        self.assertEqual(items, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_storage_isolation -v`

Expected: FAIL because alert-rule storage does not preserve or filter by workspace scope.

- [ ] **Step 3: Write minimal tenant-derived storage implementation**

```python
# backend/database.py

# Add organization_id/workspace_id to:
# - ALERT_RULE_TABLE
# - ALERT_STATE_TABLE where tenant-owned
# - ALERT_DELIVERY_LOG_TABLE where tenant-owned

def fetch_alert_rules(self, enabled_only: bool = False, workspace_id: str | None = None) -> list[dict]:
    with self.get_connection() as conn:
        self.ensure_alert_tables(conn)
        params = []
        query = f"SELECT ... organization_id, workspace_id ... FROM {self.ALERT_RULE_TABLE}"
        clauses = []
        if enabled_only:
            clauses.append("enabled = 1")
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_storage_isolation -v`

Expected: PASS with alert/report-derived storage tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/alerts.py backend/reports.py backend/server.py tests/test_workspace_storage_isolation.py
git commit -m "feat: add workspace scope to alerts and report storage"
```

---

### Task 6: Add Artifact Metadata Scope and Access Checks

**Files:**
- Modify: `backend/storage_lake.py`
- Modify: `backend/job_framework.py`
- Modify: `backend/server.py`
- Modify: `tests/test_workspace_storage_isolation.py`

- [ ] **Step 1: Write the failing artifact-scope tests**

```python
def test_artifact_metadata_contains_org_and_workspace(self):
    artifact = lake.write_artifact(
        category="report_generate",
        payload={"ok": True},
        organization_id="org_a",
        workspace_id="ws_a",
    )
    self.assertEqual(artifact["organization_id"], "org_a")
    self.assertEqual(artifact["workspace_id"], "ws_a")

def test_artifact_scope_mismatch_is_rejected(self):
    artifact = {
        "organization_id": "org_a",
        "workspace_id": "ws_a",
    }
    with self.assertRaises(HTTPException):
        server._assert_artifact_scope(
            artifact,
            {
                "organization_id": "org_a",
                "workspace_id": "ws_b",
            },
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_storage_isolation -v`

Expected: FAIL with missing artifact scope assertion or missing metadata fields.

- [ ] **Step 3: Write minimal artifact-scope implementation**

```python
# backend/storage_lake.py

def write_artifact(self, *, category: str, payload: dict, organization_id: str | None = None, workspace_id: str | None = None) -> dict:
    ...
    metadata = {
        "artifact_id": artifact_id,
        "category": category,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        ...
    }

# backend/server.py

def _assert_artifact_scope(artifact: dict, scope: dict):
    if artifact.get("organization_id") and artifact["organization_id"] != scope.get("organization_id"):
        raise HTTPException(status_code=403, detail="Artifact organization mismatch")
    if artifact.get("workspace_id") and artifact["workspace_id"] != scope.get("workspace_id"):
        raise HTTPException(status_code=403, detail="Artifact workspace mismatch")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_storage_isolation -v`

Expected: PASS with artifact-scope tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/storage_lake.py backend/job_framework.py backend/server.py tests/test_workspace_storage_isolation.py
git commit -m "feat: add artifact scope metadata and checks"
```

---

### Task 7: Unify Internal and External Query Isolation Checks

**Files:**
- Modify: `backend/server.py`
- Modify: `tests/test_workspace_isolation.py`
- Modify: `tests/test_external_api_v1_routes.py`

- [ ] **Step 1: Write the failing route-isolation tests**

```python
def test_internal_query_path_rejects_workspace_region_policy_violation(self):
    with self.assertRaises(HTTPException) as ctx:
        server._assert_scope_allows_internal_query(
            {
                "organization_id": "org_a",
                "workspace_id": "ws_a",
                "allowed_regions": ["NSW1"],
                "allowed_markets": ["NEM"],
            },
            region="QLD1",
            market="NEM",
        )
    self.assertEqual(ctx.exception.status_code, 403)

def test_v1_query_path_uses_same_scope_guard(self):
    scope = {
        "organization_id": "org_a",
        "workspace_id": "ws_a",
        "allowed_regions": ["NSW1"],
        "allowed_markets": ["NEM"],
    }
    server._assert_scope_allows_internal_query(scope, region="NSW1", market="NEM")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workspace_isolation tests.test_external_api_v1_routes -v`

Expected: FAIL with missing shared internal-query guard.

- [ ] **Step 3: Write minimal unified query-guard implementation**

```python
# backend/server.py

def _assert_scope_allows_internal_query(scope: dict, *, region: str | None = None, market: str | None = None):
    assert_scope_allows_region_market(scope, region=region, market=market)

# Replace route-local policy branches where possible with:
# _assert_scope_allows_internal_query(scope, region=region, market=market)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workspace_isolation tests.test_external_api_v1_routes -v`

Expected: PASS with internal/external isolation guard tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/server.py tests/test_workspace_isolation.py tests/test_external_api_v1_routes.py
git commit -m "feat: unify workspace query isolation guards"
```

---

### Task 8: Final Verification and Documentation Sync

**Files:**
- Modify: `docs/商业化改造执行任务书.md`
- Modify: `docs/superpowers/specs/2026-04-28-f4-identity-governance-and-workspace-isolation-design.md`

- [ ] **Step 1: Add manual acceptance checklist**

Before merge, verify:

```text
- Internal and external query paths both consume workspace scope
- Same business request in different workspaces yields different cache keys
- Analysis cache rows do not cross workspace boundaries
- Alerts/reports/artifacts preserve organization_id + workspace_id
- Artifact reads validate metadata scope before file access
```

- [ ] **Step 2: Run verification commands**

Run:

```bash
python -m unittest tests.test_workspace_scope tests.test_workspace_cache_isolation tests.test_workspace_storage_isolation tests.test_workspace_isolation tests.test_external_api_v1 tests.test_external_api_v1_routes tests.test_job_framework tests.test_job_queue_routes tests.test_reports_api tests.test_access_control tests.test_access_control_routes -v
python -m py_compile backend/access_control.py backend/database.py backend/server.py backend/storage_lake.py backend/job_framework.py backend/reports.py backend/alerts.py
```

Expected:

- all tests PASS
- `py_compile` exits cleanly

- [ ] **Step 3: Update implementation status docs**

Update `docs/商业化改造执行任务书.md` F4 section with lines equivalent to:

```md
- 已完成：AccessScope 基础模型
- 已完成：workspace policy 统一查询校验收口
- 已完成：response_cache / analysis_cache 带 workspace scope
- 已完成：alerts / reports / artifacts 派生数据带 workspace scope
- 已完成：artifact metadata 访问校验
- 未完成：更深层存储迁移与更广泛历史数据回填
```

Add a short implementation-note section to the design spec if helper or field names changed during delivery.

- [ ] **Step 4: Commit**

```bash
git add docs/商业化改造执行任务书.md docs/superpowers/specs/2026-04-28-f4-identity-governance-and-workspace-isolation-design.md
git commit -m "docs: update phase 3 isolation status"
```

---

## Self-Review

### Spec coverage

This plan covers the full `Phase 3: Workspace Isolation` scope from the approved design:

- `AccessScope`
- service-level permission unification
- scope-aware cache keys
- scope-aware stored derived data
- artifact metadata authorization path
- negative-path isolation tests

It intentionally does not implement:

- new SSO behavior
- organization membership and lifecycle changes
- SCIM
- SAML

Those belong to other plans.

### Placeholder scan

- No `TODO` or `TBD` placeholders remain.
- Each task includes concrete file paths, tests, commands, expected outcomes, and implementation snippets.

### Type consistency

Consistent names used across tasks:

- `build_workspace_access_scope`
- `assert_scope_allows_region_market`
- `_scope_cache_payload`
- `_scope_analysis_payload`
- `_assert_artifact_scope`
- `_assert_scope_allows_internal_query`

---

Plan complete and saved to `docs/superpowers/plans/2026-04-28-f4-phase3-workspace-end-to-end-isolation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
