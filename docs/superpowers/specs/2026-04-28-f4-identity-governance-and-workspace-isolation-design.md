# F4 Identity, Governance, and Workspace Isolation Design

**Date:** 2026-04-28

**Status:** Draft approved in conversation, written for implementation handoff

## Implementation Status Snapshot

As of 2026-04-28, the implementation has moved materially beyond the original draft:

- Phase 1 baseline is now delivered as first-party `password + JWT + auth_session`, not OIDC-first auth.
- Organization governance baseline is delivered:
  - `organization_membership`
  - `org_owner / org_admin / org_member` boundaries
  - invite create / accept / revoke
  - invite expiry validation
  - pending invite reuse
  - suspend / reactivate / remove
  - owner transfer
- Member lifecycle now revokes existing `auth_session` and `access_token` records on suspend/remove.
- Workspace isolation baseline is delivered across:
  - main internal analysis query paths
  - `/api/v1/*` scoped query paths
  - response cache / analysis cache
  - alerts / reports / artifact metadata
  - internal and external job / lineage access paths

The remaining work is now mostly tail work:

- invite resend / reissue and richer join policy
- deeper historical / derived storage migration
- final cleanup of remaining low-frequency internal management / observability entry points

**Goal:** Upgrade the current access-control v2 foundation into a commercial-grade identity, tenant-governance, and workspace-isolation architecture that supports first-party JWT authentication, organization administration, full member lifecycle management, and end-to-end workspace-scoped data access.

---

## 1. Context

The current repository already has a working v2 baseline:

- `organization`, `workspace`, `principal_identity`
- `workspace_membership` and workspace-scoped RBAC
- local password login and local session issuance
- basic workspace invite / accept / revoke
- access-token authentication for admin and `/api/v1/*`
- partial workspace-aware restrictions for external APIs, jobs, lineage, and artifact storage

This is a valid foundation, but it is still below commercial SaaS requirements in three critical areas:

1. Authentication is still local-first and needs a production-grade JWT/session model.
2. Tenant governance is still workspace-centric and lacks organization-level administration and full member lifecycle management.
3. Workspace isolation is only partially enforced and is not yet a system-wide invariant across query paths, cache paths, and stored derived data.

This design addresses those three gaps while staying compatible with the current codebase shape and avoiding premature full-IAM overengineering.

---

## 2. Product and Technical Principles

This design follows two constraints:

1. **Advanced enough to be commercially credible**
   - JWT-based first-party authentication
   - organization-level admin boundaries
   - auditable member lifecycle
   - workspace-scoped derived-data isolation
   - future compatibility with SCIM

2. **Fit-for-repo rather than overbuilt**
   - keep the current FastAPI + SQLite development shape usable
   - do not introduce SAML first
   - do not introduce SCIM in phase 1
   - do not rebuild the whole backend into a separate IAM service

The resulting architecture should be:

- modern
- standards-aligned
- incrementally implementable
- testable with the current repository structure

---

## 3. External Research Summary

The recommended direction is grounded in current primary standards and vendor guidance:

- OIDC Core: identity layer on top of OAuth 2.0
  - https://openid.net/specs/openid-connect-core-1_0-18.html
- OIDC Discovery: standard provider discovery flow
  - https://openid.net/specs/openid-connect-discovery-1_0.html
- OAuth 2.0 Security Best Current Practice
  - RFC 9700, January 2025
  - https://datatracker.ietf.org/doc/html/rfc9700
- PKCE
  - RFC 7636
  - https://www.rfc-editor.org/rfc/rfc7636
- SCIM 2.0 core schema and protocol
  - https://datatracker.ietf.org/doc/html/rfc7643
  - https://datatracker.ietf.org/doc/html/rfc7644
- Google OIDC
  - https://developers.google.com/identity/openid-connect/openid-connect
- Microsoft Entra OIDC
  - https://learn.microsoft.com/en-us/azure/active-directory/fundamentals/auth-oidc
- Microsoft Entra SCIM provisioning
  - https://learn.microsoft.com/en-us/entra/identity/app-provisioning/how-provisioning-works

The main design decision from this research is:

> Use standard OIDC Authorization Code Flow as the SSO base, keep local session issuance inside this system, and defer SCIM to a later lifecycle-automation phase.

---

## 4. Scope

This design covers:

- OIDC SSO
- unified auth identity model
- organization-level admin model
- full invite / revoke lifecycle
- full member lifecycle states
- workspace-scope enforcement across:
  - query paths
  - cache keys
  - stored derived data
  - artifact metadata and access

This design explicitly does **not** include:

- SCIM 2.0 implementation
- SAML implementation
- billing / subscription enforcement
- external customer self-service admin portal
- migration to PostgreSQL

---

## 5. Authentication Architecture

### 5.1 Recommended protocol

SSO should use **OIDC Authorization Code Flow** with support for:

- Google Workspace-compatible OIDC
- Microsoft Entra ID-compatible OIDC
- provider discovery from `/.well-known/openid-configuration`

The system should continue to support local password login in parallel.

### 5.2 Why OIDC first

OIDC is preferred over SAML for the current repo because:

- the frontend/backend shape is already web-session-oriented
- both Google and Entra support it directly
- it is simpler to test and reason about than SAML in this codebase
- it aligns better with modern SaaS identity integration

### 5.3 Core auth model

Authentication must separate:

- internal system person identity
- credential source
- active business session

#### Existing entity retained

- `principal_identity`
  - internal human/user record

#### New entities

- `auth_identity`
  - maps a principal to one login source
  - fields:
    - `auth_identity_id`
    - `principal_id`
    - `provider_type` (`password`, `oidc`)
    - `provider_key` (`local`, `google`, `entra`, or custom OIDC key)
    - `subject`
    - `email`
    - `email_verified`
    - `created_at`
    - `updated_at`

- `oidc_provider`
  - organization-managed IdP configuration
  - fields:
    - `provider_id`
    - `organization_id`
    - `provider_key`
    - `issuer`
    - `discovery_url`
    - `client_id`
    - `client_secret_encrypted`
    - `scopes_json`
    - `enabled`
    - `created_at`
    - `updated_at`

- `organization_domain`
  - maps verified email domains to organizations
  - fields:
    - `domain_id`
    - `organization_id`
    - `domain`
    - `verified_at`
    - `join_mode`
    - `created_at`
    - `updated_at`

#### Existing entity extended

- `auth_session`
  - already exists as local session store
  - should be extended with:
    - `organization_id`
    - `auth_method`
    - `auth_identity_id`
    - `last_seen_at`

### 5.4 Login behavior

#### Local password login

- email/password
- resolve principal
- resolve organization/workspace membership context
- mint local session

#### OIDC SSO login

Recommended route shape:

- `POST /api/auth/oidc/start`
- `GET /api/auth/oidc/callback`
- `POST /api/auth/logout`
- `GET /api/auth/session`

Flow:

1. User starts login for a specific organization or provider.
2. System loads `oidc_provider`.
3. System creates `state` and `nonce`.
4. User is redirected to the IdP authorization endpoint.
5. Callback exchanges code for tokens.
6. ID token claims are validated.
7. `auth_identity` is found or created.
8. `principal_identity` is linked or created.
9. Membership and org access rules are resolved.
10. Local `auth_session` is issued.

### 5.5 Security baseline

Minimum security requirements:

- Authorization Code Flow only
- `state` validation
- `nonce` validation
- exact `redirect_uri` validation
- no implicit flow
- minimal scopes: `openid email profile`
- local session is the only business-session credential
- audit all login success/failure and identity link/unlink events

---

## 6. Tenant Governance Architecture

### 6.1 Two-level membership model

The current model is too workspace-centric. Governance must separate:

- organization-level membership
- workspace-level membership

#### New entity

- `organization_membership`
  - fields:
    - `organization_membership_id`
    - `organization_id`
    - `principal_id`
    - `role`
    - `status`
    - `created_at`
    - `updated_at`

#### Existing entity retained and evolved

- `workspace_membership`
  - continues to govern business access inside a workspace
  - should gain lifecycle status if not already present logically

### 6.2 Role model

#### Organization roles

- `org_owner`
- `org_admin`
- `org_billing_viewer`
- `org_member`

#### Workspace roles

- `workspace_owner`
- `workspace_admin`
- `analyst`
- `viewer`
- `exporter`

### 6.3 Permission boundaries

#### Organization-level responsibilities

- manage OIDC providers
- manage organization domains
- manage organization members
- create/manage workspaces
- review organization audit history
- govern invite and membership lifecycle

#### Workspace-level responsibilities

- manage workspace members
- manage workspace business access
- perform allowed analysis/export/report actions

### 6.4 Why this split matters

Without organization membership, the following stay incorrectly modeled:

- SSO ownership
- org admin rights
- domain policies
- org-wide member suspension/removal
- future billing and compliance boundaries

---

## 7. Invite, Revoke, and Member Lifecycle

### 7.1 Invite model

The current invite support is a good minimum but must become a full stateful governance flow.

Recommended entity:

- `membership_invite`
  - can replace or evolve the current workspace-only invite table
  - fields:
    - `invite_id`
    - `organization_id`
    - `workspace_id` (nullable for org-level invites)
    - `target_scope_type` (`organization`, `workspace`)
    - `email`
    - `target_role`
    - `invite_token`
    - `status` (`pending`, `accepted`, `revoked`, `expired`)
    - `invited_by_principal_id`
    - `accepted_by_principal_id`
    - `revoked_by_principal_id`
    - `expires_at`
    - `accepted_at`
    - `revoked_at`
    - `revoke_reason`
    - `created_at`
    - `updated_at`

### 7.2 Invite rules

- org-level invite can create organization membership first
- workspace invite must belong to an organization
- duplicate pending invites for same email/scope should be prevented or superseded cleanly
- revoke must be an audit-preserving status change, not deletion
- expiration should be enforced by data or query logic, not just UI

### 7.3 Member lifecycle states

#### Organization member lifecycle

- `invited`
- `active`
- `suspended`
- `removed`

#### Workspace member lifecycle

- `active`
- `suspended`
- `removed`

### 7.4 Required lifecycle actions

- invite member
- accept invite
- join via JIT SSO
- change role
- suspend member
- reactivate member
- remove from workspace
- remove from organization
- transfer owner
- revoke pending invite

### 7.5 JIT join policy

Support these organization-level join modes:

- `invite_only`
- `domain_auto_join_org`
- `domain_auto_join_workspace` (defer unless needed later)

Recommended phase-1 default:

- only implement `invite_only` and `domain_auto_join_org`

### 7.6 Audit requirements

These events must enter audit logs:

- invite created
- invite accepted
- invite revoked
- membership role changed
- membership suspended
- membership restored
- membership removed
- ownership transferred
- OIDC provider enabled/disabled
- domain policy changed

---

## 8. Workspace Isolation Architecture

This is the highest-risk area. Partial route-level checks are insufficient.

### 8.1 Design objective

Enforce workspace isolation as a system invariant across:

- query paths
- cache paths
- stored derived data
- artifact metadata and file access

The rule is:

> Any tenant-visible or tenant-reusable result must carry `organization_id` and `workspace_id`, and reads must enforce the same scope.

### 8.2 AccessScope abstraction

Business logic should stop receiving raw auth fragments and start receiving a unified resolved scope object:

- `principal_id`
- `organization_id`
- `workspace_id`
- `org_role`
- `workspace_role`
- `allowed_regions`
- `allowed_markets`

Every service path should receive:

- `db`
- `access_scope`
- business request parameters

instead of each route hand-rolling permission logic.

### 8.3 Query-layer isolation

Coverage must extend to:

- internal `/api/*` business endpoints
- external `/api/v1/*`
- jobs
- lineage
- alerts
- reports
- artifacts
- screening
- forecasts
- data-quality
- investment analysis

Rules:

- region/market requests must pass workspace policy checks
- reads of jobs/reports/alerts/artifacts must validate stored workspace scope
- no tenant-user path should default to global data visibility

### 8.4 Cache-layer isolation

Current caches are a major risk if keys only include functional parameters.

Required coverage:

- Redis `response_cache`
- SQLite `analysis_cache`
- forecast snapshot cache
- event overlay cache
- investment caches
- future report/export caches

Recommended key structure:

- `cache_scope`
- `organization_id`
- `workspace_id`
- `api_version`
- `logical_endpoint`
- `normalized_request_hash`

Examples:

- `response:{org_id}:{workspace_id}:{endpoint}:{hash}`
- `analysis:{org_id}:{workspace_id}:{scope}:{hash}`

This is required even when functional request parameters are identical, because:

- workspace policies may differ
- audit ownership differs
- future billing/quota ownership differs

### 8.5 Storage-layer isolation

File-path partitioning alone is not enough. Database records must also carry tenant scope.

Derived data and generated outputs that must carry `organization_id` and `workspace_id`:

- analysis caches
- generated report payloads
- saved exports
- alert rules and state where tenant-owned
- artifact metadata
- job payload/result metadata for tenant-triggered outputs
- future saved scenarios or presets

Governance data that must at least carry `organization_id`:

- OIDC providers
- organization domains
- organization memberships
- invites
- policies

### 8.6 Artifact isolation

The current artifact path partitioning is correct but incomplete.

Required additions:

- artifact metadata table or metadata record must store `organization_id` and `workspace_id`
- artifact access must resolve metadata first, then authorize, then read file
- no direct path-derived access
- report/export files must use the same metadata + auth path

Physical directory layout is not the security boundary. Authorization is.

---

## 9. Testing Strategy

This feature set requires explicit negative-path coverage, not just happy-path tests.

### 9.1 Authentication tests

- OIDC login success path
- invalid state rejected
- invalid nonce rejected
- wrong redirect URI rejected
- local session minted after valid callback
- account linking success/failure

### 9.2 Governance tests

- org admin can manage org members
- workspace admin cannot mutate org-level configuration
- invite state transitions:
  - pending -> accepted
  - pending -> revoked
  - pending -> expired
- suspend/reactivate/remove behavior
- owner transfer protections

### 9.3 Isolation tests

- same business parameters across different workspaces must not share tenant caches
- one workspace cannot read another workspace's:
  - jobs
  - lineage
  - alerts
  - report outputs
  - artifacts
  - cached analysis results
- suspended/removed members must fail business access even with older session tokens
- differing workspace policies should affect result visibility correctly

---

## 10. Implementation Phasing

### Phase 1: Authentication Foundation

Build:

- password login hardening
- JWT access token issuance
- refresh/session lifecycle
- authenticated actor resolution
- session enhancements
- auth audit coverage

Success condition:

- local login still works
- JWT login and refresh work reliably
- system can revoke auth state after suspend / revoke / role change

Implementation note as of 2026-04-28:

- Product direction has changed: OIDC / enterprise SSO is no longer the target for this project.
- Phase 1 should now converge on first-party auth only: password login, JWT access token, refresh/session control, revoke/logout, and audit coverage.
- Existing OIDC-related foundation code may remain in the codebase temporarily, but it is no longer the recommended completion path for F4.

### Phase 2: Tenant Governance

Build:

- `organization_membership`
- org roles
- richer invite model
- suspend/reactivate/remove flows
- ownership transfer
- JIT org join policies

Success condition:

- organization governance is independent from workspace business roles

Implementation note as of 2026-04-28:

- Phase 2 delivery has landed for `organization_membership`, org-role permission checks, organization-scope invite state, member suspension/reactivation/removal, owner transfer, invite expiration enforcement, and invite reissue/revoke hardening.
- The current invite implementation uses a new `membership_invite` table for organization-scope governance while the legacy `workspace_invite` path remains in place for workspace-only flows.
- JIT org join policy is now implemented for `invite_only` and `domain_auto_join_org`, including a first-party `/api/auth/domain-join` path. `domain_auto_join_workspace` remains deferred by design.
- Tenant governance operating surface is now closed for this phase, including member search/filter views, organization audit-log query support, and bulk lifecycle operations.

### Phase 3: Workspace Isolation

Build:

- `AccessScope`
- service-level permission unification
- scope-aware cache keys
- scope-aware stored derived data
- artifact metadata authorization path
- negative-path isolation tests

Success condition:

- workspace isolation is enforced across read, cache, and derived-data boundaries

Implementation note as of 2026-04-28:

- Phase 3 first delivery has landed for `build_workspace_access_scope`, unified region/market scope assertions, scope-aware response-cache payload builders, and scoped analysis-cache storage keys.
- Artifact metadata now preserves `organization_id` and `workspace_id`, and the backend has a shared artifact-scope assertion helper.
- Alerts tenant-owned storage and report payload generation now also preserve workspace scope.
- Alerts list/state/delivery/evaluate paths now support workspace-scoped filtering, so tenant-owned alert reads no longer depend only on write-time tagging.
- `/api/v1/prices`, `/api/v1/events`, `/api/v1/fcas`, and `/api/v1/data-quality` now share the same scope-guard path instead of each route holding its own policy logic.
- Internal non-v1 query entrypoints `get_price_trend`, `get_event_overlays`, `get_fcas_analysis`, `get_grid_forecast`, `get_grid_forecast_coverage`, `get_peak_analysis`, and `get_hourly_price_profile` now also accept optional `access_scope` and enforce the same shared region/market guard.
- `investment_analysis` now also accepts optional `access_scope`, enforces the shared region/market guard, and scopes its analysis-cache payload so one workspace cannot reuse another workspace's cached investment result.
- `get_data_quality_summary`, `get_data_quality_markets`, and `get_data_quality_issues` now support scope-aware market filtering, and `get_data_quality_issues(market=...)` now rejects requests outside workspace market policy with an explicit `403`.
- `get_market_screening` now supports scope-aware filtering across ranked candidates, honoring both `allowed_markets` and `allowed_regions` for tenant-visible result narrowing.
- Fingrid tenant-visible result endpoints (`status`, `series`, `summary`, `export`) and standardized BESS backtest endpoints (`backtests`, `coverage`) now also participate in shared scope enforcement.
- Alert read/evaluate helpers now also support `access_scope`, default to the scoped workspace when no explicit `workspace_id` is supplied, and reject cross-workspace reads with an explicit `403`.
- `generate_report` now accepts optional `access_scope`, enforces the same shared region/market guard, and propagates scope context into report generation inputs.
- The planned lower-priority internal management and observability sweep is now complete for this phase, including scoped `run-next` execution and scoped observability summaries.
- Future deeper historical derived-data migration can still improve architecture quality, but it is no longer treated as an F4 blocker.

### Deferred Phase 4

Not part of this design's first implementation:

- SCIM 2.0
- SAML
- external IAM service extraction
- full billing integration

---

## 11. Risks and Tradeoffs

### 11.1 `server.py` is already large

This work should avoid adding more long-lived complexity directly into the route file. Authentication, governance, and scope resolution should progressively move into focused backend modules.

### 11.2 Cache hit rate may drop

Workspace-scoped cache keys reduce cross-request reuse. That is the correct tradeoff because correctness and isolation matter more than global cache density.

### 11.3 SQLite remains acceptable for feature validation

This design can still be validated on SQLite, but it increases the eventual value of migrating business metadata and tenant-owned derived data into PostgreSQL later.

### 11.4 Premature SCIM or SAML would slow delivery

They are valid future capabilities, but they are not the right first step for this codebase's current stage.

---

## 12. Final Recommendation

Implement in this order:

1. First-party password + JWT + session auth foundation
2. organization-level governance and lifecycle
3. workspace-wide read/cache/storage isolation
4. SCIM later

This sequence is the best balance between:

- standards alignment
- commercial credibility
- repository fit
- implementation risk

It upgrades the current v2 access-control work into a credible platform foundation without turning the repo into an oversized IAM project too early.
