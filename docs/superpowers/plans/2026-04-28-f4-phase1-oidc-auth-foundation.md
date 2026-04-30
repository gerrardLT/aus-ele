# F4 Phase 1 JWT Auth Foundation Implementation Plan

> Status: updated on 2026-04-28 after product direction reset.  
> OIDC and enterprise SSO are out of scope. Phase 1 now means first-party auth: password login, JWT access token, server-side session lifecycle, and org/workspace-aware authorization.

## 1. Scope

Phase 1 is responsible for:

- password setup and password login
- short-lived JWT access token issuance
- server-side session issuance and refresh
- logout and session revoke
- authenticated actor resolution
- org/workspace context propagation
- audit coverage for login, refresh, and logout

Phase 1 does not complete:

- enterprise SSO
- external identity providers
- advanced invite policies
- full tenant-governance lifecycle
- full workspace-wide storage isolation retrofit

## 2. Implemented Baseline

As of 2026-04-28, the codebase now has:

- `POST /api/auth/password/set`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/session`
- `POST /api/auth/logout`
- JWT access token issuance with HS256 signing
- DB-backed `auth_session` lifecycle
- JWT claims bound to `principal_id`, `workspace_id`, and `session_id`
- refresh issuing a new JWT from a valid session
- suspended org membership blocking existing session and access token use

## 3. Current Architecture

### Authentication shape

1. User logs in with email, password, and workspace.
2. Server verifies password, workspace membership, and active org membership.
3. Server creates `auth_session`.
4. Server issues a short-lived JWT access token.
5. API authorization continues to resolve current permission state from the database.
6. Refresh uses the session token, not a long-lived stateless JWT.
7. Logout revokes the session. Session-bound JWTs become invalid because auth checks require the backing session to remain active.

### Security model

- JWT is only the transport token for API access.
- Session remains the revocable source of truth.
- Workspace membership is resolved live from DB state.
- Org membership suspension is enforced during token/session authentication.
- Permissions are not trusted from token claims alone.

## 4. Files in Scope

### Code

- `backend/access_control.py`
- `backend/database.py`
- `backend/server.py`

### Tests

- `tests/test_access_control.py`
- `tests/test_access_control_routes.py`
- regression suites touching org governance, workspace isolation, alerts, reports, Fingrid, and v1 APIs

## 5. Delivered Work

### Phase 1A: JWT and session foundation

Completed:

- JWT access token helper implementation
- session-backed password login bundle
- refresh route and domain helper
- access token expiry checks
- session expiry / revoked checks
- session-bound JWT validation

### Phase 1B: governance-aware auth enforcement

Completed:

- login requires active org membership when workspace belongs to an organization
- session auth blocks inactive org membership
- JWT auth blocks inactive org membership
- suspended members lose access to existing session-bound tokens

### Phase 1C: route surface

Completed:

- `/api/auth/login` returns session + JWT bundle
- `/api/auth/refresh` rotates JWT
- `/api/auth/logout` revokes session
- `/api/auth/session` resolves current authenticated actor

## 6. Verification

Relevant auth tests now cover:

- JWT token shape and claim binding
- password login returns authenticated session and JWT
- refresh rotates access token
- logout blocks further refresh
- suspended org membership blocks existing session and access token

Broader regression also remains green across:

- org governance
- workspace scope/isolation
- alerts
- reports
- external API v1
- Fingrid endpoints
- BESS backtest endpoints

## 7. Remaining F4 Work After Phase 1

This section is now historical context.

As of 2026-04-28, the planned F4 follow-on work after Phase 1 has been completed inside later implementation passes:

- tenant governance lifecycle was closed with invite expiry/reissue, JIT org join policy, member search/filter views, org audit queries, and bulk member operations
- workspace isolation sweep was closed for the planned phase scope, including scoped job management, scoped observability summaries, and shared scope enforcement across the high-value business paths

What remains after F4 is optional hardening rather than required scope:

- explicit refresh-token model if product later needs browser/mobile split semantics
- configurable secret rotation policy
- optional access-token revocation index beyond session-bound revocation
- deeper historical storage migration work that belongs to broader platform architecture, not F4 acceptance

## 8. Acceptance State

Phase 1 should be considered complete when the team agrees the project only needs:

- first-party login
- JWT access
- session refresh/revoke
- org/workspace-aware authorization

If future product scope adds enterprise federation, that is a separate later phase, not a reopen of this Phase 1 plan.
