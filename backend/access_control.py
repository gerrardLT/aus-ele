from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import secrets
import uuid

from fastapi import HTTPException


ROLE_PERMISSIONS = {
    "owner": {"org_manage", "workspace_manage", "member_manage", "export", "read_audit"},
    "admin": {"workspace_manage", "member_manage", "export", "read_audit"},
    "analyst": {"export"},
    "viewer": set(),
    "exporter": {"export"},
}

ORG_ROLE_PERMISSIONS = {
    "org_owner": {"org_manage", "member_manage", "workspace_manage", "read_audit"},
    "org_admin": {"member_manage", "workspace_manage", "read_audit"},
    "org_billing_viewer": set(),
    "org_member": set(),
}


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso_datetime(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(normalized)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _jwt_secret() -> str:
    return os.environ.get("AUS_ELE_JWT_SECRET", "aus-ele-dev-jwt-secret")


def _access_token_ttl_seconds() -> int:
    return int(os.environ.get("AUS_ELE_ACCESS_TOKEN_TTL_SECONDS", "3600"))


def _session_ttl_seconds() -> int:
    return int(os.environ.get("AUS_ELE_SESSION_TTL_SECONDS", str(30 * 24 * 60 * 60)))


def _issue_jwt_access_token(*, token_id: str, principal_id: str, workspace_id: str, session_id: str | None, expires_at: datetime.datetime) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "jti": token_id,
        "sub": principal_id,
        "workspace_id": workspace_id,
        "iat": int(_utc_now().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if session_id:
        payload["session_id"] = session_id
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        ]
    )
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def _decode_and_verify_jwt_access_token(token: str) -> dict:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        actual_signature = _b64url_decode(signature_segment)
        header = json.loads(_b64url_decode(header_segment).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid access token")
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Invalid access token")
    if int(payload.get("exp", 0)) <= int(_utc_now().timestamp()):
        raise HTTPException(status_code=401, detail="Access token expired")
    return payload


def _write_audit(db, *, actor_principal_id=None, workspace_id=None, action: str, target_type: str, target_id: str, detail_json=None):
    db.insert_audit_log(
        {
            "actor_principal_id": actor_principal_id,
            "workspace_id": workspace_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "detail_json": detail_json or {},
            "created_at": _utc_now_iso(),
        }
    )


def _revoke_principal_auth_context(db, *, principal_id: str, organization_id: str):
    workspaces = db.list_workspaces(organization_id=organization_id)
    workspace_ids = [workspace["workspace_id"] for workspace in workspaces]
    sessions = db.list_auth_sessions_for_principal(
        principal_id,
        organization_id=organization_id,
        workspace_ids=workspace_ids or None,
    )
    for session in sessions:
        if not session.get("revoked"):
            db.upsert_auth_session({**session, "revoked": 1})
            _write_audit(
                db,
                actor_principal_id=principal_id,
                workspace_id=session.get("workspace_id"),
                action="auth.session_revoked",
                target_type="auth_session",
                target_id=session["session_id"],
                detail_json={"auth_method": session.get("auth_method"), "reason": "organization_membership_disabled"},
            )
    tokens = db.list_access_tokens_for_principal(principal_id, workspace_ids=workspace_ids or None)
    for token in tokens:
        if not token.get("revoked"):
            db.upsert_access_token({**token, "revoked": 1})
            _write_audit(
                db,
                actor_principal_id=principal_id,
                workspace_id=token.get("workspace_id"),
                action="access_token.revoked",
                target_type="access_token",
                target_id=token["token_id"],
                detail_json={"reason": "organization_membership_disabled"},
            )


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()


def _build_actor(db, *, principal_id: str, workspace_id: str, session: dict | None = None, token: dict | None = None) -> dict:
    principal = db.fetch_principal(principal_id)
    workspace = db.fetch_workspace(workspace_id)
    membership = db.fetch_workspace_membership(workspace_id, principal_id)
    if not principal or not workspace or not membership:
        raise HTTPException(status_code=401, detail="Incomplete authentication context")
    actor = {
        "principal": principal,
        "workspace": workspace,
        "membership": membership,
    }
    if session is not None:
        actor["session"] = session
    if token is not None:
        actor["token"] = token
    organization_id = workspace.get("organization_id")
    if organization_id:
        org_membership = db.fetch_organization_membership(organization_id, principal_id)
        if org_membership and org_membership.get("status") != "active":
            raise HTTPException(status_code=401, detail="Inactive organization membership")
        if org_membership is not None:
            actor["organization_membership"] = org_membership
    return actor


def seed_organization(db, *, name: str) -> dict:
    org = db.upsert_organization(
        {
            "organization_id": f"org_{uuid.uuid4().hex[:12]}",
            "name": name,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(db, action="organization.created", target_type="organization", target_id=org["organization_id"], detail_json={"name": name})
    return org


def seed_workspace(db, *, organization_id: str, name: str) -> dict:
    workspace = db.upsert_workspace(
        {
            "workspace_id": f"ws_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "name": name,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        workspace_id=workspace["workspace_id"],
        action="workspace.created",
        target_type="workspace",
        target_id=workspace["workspace_id"],
        detail_json={"name": name, "organization_id": organization_id},
    )
    return workspace


def seed_principal(db, *, email: str, display_name: str) -> dict:
    principal = db.upsert_principal(
        {
            "principal_id": f"pr_{uuid.uuid4().hex[:12]}",
            "email": email,
            "display_name": display_name,
            "password_hash": None,
            "password_salt": None,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(db, actor_principal_id=principal["principal_id"], action="principal.created", target_type="principal", target_id=principal["principal_id"], detail_json={"email": email})
    return principal


def seed_workspace_membership(db, *, workspace_id: str, principal_id: str, role: str) -> dict:
    membership = db.upsert_workspace_membership(
        {
            "membership_id": f"m_{uuid.uuid4().hex[:12]}",
            "workspace_id": workspace_id,
            "principal_id": principal_id,
            "role": role,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="workspace_membership.upserted",
        target_type="workspace_membership",
        target_id=membership["membership_id"],
        detail_json={"principal_id": principal_id, "role": role},
    )
    return membership


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


def issue_access_token(db, *, principal_id: str, workspace_id: str, session_id: str | None = None) -> dict:
    expires_at = _utc_now() + datetime.timedelta(seconds=_access_token_ttl_seconds())
    token_id = f"tok_{uuid.uuid4().hex[:12]}"
    jwt_token = _issue_jwt_access_token(
        token_id=token_id,
        principal_id=principal_id,
        workspace_id=workspace_id,
        session_id=session_id,
        expires_at=expires_at,
    )
    token = db.upsert_access_token(
        {
            "token_id": token_id,
            "token": jwt_token,
            "principal_id": principal_id,
            "workspace_id": workspace_id,
            "created_at": _utc_now_iso(),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "revoked": 0,
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="access_token.issued",
        target_type="access_token",
        target_id=token["token_id"],
        detail_json={"workspace_id": workspace_id, "session_id": session_id},
    )
    return {
        **token,
        "token_type": "Bearer",
        "expires_in": _access_token_ttl_seconds(),
    }


def set_principal_password(db, *, principal_id: str, password: str) -> dict:
    principal = db.fetch_principal(principal_id)
    if not principal:
        raise HTTPException(status_code=404, detail="Principal not found")
    salt = secrets.token_hex(16)
    updated = db.upsert_principal(
        {
            **principal,
            "password_salt": salt,
            "password_hash": _hash_password(password, salt),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="principal.password_set",
        target_type="principal",
        target_id=principal_id,
        detail_json={},
    )
    return updated


def link_auth_identity(db, *, principal_id: str, provider_key: str, subject: str, email: str, email_verified: bool) -> dict:
    existing = db.fetch_auth_identity_by_subject("oidc", provider_key, subject)
    if existing:
        return existing
    return db.upsert_auth_identity(
        {
            "auth_identity_id": f"ai_{uuid.uuid4().hex[:12]}",
            "principal_id": principal_id,
            "provider_type": "oidc",
            "provider_key": provider_key,
            "subject": subject,
            "email": email,
            "email_verified": int(bool(email_verified)),
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )


def resolve_principal_for_oidc_claims(db, *, provider_key: str, subject: str, email: str, email_verified: bool, display_name: str) -> dict:
    existing_identity = db.fetch_auth_identity_by_subject("oidc", provider_key, subject)
    if existing_identity:
        return {
            "principal": db.fetch_principal(existing_identity["principal_id"]),
            "auth_identity": existing_identity,
        }
    principal = db.fetch_principal_by_email(email)
    if principal is None:
        principal = seed_principal(db, email=email, display_name=display_name or email)
    identity = link_auth_identity(
        db,
        principal_id=principal["principal_id"],
        provider_key=provider_key,
        subject=subject,
        email=email,
        email_verified=email_verified,
    )
    return {
        "principal": principal,
        "auth_identity": identity,
    }


def login_with_password(db, *, email: str, password: str, workspace_id: str) -> dict:
    principal = db.fetch_principal_by_email(email)
    if not principal or not principal.get("password_hash") or not principal.get("password_salt"):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if _hash_password(password, principal["password_salt"]) != principal["password_hash"]:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    workspace = db.fetch_workspace(workspace_id)
    membership = db.fetch_workspace_membership(workspace_id, principal["principal_id"])
    if not workspace or not membership:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    organization_id = workspace.get("organization_id")
    if organization_id:
        org_membership = db.fetch_organization_membership(organization_id, principal["principal_id"])
        if not org_membership or org_membership.get("status") != "active":
            raise HTTPException(status_code=403, detail="Organization access denied")
    expires_at = _utc_now() + datetime.timedelta(seconds=_session_ttl_seconds())
    session = db.upsert_auth_session(
        {
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "session_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "principal_id": principal["principal_id"],
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "auth_method": "password",
            "created_at": _utc_now_iso(),
            "last_seen_at": _utc_now_iso(),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "revoked": 0,
        }
    )
    access_token = issue_access_token(
        db,
        principal_id=principal["principal_id"],
        workspace_id=workspace_id,
        session_id=session["session_id"],
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        workspace_id=workspace_id,
        action="auth.login",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={"email": email},
    )
    return {
        **session,
        "access_token": access_token["token"],
        "token_type": access_token["token_type"],
        "access_token_expires_at": access_token["expires_at"],
        "access_token_expires_in": access_token["expires_in"],
    }


def issue_oidc_session(db, *, principal_id: str, organization_id: str, workspace_id: str, auth_identity_id: str, auth_method: str = "oidc") -> dict:
    session = db.upsert_auth_session(
        {
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "session_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "principal_id": principal_id,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "auth_identity_id": auth_identity_id,
            "auth_method": auth_method,
            "created_at": _utc_now_iso(),
            "last_seen_at": _utc_now_iso(),
            "expires_at": None,
            "revoked": 0,
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        workspace_id=workspace_id,
        action="auth.oidc_login",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={"organization_id": organization_id, "auth_identity_id": auth_identity_id},
    )
    return session


def authenticate_org_actor(db, organization_id: str, principal_id: str) -> dict:
    organization = db.fetch_organization(organization_id)
    principal = db.fetch_principal(principal_id)
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not organization or not principal or not membership or membership.get("status") != "active":
        raise HTTPException(status_code=401, detail="Invalid organization actor")
    return {
        "organization": organization,
        "principal": principal,
        "organization_membership": membership,
    }


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
    return True


def authenticate_access_token(db, token: str | None) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    claims = _decode_and_verify_jwt_access_token(token)
    token_row = db.fetch_access_token_by_value(token)
    if not token_row or token_row.get("revoked"):
        raise HTTPException(status_code=401, detail="Invalid access token")
    expires_at = _parse_iso_datetime(token_row.get("expires_at"))
    if expires_at and expires_at <= _utc_now():
        raise HTTPException(status_code=401, detail="Access token expired")
    if claims.get("sub") != token_row["principal_id"] or claims.get("workspace_id") != token_row["workspace_id"]:
        raise HTTPException(status_code=401, detail="Invalid access token")
    session = None
    session_id = claims.get("session_id")
    if session_id:
        session = db.fetch_auth_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=401, detail="Invalid access token")
        if session.get("revoked"):
            raise HTTPException(status_code=401, detail="Session revoked")
        if session["principal_id"] != token_row["principal_id"] or session["workspace_id"] != token_row["workspace_id"]:
            raise HTTPException(status_code=401, detail="Invalid access token")
        session_expires_at = _parse_iso_datetime(session.get("expires_at"))
        if session_expires_at and session_expires_at <= _utc_now():
            raise HTTPException(status_code=401, detail="Session expired")
    return _build_actor(db, principal_id=token_row["principal_id"], workspace_id=token_row["workspace_id"], token=token_row, session=session)


def authenticate_session_token(db, session_token: str | None) -> dict:
    if not session_token:
        raise HTTPException(status_code=401, detail="Missing session token")
    session = db.fetch_auth_session_by_token(session_token)
    if not session or session.get("revoked"):
        raise HTTPException(status_code=401, detail="Invalid session token")
    expires_at = _parse_iso_datetime(session.get("expires_at"))
    if expires_at and expires_at <= _utc_now():
        raise HTTPException(status_code=401, detail="Session expired")
    return _build_actor(db, principal_id=session["principal_id"], workspace_id=session["workspace_id"], session=session)


def refresh_session_access_token(db, session_token: str) -> dict:
    actor = authenticate_session_token(db, session_token)
    session = actor["session"]
    access_token = issue_access_token(
        db,
        principal_id=session["principal_id"],
        workspace_id=session["workspace_id"],
        session_id=session["session_id"],
    )
    updated_session = db.upsert_auth_session(
        {
            **session,
            "last_seen_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=session["principal_id"],
        workspace_id=session["workspace_id"],
        action="auth.refresh",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={},
    )
    return {
        **updated_session,
        "access_token": access_token["token"],
        "token_type": access_token["token_type"],
        "access_token_expires_at": access_token["expires_at"],
        "access_token_expires_in": access_token["expires_in"],
    }


def logout_session(db, session_token: str):
    session = db.fetch_auth_session_by_token(session_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.upsert_auth_session({**session, "revoked": 1})
    _write_audit(
        db,
        actor_principal_id=session["principal_id"],
        workspace_id=session["workspace_id"],
        action="auth.session_revoked",
        target_type="auth_session",
        target_id=session["session_id"],
        detail_json={"auth_method": session.get("auth_method")},
    )


def check_organization_permission(actor: dict, permission: str):
    role = actor["organization_membership"]["role"]
    permissions = ORG_ROLE_PERMISSIONS.get(role, set())
    if permission not in permissions:
        raise HTTPException(status_code=403, detail="Organization permission denied")
    return True


def create_membership_invite(
    db,
    *,
    actor: dict,
    organization_id: str,
    workspace_id: str | None,
    target_scope_type: str,
    email: str,
    target_role: str,
    expires_at: str | None,
) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    normalized_email = email.strip().lower()
    existing_pending = db.list_membership_invites(
        organization_id,
        workspace_id=workspace_id,
        status="pending",
        email=normalized_email,
    )
    if existing_pending:
        return existing_pending[0]
    invite = db.upsert_membership_invite(
        {
            "invite_id": f"inv_{uuid.uuid4().hex[:12]}",
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_scope_type": target_scope_type,
            "email": normalized_email,
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
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="membership_invite.created",
        target_type="membership_invite",
        target_id=invite["invite_id"],
        detail_json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_scope_type": target_scope_type,
            "email": invite["email"],
            "target_role": target_role,
        },
    )
    return invite


def revoke_membership_invite(db, *, actor: dict, invite_id: str, revoke_reason: str | None) -> dict:
    invite = db.fetch_membership_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if actor["organization"]["organization_id"] != invite["organization_id"]:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    if invite.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invite is not revocable")
    updated = db.upsert_membership_invite(
        {
            **invite,
            "status": "revoked",
            "revoked_by_principal_id": actor["principal"]["principal_id"],
            "revoked_at": _utc_now_iso(),
            "revoke_reason": revoke_reason,
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="membership_invite.revoked",
        target_type="membership_invite",
        target_id=invite_id,
        detail_json={"organization_id": invite["organization_id"], "revoke_reason": revoke_reason},
    )
    return updated


def reissue_membership_invite(db, *, actor: dict, invite_id: str, expires_at: str | None) -> dict:
    invite = db.fetch_membership_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if actor["organization"]["organization_id"] != invite["organization_id"]:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    if invite.get("status") == "accepted":
        raise HTTPException(status_code=400, detail="Accepted invite cannot be reissued")
    updated_at = _utc_now_iso()
    updated = db.upsert_membership_invite(
        {
            **invite,
            "invite_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "status": "pending",
            "accepted_by_principal_id": None,
            "revoked_by_principal_id": None,
            "expires_at": expires_at,
            "accepted_at": None,
            "revoked_at": None,
            "revoke_reason": None,
            "updated_at": updated_at,
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="membership_invite.reissued",
        target_type="membership_invite",
        target_id=invite_id,
        detail_json={"organization_id": invite["organization_id"], "expires_at": expires_at},
    )
    return updated


def accept_membership_invite(db, *, invite_token: str, display_name: str) -> dict:
    invite = db.fetch_membership_invite_by_token(invite_token)
    if not invite or invite.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invite is not valid")
    expires_at = _parse_iso_datetime(invite.get("expires_at"))
    if expires_at and expires_at <= _utc_now():
        raise HTTPException(status_code=400, detail="Invite has expired")
    principal = db.fetch_principal_by_email(invite["email"])
    if not principal:
        principal = seed_principal(db, email=invite["email"], display_name=display_name)
    elif display_name and principal.get("display_name") != display_name:
        principal = db.upsert_principal({**principal, "display_name": display_name, "updated_at": _utc_now_iso()})
    accepted_at = _utc_now_iso()
    updated_invite = db.upsert_membership_invite(
        {
            **invite,
            "status": "accepted",
            "accepted_by_principal_id": principal["principal_id"],
            "accepted_at": accepted_at,
            "updated_at": accepted_at,
        }
    )
    org_membership = seed_organization_membership(
        db,
        organization_id=invite["organization_id"],
        principal_id=principal["principal_id"],
        role=invite["target_role"],
        status="active",
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        action="membership_invite.accepted",
        target_type="membership_invite",
        target_id=invite["invite_id"],
        detail_json={"organization_id": invite["organization_id"], "organization_membership_id": org_membership["organization_membership_id"]},
    )
    return {
        "invite": updated_invite,
        "principal": principal,
        "organization_membership": org_membership,
    }


def ensure_organization_membership_from_domain_policy(
    db,
    *,
    organization_id: str,
    principal_id: str,
    email: str,
) -> tuple[dict, dict, bool]:
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=400, detail="Invalid email")
    domain = normalized_email.split("@", 1)[-1]
    domain_record = db.fetch_organization_domain_by_name(domain)
    if not domain_record or domain_record["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization domain mismatch")

    membership = db.fetch_organization_membership(organization_id, principal_id)
    if membership:
        if membership.get("status") != "active":
            raise HTTPException(status_code=403, detail="Organization access denied")
        return membership, domain_record, False

    if domain_record.get("join_mode") != "domain_auto_join_org":
        raise HTTPException(status_code=403, detail="Organization invite required")

    membership = seed_organization_membership(
        db,
        organization_id=organization_id,
        principal_id=principal_id,
        role="org_member",
        status="active",
    )
    _write_audit(
        db,
        actor_principal_id=principal_id,
        action="organization_membership.auto_joined",
        target_type="organization_membership",
        target_id=membership["organization_membership_id"],
        detail_json={"organization_id": organization_id, "domain": domain},
    )
    return membership, domain_record, True


def _list_principal_workspace_memberships_in_organization(db, *, organization_id: str, principal_id: str) -> list[dict]:
    items = []
    for workspace in db.list_workspaces(organization_id=organization_id):
        membership = db.fetch_workspace_membership(workspace["workspace_id"], principal_id)
        if membership:
            items.append(
                {
                    "workspace": workspace,
                    "membership": membership,
                }
            )
    return items


def join_organization_by_domain(
    db,
    *,
    organization_id: str,
    email: str,
    display_name: str,
    password: str,
) -> dict:
    organization = db.fetch_organization(organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=400, detail="Invalid email")

    principal = db.fetch_principal_by_email(normalized_email)
    if principal is None:
        principal = seed_principal(db, email=normalized_email, display_name=display_name or normalized_email)
    else:
        if principal.get("password_hash") and principal.get("password_salt"):
            if _hash_password(password, principal["password_salt"]) != principal["password_hash"]:
                raise HTTPException(status_code=401, detail="Invalid email or password")
        if display_name and principal.get("display_name") != display_name:
            principal = db.upsert_principal({**principal, "display_name": display_name, "updated_at": _utc_now_iso()})

    if not principal.get("password_hash") or not principal.get("password_salt"):
        principal = set_principal_password(db, principal_id=principal["principal_id"], password=password)

    org_membership, domain_record, auto_joined = ensure_organization_membership_from_domain_policy(
        db,
        organization_id=organization_id,
        principal_id=principal["principal_id"],
        email=normalized_email,
    )
    workspace_memberships = _list_principal_workspace_memberships_in_organization(
        db,
        organization_id=organization_id,
        principal_id=principal["principal_id"],
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        action="auth.domain_join",
        target_type="organization",
        target_id=organization_id,
        detail_json={
            "domain": domain_record["domain"],
            "auto_joined": auto_joined,
            "workspace_access_ready": bool(workspace_memberships),
        },
    )
    return {
        "organization": organization,
        "principal": principal,
        "organization_membership": org_membership,
        "workspace_memberships": workspace_memberships,
        "workspace_access_ready": bool(workspace_memberships),
    }


def suspend_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    if membership.get("role") == "org_owner":
        raise HTTPException(status_code=400, detail="Org owner cannot be suspended")
    updated = db.upsert_organization_membership({**membership, "status": "suspended", "updated_at": _utc_now_iso()})
    _revoke_principal_auth_context(db, principal_id=principal_id, organization_id=organization_id)
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.suspended",
        target_type="organization_membership",
        target_id=updated["organization_membership_id"],
        detail_json={"organization_id": organization_id, "principal_id": principal_id},
    )
    return updated


def reactivate_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    updated = db.upsert_organization_membership({**membership, "status": "active", "updated_at": _utc_now_iso()})
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.reactivated",
        target_type="organization_membership",
        target_id=updated["organization_membership_id"],
        detail_json={"organization_id": organization_id, "principal_id": principal_id},
    )
    return updated


def remove_organization_member(db, *, actor: dict, organization_id: str, principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(actor, "member_manage")
    membership = db.fetch_organization_membership(organization_id, principal_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    if membership.get("role") == "org_owner":
        raise HTTPException(status_code=400, detail="Org owner cannot be removed")
    updated = db.upsert_organization_membership({**membership, "status": "removed", "updated_at": _utc_now_iso()})
    _revoke_principal_auth_context(db, principal_id=principal_id, organization_id=organization_id)
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.removed",
        target_type="organization_membership",
        target_id=updated["organization_membership_id"],
        detail_json={"organization_id": organization_id, "principal_id": principal_id},
    )
    return updated


def transfer_organization_owner(db, *, actor: dict, organization_id: str, new_owner_principal_id: str) -> dict:
    if actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    if actor["organization_membership"]["role"] != "org_owner":
        raise HTTPException(status_code=403, detail="Only org owner can transfer ownership")
    previous_owner = db.fetch_organization_membership(organization_id, actor["principal"]["principal_id"])
    new_owner = db.fetch_organization_membership(organization_id, new_owner_principal_id)
    if not previous_owner or not new_owner:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    updated_previous = db.upsert_organization_membership(
        {**previous_owner, "role": "org_admin", "updated_at": _utc_now_iso()}
    )
    updated_new = db.upsert_organization_membership(
        {**new_owner, "role": "org_owner", "status": "active", "updated_at": _utc_now_iso()}
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        action="organization_membership.owner_transferred",
        target_type="organization",
        target_id=organization_id,
        detail_json={"previous_owner_principal_id": actor["principal"]["principal_id"], "new_owner_principal_id": new_owner_principal_id},
    )
    return {"previous_owner": updated_previous, "new_owner": updated_new}


def create_workspace_invite(db, *, actor: dict, workspace_id: str, email: str, role: str) -> dict:
    if actor["workspace"]["workspace_id"] != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    check_workspace_permission(actor, "member_manage")
    invite = db.upsert_workspace_invite(
        {
            "invite_id": f"inv_{uuid.uuid4().hex[:12]}",
            "workspace_id": workspace_id,
            "email": email.strip().lower(),
            "role": role,
            "invite_token": uuid.uuid4().hex + uuid.uuid4().hex,
            "invited_by_principal_id": actor["principal"]["principal_id"],
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "revoked": 0,
            "accepted_at": None,
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        workspace_id=workspace_id,
        action="workspace_invite.created",
        target_type="workspace_invite",
        target_id=invite["invite_id"],
        detail_json={"email": invite["email"], "role": role},
    )
    return invite


def revoke_workspace_invite(db, *, actor: dict, invite_id: str) -> dict:
    invite = db.fetch_workspace_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if actor["workspace"]["workspace_id"] != invite["workspace_id"]:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    check_workspace_permission(actor, "member_manage")
    updated = db.upsert_workspace_invite(
        {
            **invite,
            "revoked": 1,
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=actor["principal"]["principal_id"],
        workspace_id=invite["workspace_id"],
        action="workspace_invite.revoked",
        target_type="workspace_invite",
        target_id=invite_id,
        detail_json={"email": invite["email"]},
    )
    return updated


def accept_workspace_invite(db, *, invite_token: str, display_name: str, password: str) -> dict:
    invite = db.fetch_workspace_invite_by_token(invite_token)
    if not invite or invite.get("revoked") or invite.get("accepted_at"):
        raise HTTPException(status_code=400, detail="Invite is not valid")
    principal = db.fetch_principal_by_email(invite["email"])
    if not principal:
        principal = seed_principal(db, email=invite["email"], display_name=display_name)
    elif display_name and principal.get("display_name") != display_name:
        principal = db.upsert_principal({**principal, "display_name": display_name, "updated_at": _utc_now_iso()})
    principal = set_principal_password(db, principal_id=principal["principal_id"], password=password)
    membership = seed_workspace_membership(
        db,
        workspace_id=invite["workspace_id"],
        principal_id=principal["principal_id"],
        role=invite["role"],
    )
    updated_invite = db.upsert_workspace_invite(
        {
            **invite,
            "accepted_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    _write_audit(
        db,
        actor_principal_id=principal["principal_id"],
        workspace_id=invite["workspace_id"],
        action="workspace_invite.accepted",
        target_type="workspace_invite",
        target_id=invite["invite_id"],
        detail_json={"membership_id": membership["membership_id"]},
    )
    return {
        "invite": updated_invite,
        "principal": principal,
        "workspace": db.fetch_workspace(invite["workspace_id"]),
        "membership": membership,
    }


def check_workspace_permission(actor: dict, permission: str):
    role = actor["membership"]["role"]
    permissions = ROLE_PERMISSIONS.get(role, set())
    if permission not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied")
    return True
