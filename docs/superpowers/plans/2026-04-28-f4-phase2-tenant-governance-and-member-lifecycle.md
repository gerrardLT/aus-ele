# F4 Phase 2 Tenant Governance and Member Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add organization-level membership, org-admin authority boundaries, a richer invite model, and auditable member lifecycle controls on top of the Phase 1 auth foundation and current workspace-scoped RBAC.

**Architecture:** Extend the access-control layer from workspace-only membership into a two-level model: `organization_membership` for tenant governance and evolved invite/member state records for organization/workspace lifecycle actions. Keep business-role RBAC at the workspace layer, but route governance-sensitive actions through organization-role checks in focused access-control helpers rather than ad hoc route logic.

**Tech Stack:** FastAPI, SQLite via `DatabaseManager`, Python `unittest`, existing `backend/access_control.py`, existing audit log table, existing route direct-call test style

---

## File Structure

### Existing files to modify

- `backend/database.py`
  - add organization membership schema and richer invite/member status fields
  - add fetch/upsert/list helpers for organization memberships and invite transitions
- `backend/access_control.py`
  - add org role model, org permission checks, invite lifecycle helpers, member lifecycle helpers
- `backend/server.py`
  - expose org membership, org invite, suspension, reactivation, removal, and owner-transfer routes

### New files to create

- `tests/test_org_governance.py`
  - core domain tests for org roles, invite states, and member lifecycle
- `tests/test_org_governance_routes.py`
  - route-level tests for admin boundaries and lifecycle actions

### Existing tests to keep green

- `tests/test_access_control.py`
- `tests/test_access_control_routes.py`
- `tests/test_oidc_auth.py`
- `tests/test_oidc_auth_routes.py`
- `tests/test_workspace_isolation.py`

---

### Task 1: Add Organization Membership Schema and Helpers

**Files:**
- Create: `tests/test_org_governance.py`
- Modify: `backend/database.py`

- [ ] **Step 1: Write the failing organization-membership database tests**

```python
import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager


class OrganizationGovernanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_organization_membership_round_trip(self):
        organization = self.db.upsert_organization(
            {
                "organization_id": "org_acme",
                "name": "Acme",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        principal = self.db.upsert_principal(
            {
                "principal_id": "pr_owner",
                "email": "owner@acme.com",
                "display_name": "Owner",
                "password_hash": None,
                "password_salt": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        membership = self.db.upsert_organization_membership(
            {
                "organization_membership_id": "om_1",
                "organization_id": organization["organization_id"],
                "principal_id": principal["principal_id"],
                "role": "org_owner",
                "status": "active",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        fetched = self.db.fetch_organization_membership(organization["organization_id"], principal["principal_id"])
        self.assertEqual(membership["role"], fetched["role"])
        self.assertEqual(fetched["status"], "active")

    def test_list_organization_memberships_returns_multiple_members(self):
        self.db.upsert_organization({"organization_id": "org_acme", "name": "Acme", "created_at": "2026-04-28T00:00:00Z", "updated_at": "2026-04-28T00:00:00Z"})
        for idx in range(2):
            principal_id = f"pr_{idx}"
            self.db.upsert_principal(
                {
                    "principal_id": principal_id,
                    "email": f"user{idx}@acme.com",
                    "display_name": f"User {idx}",
                    "password_hash": None,
                    "password_salt": None,
                    "created_at": "2026-04-28T00:00:00Z",
                    "updated_at": "2026-04-28T00:00:00Z",
                }
            )
            self.db.upsert_organization_membership(
                {
                    "organization_membership_id": f"om_{idx}",
                    "organization_id": "org_acme",
                    "principal_id": principal_id,
                    "role": "org_member",
                    "status": "active",
                    "created_at": "2026-04-28T00:00:00Z",
                    "updated_at": "2026-04-28T00:00:00Z",
                }
            )
        items = self.db.list_organization_memberships("org_acme")
        self.assertEqual(len(items), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_org_governance.OrganizationGovernanceDatabaseTests -v`

Expected: FAIL with missing `upsert_organization_membership`, `fetch_organization_membership`, or `list_organization_memberships`.

- [ ] **Step 3: Write minimal organization-membership schema and helpers**

```python
# backend/database.py

ORGANIZATION_MEMBERSHIP_TABLE = "organization_membership"

def ensure_access_control_tables(self, conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.ORGANIZATION_MEMBERSHIP_TABLE} (
            organization_membership_id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(organization_id, principal_id),
            FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
            FOREIGN KEY(principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id)
        )
    """)
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{self.ORGANIZATION_MEMBERSHIP_TABLE}_org_status
        ON {self.ORGANIZATION_MEMBERSHIP_TABLE} (organization_id, status, created_at)
    """)
    conn.commit()

def upsert_organization_membership(self, record: dict) -> dict:
    with self.get_connection() as conn:
        self.ensure_access_control_tables(conn)
        conn.execute(
            f"""
            INSERT INTO {self.ORGANIZATION_MEMBERSHIP_TABLE} (
                organization_membership_id, organization_id, principal_id, role, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(organization_id, principal_id) DO UPDATE SET
                role=excluded.role,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                record["organization_membership_id"],
                record["organization_id"],
                record["principal_id"],
                record["role"],
                record["status"],
                record["created_at"],
                record["updated_at"],
            ),
        )
        conn.commit()
    return self.fetch_organization_membership(record["organization_id"], record["principal_id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_org_governance.OrganizationGovernanceDatabaseTests -v`

Expected: PASS with both organization-membership database tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py tests/test_org_governance.py
git commit -m "feat: add organization membership storage"
```

---

### Task 2: Upgrade Invite Storage to a Stateful Membership Invite Model

**Files:**
- Modify: `backend/database.py`
- Modify: `tests/test_org_governance.py`

- [ ] **Step 1: Write the failing invite-state tests**

```python
def test_membership_invite_round_trip_supports_org_scope(self):
    invite = self.db.upsert_membership_invite(
        {
            "invite_id": "inv_org_1",
            "organization_id": "org_acme",
            "workspace_id": None,
            "target_scope_type": "organization",
            "email": "analyst@acme.com",
            "target_role": "org_member",
            "invite_token": "invite-token-1",
            "status": "pending",
            "invited_by_principal_id": "pr_owner",
            "accepted_by_principal_id": None,
            "revoked_by_principal_id": None,
            "expires_at": "2026-05-01T00:00:00Z",
            "accepted_at": None,
            "revoked_at": None,
            "revoke_reason": None,
            "created_at": "2026-04-28T00:00:00Z",
            "updated_at": "2026-04-28T00:00:00Z",
        }
    )
    fetched = self.db.fetch_membership_invite(invite["invite_id"])
    self.assertEqual(fetched["target_scope_type"], "organization")
    self.assertEqual(fetched["status"], "pending")

def test_membership_invite_can_be_fetched_by_token(self):
    invite = self.db.fetch_membership_invite_by_token("invite-token-1")
    self.assertEqual(invite["email"], "analyst@acme.com")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_org_governance -v`

Expected: FAIL with missing `upsert_membership_invite`, `fetch_membership_invite`, or `fetch_membership_invite_by_token`.

- [ ] **Step 3: Write minimal invite storage implementation**

```python
# backend/database.py

MEMBERSHIP_INVITE_TABLE = "membership_invite"

def ensure_access_control_tables(self, conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.MEMBERSHIP_INVITE_TABLE} (
            invite_id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            workspace_id TEXT,
            target_scope_type TEXT NOT NULL,
            email TEXT NOT NULL,
            target_role TEXT NOT NULL,
            invite_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            invited_by_principal_id TEXT NOT NULL,
            accepted_by_principal_id TEXT,
            revoked_by_principal_id TEXT,
            expires_at TEXT,
            accepted_at TEXT,
            revoked_at TEXT,
            revoke_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
            FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
        )
    """)
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{self.MEMBERSHIP_INVITE_TABLE}_org_email
        ON {self.MEMBERSHIP_INVITE_TABLE} (organization_id, email, status, created_at DESC)
    """)
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_org_governance -v`

Expected: PASS with invite-state tests green alongside Task 1 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py tests/test_org_governance.py
git commit -m "feat: add membership invite state storage"
```

---

### Task 3: Add Org Role Permissions and Org Actor Resolution

**Files:**
- Modify: `backend/access_control.py`
- Modify: `tests/test_org_governance.py`

- [ ] **Step 1: Write the failing org-role tests**

```python
from access_control import (
    ORG_ROLE_PERMISSIONS,
    authenticate_org_actor,
    check_organization_permission,
    seed_organization_membership,
)

def test_org_owner_contains_governance_permissions(self):
    self.assertIn("org_manage", ORG_ROLE_PERMISSIONS["org_owner"])
    self.assertIn("member_manage", ORG_ROLE_PERMISSIONS["org_owner"])

def test_authenticate_org_actor_uses_active_organization_membership(self):
    organization = seed_organization(self.db, name="Acme")
    principal = seed_principal(self.db, email="owner@acme.com", display_name="Owner")
    seed_organization_membership(
        self.db,
        organization_id=organization["organization_id"],
        principal_id=principal["principal_id"],
        role="org_owner",
        status="active",
    )
    actor = authenticate_org_actor(self.db, organization["organization_id"], principal["principal_id"])
    self.assertEqual(actor["organization_membership"]["role"], "org_owner")

def test_check_organization_permission_rejects_org_member_for_org_manage(self):
    actor = {
        "organization_membership": {"role": "org_member", "status": "active"},
    }
    with self.assertRaises(HTTPException) as ctx:
        check_organization_permission(actor, "org_manage")
    self.assertEqual(ctx.exception.status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_org_governance -v`

Expected: FAIL with missing `ORG_ROLE_PERMISSIONS`, `authenticate_org_actor`, or `seed_organization_membership`.

- [ ] **Step 3: Write minimal org-role implementation**

```python
# backend/access_control.py

ORG_ROLE_PERMISSIONS = {
    "org_owner": {"org_manage", "member_manage", "workspace_manage", "read_audit"},
    "org_admin": {"member_manage", "workspace_manage", "read_audit"},
    "org_billing_viewer": set(),
    "org_member": set(),
}

def seed_organization_membership(db, *, organization_id: str, principal_id: str, role: str, status: str = "active") -> dict:
    membership = db.upsert_organization_membership(
        {
            "organization_membership_id": f"om_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "principal_id": principal_id,
            "role": role,
            "status": status,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="organization_membership.upserted",
        target_type="organization_membership",
        target_id=membership["organization_membership_id"],
        detail_json={"organization_id": organization_id, "role": role, "status": status},
    )
    return membership

def authenticate_org_actor(db, organization_id: str, principal_id: str) -> dict:
    organization = db.fetch_organization(organization_id)
    principal = db.fetch_principal(principal_id)
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not organization or not principal or not membership or membership["status"] != "active":
        raise HTTPException(status_code=401, detail="Invalid organization actor")
    return {"organization": organization, "principal": principal, "organization_membership": membership}

def check_organization_permission(actor: dict, permission: str):
    role = actor["organization_membership"]["role"]
    allowed = ORG_ROLE_PERMISSIONS.get(role, set())
    if permission not in allowed:
        raise HTTPException(status_code=403, detail="Organization permission denied")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_org_governance -v`

Expected: PASS with org-role tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/access_control.py tests/test_org_governance.py
git commit -m "feat: add organization role permissions"
```

---

### Task 4: Add Organization Invite Lifecycle Helpers

**Files:**
- Modify: `backend/access_control.py`
- Modify: `tests/test_org_governance.py`

- [ ] **Step 1: Write the failing org-invite lifecycle tests**

```python
from access_control import (
    create_membership_invite,
    revoke_membership_invite,
    accept_membership_invite,
)

def test_org_admin_can_create_org_invite(self):
    invite = create_membership_invite(
        self.db,
        actor=self.org_owner_actor,
        organization_id=self.organization["organization_id"],
        workspace_id=None,
        target_scope_type="organization",
        email="invitee@acme.com",
        target_role="org_member",
        expires_at="2026-05-01T00:00:00Z",
    )
    self.assertEqual(invite["status"], "pending")
    self.assertEqual(invite["target_scope_type"], "organization")

def test_revoke_membership_invite_marks_status_and_reason(self):
    revoked = revoke_membership_invite(
        self.db,
        actor=self.org_owner_actor,
        invite_id=self.pending_invite["invite_id"],
        revoke_reason="duplicate",
    )
    self.assertEqual(revoked["status"], "revoked")
    self.assertEqual(revoked["revoke_reason"], "duplicate")

def test_accept_org_invite_creates_active_org_membership(self):
    accepted = accept_membership_invite(
        self.db,
        invite_token=self.pending_invite["invite_token"],
        display_name="Invitee",
    )
    membership = self.db.fetch_organization_membership(self.organization["organization_id"], accepted["principal"]["principal_id"])
    self.assertEqual(membership["status"], "active")
    self.assertEqual(membership["role"], "org_member")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_org_governance -v`

Expected: FAIL with missing membership-invite lifecycle helpers.

- [ ] **Step 3: Write minimal invite lifecycle implementation**

```python
# backend/access_control.py

def create_membership_invite(db, *, actor: dict, organization_id: str, workspace_id: str | None, target_scope_type: str, email: str, target_role: str, expires_at: str | None) -> dict:
    check_organization_permission(actor, "member_manage")
    invite = db.upsert_membership_invite(
        {
            "invite_id": f"inv_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_scope_type": target_scope_type,
            "email": email.lower().strip(),
            "target_role": target_role,
            "invite_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "status": "pending",
            "invited_by_principal_id": actor["principal"]["principal_id"],
            "accepted_by_principal_id": None,
            "revoked_by_principal_id": None,
            "expires_at": expires_at,
            "accepted_at": None,
            "revoked_at": None,
            "revoke_reason": None,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(db, actor_principal_id=actor["principal"]["principal_id"], action="membership_invite.created", target_type="membership_invite", target_id=invite["invite_id"], detail_json={"organization_id": organization_id, "workspace_id": workspace_id, "email": invite["email"]})
    return invite
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_org_governance -v`

Expected: PASS with organization-invite lifecycle tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/access_control.py tests/test_org_governance.py
git commit -m "feat: add organization invite lifecycle"
```

---

### Task 5: Add Suspension, Reactivation, Removal, and Owner Transfer Helpers

**Files:**
- Modify: `backend/access_control.py`
- Modify: `tests/test_org_governance.py`

- [ ] **Step 1: Write the failing member-lifecycle tests**

```python
from access_control import (
    suspend_organization_member,
    reactivate_organization_member,
    remove_organization_member,
    transfer_organization_owner,
)

def test_suspend_and_reactivate_organization_member(self):
    suspended = suspend_organization_member(
        self.db,
        actor=self.org_owner_actor,
        organization_id=self.organization["organization_id"],
        principal_id=self.member_principal["principal_id"],
    )
    self.assertEqual(suspended["status"], "suspended")
    reactivated = reactivate_organization_member(
        self.db,
        actor=self.org_owner_actor,
        organization_id=self.organization["organization_id"],
        principal_id=self.member_principal["principal_id"],
    )
    self.assertEqual(reactivated["status"], "active")

def test_remove_organization_member_marks_removed(self):
    removed = remove_organization_member(
        self.db,
        actor=self.org_owner_actor,
        organization_id=self.organization["organization_id"],
        principal_id=self.member_principal["principal_id"],
    )
    self.assertEqual(removed["status"], "removed")

def test_transfer_organization_owner_promotes_target_and_demotes_current_owner(self):
    result = transfer_organization_owner(
        self.db,
        actor=self.org_owner_actor,
        organization_id=self.organization["organization_id"],
        new_owner_principal_id=self.member_principal["principal_id"],
    )
    self.assertEqual(result["new_owner"]["role"], "org_owner")
    self.assertEqual(result["previous_owner"]["role"], "org_admin")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_org_governance -v`

Expected: FAIL with missing lifecycle helper functions.

- [ ] **Step 3: Write minimal lifecycle implementation**

```python
# backend/access_control.py

def suspend_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    updated = db.upsert_organization_membership({**membership, "status": "suspended", "updated_at": _utc_now_iso()})
    _write_audit(db, actor_principal_id=actor["principal"]["principal_id"], action="organization_membership.suspended", target_type="organization_membership", target_id=updated["organization_membership_id"], detail_json={"organization_id": organization_id, "principal_id": principal_id})
    return updated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_org_governance -v`

Expected: PASS with suspension/reactivation/removal/owner-transfer tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/access_control.py tests/test_org_governance.py
git commit -m "feat: add organization member lifecycle helpers"
```

---

### Task 6: Expose Organization Governance Routes

**Files:**
- Create: `tests/test_org_governance_routes.py`
- Modify: `backend/server.py`

- [ ] **Step 1: Write the failing governance route tests**

```python
import os
import sys
import tempfile
import types
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


class OrganizationGovernanceRouteTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_orchestrator_db = server.job_orchestrator.db
        server.db = self.db
        server.job_orchestrator.db = self.db

        self.organization = server.create_organization_route(name="Acme")
        self.owner = server.create_principal_route(email="owner@acme.com", display_name="Owner")
        self.member = server.create_principal_route(email="member@acme.com", display_name="Member")
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            role="org_owner",
            status="active",
        )

    def tearDown(self):
        server.db = self.original_db
        server.job_orchestrator.db = self.original_orchestrator_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_owner_can_list_organization_members(self):
        payload = server.list_organization_members_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
        )
        self.assertEqual(len(payload["items"]), 1)

    def test_owner_can_invite_and_suspend_member(self):
        invite = server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="invitee@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        self.assertEqual(invite["status"], "pending")
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.member["principal_id"],
            role="org_member",
            status="active",
        )
        suspended = server.suspend_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.member["principal_id"],
            actor_principal_id=self.owner["principal_id"],
        )
        self.assertEqual(suspended["status"], "suspended")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_org_governance_routes -v`

Expected: FAIL with missing organization governance routes.

- [ ] **Step 3: Write minimal route implementation**

```python
# backend/server.py

@app.post("/api/admin/organizations/{organization_id}/members")
def add_organization_member_route(
    organization_id: str,
    principal_id: str = Query(...),
    role: str = Query(...),
    status: str = Query("active"),
):
    return seed_organization_membership(db, organization_id=organization_id, principal_id=principal_id, role=role, status=status)


@app.get("/api/admin/organizations/{organization_id}/members")
def list_organization_members_route(organization_id: str, principal_id: str = Query(...)):
    authenticate_org_actor(db, organization_id, principal_id)
    return {"items": db.list_organization_memberships(organization_id)}


@app.post("/api/admin/organizations/{organization_id}/invites")
def create_organization_invite_route(
    organization_id: str,
    principal_id: str = Query(...),
    email: str = Query(...),
    target_role: str = Query(...),
    expires_at: str = Query(...),
):
    actor = authenticate_org_actor(db, organization_id, principal_id)
    return create_membership_invite(
        db,
        actor=actor,
        organization_id=organization_id,
        workspace_id=None,
        target_scope_type="organization",
        email=email,
        target_role=target_role,
        expires_at=expires_at,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_org_governance_routes -v`

Expected: PASS with organization-governance route tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/server.py tests/test_org_governance_routes.py
git commit -m "feat: add organization governance routes"
```

---

### Task 7: Add Admin-Boundary Negative Tests and Final Verification

**Files:**
- Modify: `tests/test_org_governance_routes.py`
- Modify: `docs/商业化改造执行任务书.md`
- Modify: `docs/superpowers/specs/2026-04-28-f4-identity-governance-and-workspace-isolation-design.md`

- [ ] **Step 1: Write the failing negative-boundary tests**

```python
def test_org_member_cannot_create_org_invite(self):
    server.add_organization_member_route(
        organization_id=self.organization["organization_id"],
        principal_id=self.member["principal_id"],
        role="org_member",
        status="active",
    )
    with self.assertRaises(HTTPException) as ctx:
        server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.member["principal_id"],
            email="blocked@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
    self.assertEqual(ctx.exception.status_code, 403)

def test_workspace_admin_cannot_mutate_org_membership(self):
    workspace = server.create_workspace_route(organization_id=self.organization["organization_id"], name="Primary")
    server.add_workspace_member_route(workspace_id=workspace["workspace_id"], principal_id=self.member["principal_id"], role="admin")
    with self.assertRaises(HTTPException):
        server.suspend_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            actor_principal_id=self.member["principal_id"],
        )
```

- [ ] **Step 2: Run verification commands**

Run:

```bash
python -m unittest tests.test_org_governance tests.test_org_governance_routes tests.test_access_control tests.test_access_control_routes tests.test_oidc_auth tests.test_oidc_auth_routes -v
python -m py_compile backend/database.py backend/access_control.py backend/server.py
```

Expected:

- all tests PASS
- `py_compile` exits cleanly

- [ ] **Step 3: Update implementation status docs**

Update `docs/商业化改造执行任务书.md` F4 section with lines equivalent to:

```md
- 已完成：organization membership 基础模型
- 已完成：org_owner / org_admin 权限边界
- 已完成：organization invite / revoke / accept 状态流
- 已完成：organization member suspend / reactivate / remove
- 已完成：organization owner transfer 基础闭环
- 未完成：JIT org join policy
- 未完成：workspace 全链路隔离
```

Add a short implementation-note section to the Phase 2 portion of the spec if field or route names drift during implementation.

- [ ] **Step 4: Commit**

```bash
git add tests/test_org_governance_routes.py docs/商业化改造执行任务书.md docs/superpowers/specs/2026-04-28-f4-identity-governance-and-workspace-isolation-design.md
git commit -m "docs: update phase 2 governance status"
```

---

## Self-Review

### Spec coverage

This plan covers the full `Phase 2: Tenant Governance` scope from the approved design:

- `organization_membership`
- org roles
- richer invite model
- suspend/reactivate/remove flows
- ownership transfer

It intentionally does not implement:

- `domain_auto_join_org` JIT policy behavior
- workspace-wide query/cache/storage isolation
- SCIM

Those belong to later plans.

### Placeholder scan

- No `TODO` or `TBD` placeholders remain.
- Each task includes concrete file paths, tests, commands, expected outcomes, and code snippets.

### Type consistency

Consistent names used across tasks:

- `organization_membership`
- `membership_invite`
- `seed_organization_membership`
- `authenticate_org_actor`
- `check_organization_permission`
- `create_membership_invite`
- `suspend_organization_member`
- `transfer_organization_owner`

---

Plan complete and saved to `docs/superpowers/plans/2026-04-28-f4-phase2-tenant-governance-and-member-lifecycle.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
