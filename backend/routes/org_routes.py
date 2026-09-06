"""组织自助管理端点（R1.4，2026-09-06）。

前缀 ``/api/v1/organizations``，与 ``server.py`` 的 ``/api/admin/organizations/*`` 分离。
为什么要另开一套而不是复用 admin 端点：

1. admin 端点的语义是「平台管理员跨租户操作」，其鉴权走 ``_resolve_admin_principal_id``
   —— 在**没有** Bearer 令牌时（进程内直调、引导脚本）会放行并保持旧行为。这个默认宽松
   对内部运维是对的，放到公网自助界面上就是「忘记带令牌 = 不需要令牌」。本模块每个写端点
   都要求真实 Bearer 且拒绝匿名 bootstrap 身份（``assert_human_actor``），没有进程内旁路。
2. 请求体：admin 端点全用 query 参数（含邮箱、角色、到期时间）。邮箱与 token 进 URL 会
   落到访问日志、Referer 与浏览器历史里；自助界面不该继承这个。这里一律 JSON body。
3. 只暴露调用者**自己所在组织**的视图：所有端点先 ``authenticate_org_actor`` 把
   principal_id 与该 organization 绑在一起（非成员一律 401，组织不存在也是 401 ——
   刻意不区分，否则这个端点就成了「探测某个 organization_id 是否存在」的Oracle），
   权限再按 ``check_organization_permission`` 逐项判定 —— 与后端既有 RBAC 表完全一致，
   本模块不新增任何权限语义。

审计 action 名沿用既有字面量（``organization.*`` 由 access_control 内部写入），
本模块不自造 action 串，避免审计流水按入口分叉。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from access_control import (
    ROLE_PERMISSIONS,
    DomainVerificationUnavailable,
    accept_membership_invite,
    authenticate_org_actor,
    check_organization_permission,
    create_membership_invite,
    reactivate_organization_member,
    register_organization_domain,
    reissue_membership_invite,
    remove_organization_member,
    revoke_membership_invite,
    suspend_organization_member,
    transfer_organization_owner,
    verify_organization_domain,
    begin_domain_verification,
)
from deps import get_db
from routes.account_routes import _assert_human_write, _get_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])

# 组织级可邀请角色。刻意不含 org_owner：owner 只能通过 transfer_organization_owner
# 产生，否则一次误操作邀请就能把别人的组织送出去。
INVITABLE_ORG_ROLES = {"org_admin", "org_billing_viewer", "org_member"}

# 接受组织邀请时落地用的工作空间角色。必须是 ``ROLE_PERMISSIONS`` 的键：
# ``check_workspace_permission`` 是按角色名查表的，写错不会抛错，只会静默给出一张
# 空权限卡 —— 那种「登得进来但什么都干不了」的账户是最难从工单反查的一类故障。
# 更高的权限由管理员事后在工作空间成员页调整，不借邀请 token 授予。
INVITE_WORKSPACE_ROLE = "viewer"
# 用 raise 而不是 assert：`python -O` 会把 assert 整条剥离，那时这道检查就不存在了。
if INVITE_WORKSPACE_ROLE not in ROLE_PERMISSIONS:
    raise RuntimeError(
        f"INVITE_WORKSPACE_ROLE={INVITE_WORKSPACE_ROLE!r} 不在后端工作空间角色表里"
    )


# ---------------------------------------------------------------------------
# 请求模型（全部 JSON body —— 见模块 docstring 第 2 点）
# ---------------------------------------------------------------------------


class OrgInviteCreateRequest(BaseModel):
    email: str = Field(..., description="受邀人邮箱")
    target_role: str = Field("org_member", description="组织角色：org_admin/org_billing_viewer/org_member")
    expires_at: Optional[str] = Field(None, description="ISO 到期时间，缺省由后端按默认窗口签发")
    workspace_id: Optional[str] = Field(
        None,
        description="可选：接受邀请时顺便落地到该工作空间（viewer）。缺省自动取本组织任一个空间",
    )


class InviteReissueRequest(BaseModel):
    expires_at: Optional[str] = Field(None, description="新到期时间")


class InviteRevokeRequest(BaseModel):
    revoke_reason: str = Field("manual_revoke", max_length=120)


class OrgInviteAcceptRequest(BaseModel):
    invite_token: str = Field(..., description="邀请 token")
    display_name: str = Field(..., min_length=1, max_length=120)
    password: Optional[str] = Field(None, description="设置密码；建议始终提供（与空间级邀请对齐）")


class OwnerTransferRequest(BaseModel):
    new_owner_principal_id: str = Field(..., description="新 owner 的 principal_id")


class DomainCreateRequest(BaseModel):
    domain: str = Field(..., max_length=253)
    join_mode: str = Field("invite_only", description="invite_only / domain_auto_join_org")


class DomainVerificationBeginRequest(BaseModel):
    method: str = Field("dns_txt", description="dns_txt | email（与 DOMAIN_VERIFICATION_METHODS 一致）")


class DomainVerificationConfirmRequest(BaseModel):
    method: str = Field(..., description="dns_txt | email")
    token: Optional[str] = Field(None, description="email 方式下为收到的挑战串；dns_txt 无需传")


# ---------------------------------------------------------------------------
# 守卫与视图
# ---------------------------------------------------------------------------


def _org_actor(db, actor: dict, organization_id: str) -> dict:
    """把「令牌里的这个人」解析为「该组织的成员身份」，非成员 401。

    必须用令牌里的 principal_id，绝不接受调用方自报的 ``principal_id`` 参数 ——
    admin 端点那套 ``_resolve_admin_principal_id`` 的回落正是这里要避开的。
    401（而非 403）来自 ``authenticate_org_actor`` 的既有语义：组织不存在与
    非成员返回同一个码，避免成为 organization_id 枚举探针。
    """
    return authenticate_org_actor(db, organization_id, actor["principal"]["principal_id"])


def _require_org_permission(org_actor: dict, organization_id: str, permission: str) -> None:
    if org_actor["organization"]["organization_id"] != organization_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    check_organization_permission(org_actor, permission)


def _domain_view(row: dict) -> dict:
    """组织域名的对外视图 —— **绝不含 verification_token**。

    那个 token 是「谁拥有这个域名」的证明物；一旦能从任何读取接口取出，拿到只读权限的人
    就能直接完成验证挑战，P0.3 的整条信任锚修复随之作废。与 server 侧同名视图保持一致。
    """
    return {
        "domain_id": row["domain_id"],
        "organization_id": row["organization_id"],
        "domain": row["domain"],
        "join_mode": row["join_mode"],
        "verified": bool(row.get("verified")),
        "verified_at": row.get("verified_at"),
        "verification_requested_at": row.get("verification_requested_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _member_view(db, membership: dict) -> dict:
    return {**membership, "principal": db.fetch_principal(membership["principal_id"])}


# ---------------------------------------------------------------------------
# 我的组织清单
# ---------------------------------------------------------------------------


@router.get("")
def list_my_organizations(actor: dict = Depends(_get_actor)):
    """当前 principal 所属的全部组织（供前端「没有可管理组织」的空态判断）。"""
    db = get_db()
    principal_id = actor["principal"]["principal_id"]
    seen: dict[str, dict] = {}
    for membership in db.list_workspace_memberships_by_principal(principal_id):
        ws = db.fetch_workspace(membership["workspace_id"])
        organization_id = (ws or {}).get("organization_id")
        if not organization_id or organization_id in seen:
            continue
        org = db.fetch_organization(organization_id)
        org_membership = db.fetch_organization_membership(organization_id, principal_id)
        seen[organization_id] = {
            "organization_id": organization_id,
            "name": (org or {}).get("name"),
            "organization_role": (org_membership or {}).get("role"),
        }
    return {"items": list(seen.values())}


@router.get("/{organization_id}")
def get_organization(organization_id: str, actor: dict = Depends(_get_actor)):
    """组织概览：名称、我的角色、成员数、工作空间清单。任何组织成员可读。"""
    db = get_db()
    org_actor = _org_actor(db, actor, organization_id)
    org = db.fetch_organization(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    members = db.list_organization_memberships(organization_id)
    workspaces = db.list_workspaces(organization_id=organization_id)
    return {
        "organization_id": organization_id,
        "name": org.get("name"),
        "created_at": org.get("created_at"),
        "my_role": org_actor["organization_membership"]["role"],
        "member_count": len(members),
        "workspaces": [
            {"workspace_id": ws["workspace_id"], "name": ws.get("name")} for ws in workspaces
        ],
    }


# ---------------------------------------------------------------------------
# 成员
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/members")
def list_members(organization_id: str, actor: dict = Depends(_get_actor)):
    """成员名册（含邮箱与显示名）。要求 member_manage：名册本身就是组织架构信息，
    org_member 无权据此枚举同事邮箱。"""
    db = get_db()
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    items = [_member_view(db, m) for m in db.list_organization_memberships(organization_id)]
    return {"organization_id": organization_id, "items": items, "total": len(items)}


@router.post("/{organization_id}/members/{principal_id}/suspend")
def suspend_member(
    organization_id: str, principal_id: str, actor: dict = Depends(_get_actor)
):
    db = get_db()
    _assert_human_write(actor, action="organization.member_suspend")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    return suspend_organization_member(
        db, actor=org_actor, organization_id=organization_id, principal_id=principal_id
    )


@router.post("/{organization_id}/members/{principal_id}/reactivate")
def reactivate_member(
    organization_id: str, principal_id: str, actor: dict = Depends(_get_actor)
):
    db = get_db()
    _assert_human_write(actor, action="organization.member_reactivate")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    return reactivate_organization_member(
        db, actor=org_actor, organization_id=organization_id, principal_id=principal_id
    )


@router.post("/{organization_id}/members/{principal_id}/remove")
def remove_member(organization_id: str, principal_id: str, actor: dict = Depends(_get_actor)):
    db = get_db()
    _assert_human_write(actor, action="organization.member_remove")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    return remove_organization_member(
        db, actor=org_actor, organization_id=organization_id, principal_id=principal_id
    )


@router.post("/{organization_id}/owner-transfer")
def transfer_owner(
    organization_id: str, body: OwnerTransferRequest, actor: dict = Depends(_get_actor)
):
    """移交 owner。要求 org_manage —— 只有 org_owner 持有该项，故不可能被 org_admin 反夺。"""
    db = get_db()
    _assert_human_write(actor, action="organization.owner_transfer")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "org_manage")
    return transfer_organization_owner(
        db,
        actor=org_actor,
        organization_id=organization_id,
        new_owner_principal_id=body.new_owner_principal_id,
    )


# ---------------------------------------------------------------------------
# 邀请
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/invites")
def list_invites(
    organization_id: str, status: Optional[str] = None, actor: dict = Depends(_get_actor)
):
    db = get_db()
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    items = db.list_membership_invites(organization_id, status=status)
    return {"organization_id": organization_id, "items": items, "total": len(items)}


@router.post("/{organization_id}/invites")
def create_invite(
    organization_id: str, body: OrgInviteCreateRequest, actor: dict = Depends(_get_actor)
):
    db = get_db()
    _assert_human_write(actor, action="organization.invite_create")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    target_role = (body.target_role or "org_member").strip()
    if target_role not in INVITABLE_ORG_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported organization role: {target_role}",
        )
    landing_workspace_id = body.workspace_id or None
    if landing_workspace_id:
        # 必须校验归属：否则邀请行会带上别组织的 workspace_id，受邀人一接受就被塞进
        # 那个空间（接受端点只按 invite 里的 workspace_id 落地，不再复查组织）。
        target_ws = db.fetch_workspace(landing_workspace_id)
        if not target_ws or target_ws.get("organization_id") != organization_id:
            raise HTTPException(
                status_code=400, detail="Workspace not found in this organization"
            )
    return create_membership_invite(
        db,
        actor=org_actor,
        organization_id=organization_id,
        workspace_id=landing_workspace_id,
        target_scope_type="organization",
        email=body.email,
        target_role=target_role,
        expires_at=body.expires_at,
    )


@router.post("/{organization_id}/invites/{invite_id}/revoke")
def revoke_invite(
    organization_id: str, invite_id: str, body: InviteRevokeRequest, actor: dict = Depends(_get_actor)
):
    db = get_db()
    _assert_human_write(actor, action="organization.invite_revoke")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    return revoke_membership_invite(
        db, actor=org_actor, invite_id=invite_id, revoke_reason=body.revoke_reason
    )


@router.post("/{organization_id}/invites/{invite_id}/reissue")
def reissue_invite(
    organization_id: str, invite_id: str, body: InviteReissueRequest, actor: dict = Depends(_get_actor)
):
    db = get_db()
    _assert_human_write(actor, action="organization.invite_reissue")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "member_manage")
    return reissue_membership_invite(
        db, actor=org_actor, invite_id=invite_id, expires_at=body.expires_at
    )


@router.post("/invites/accept")
def accept_invite(body: OrgInviteAcceptRequest, request: Request = None):
    """接受组织级邀请（无需先登录）。

    限流复用 ``check_invite_accept_rate_limit``：它按 ``invite_token + IP`` 计窗，而组织级
    邀请与工作空间级邀请的 token 形状相同（``uuid4().hex * 2``），所以复用同一函数即等价
    保护，不必另开一套计数器 —— 另开反而会让攻击者的预算翻倍。

    ``also_join_workspace=True`` 是这条链路能用的前提：只建组织成员身份的账户在
    ``account_login`` 那里取不到任何 workspace，会被回以 401「邮箱或密码错误」——
    受邀者刚设完密码就被告知密码错，且没有 UI 能自救。落地角色固定 viewer（见
    ``INVITE_WORKSPACE_ROLE``），更高权限由管理员事后在工作空间成员页调整。
    """
    from routes.account_routes import check_invite_accept_rate_limit
    from routes.auth_routes import _client_ip

    check_invite_accept_rate_limit(body.invite_token, _client_ip(request))
    db = get_db()
    return accept_membership_invite(
        db,
        invite_token=body.invite_token,
        display_name=body.display_name,
        password=body.password,
        also_join_workspace=True,
        workspace_role=INVITE_WORKSPACE_ROLE,
    )


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/audit-logs")
def list_audit_logs(
    organization_id: str,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    limit: int = 100,
    actor: dict = Depends(_get_actor),
):
    """本组织审计流水。要求 read_audit。

    ``fetch_audit_logs`` 没有 organization 维度参数，因此先取再按 detail_json 过滤，
    与 server 侧 admin 端点同法。副作用是 ``limit`` 是**过滤前**的条数 —— 对自助界面
    来说宁可少显示，也不能把别的组织一行不漏地读进内存再丢掉。
    """
    db = get_db()
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "read_audit")
    capped = max(1, min(int(limit or 100), 500))
    rows = db.fetch_audit_logs(
        action=action, target_type=target_type, limit=min(capped * 5, 2000)
    )
    items = []
    for item in rows:
        detail = item.get("detail_json") or {}
        belongs = detail.get("organization_id") == organization_id or (
            item.get("target_type") == "organization" and item.get("target_id") == organization_id
        )
        if belongs:
            items.append(item)
        if len(items) >= capped:
            break
    return {"organization_id": organization_id, "items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# 域名（P0.3 信任锚的自助入口）
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/domains")
def list_domains(organization_id: str, actor: dict = Depends(_get_actor)):
    db = get_db()
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "org_manage")
    items = [_domain_view(row) for row in db.list_organization_domains(organization_id)]
    return {"organization_id": organization_id, "items": items}


@router.post("/{organization_id}/domains")
def create_domain(
    organization_id: str, body: DomainCreateRequest, actor: dict = Depends(_get_actor)
):
    """登记组织域名。**登记不等于授权** —— 新记录一律未验证，未验证域名不会带来自动入组。"""
    db = get_db()
    _assert_human_write(actor, action="organization.domain_register")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "org_manage")
    row = register_organization_domain(
        db,
        organization_id=organization_id,
        domain=body.domain,
        join_mode=body.join_mode,
        actor_principal_id=actor["principal"]["principal_id"],
    )
    return _domain_view(row)


@router.post("/{organization_id}/domains/{domain_id}/verification")
def begin_domain_verification_route(
    organization_id: str,
    domain_id: str,
    body: DomainVerificationBeginRequest,
    actor: dict = Depends(_get_actor),
):
    """发起所有权挑战。邮件方式下 token 只投递到域名方邮箱，不回 API。"""
    db = get_db()
    _assert_human_write(actor, action="organization.domain_verify_begin")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "org_manage")
    try:
        return begin_domain_verification(
            db,
            organization_id=organization_id,
            domain_id=domain_id,
            method=body.method,
            actor_principal_id=actor["principal"]["principal_id"],
        )
    except DomainVerificationUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.post("/{organization_id}/domains/{domain_id}/verification/verify")
def verify_domain_route(
    organization_id: str,
    domain_id: str,
    body: DomainVerificationConfirmRequest,
    actor: dict = Depends(_get_actor),
):
    db = get_db()
    _assert_human_write(actor, action="organization.domain_verify_confirm")
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "org_manage")
    try:
        row = verify_organization_domain(
            db,
            organization_id=organization_id,
            domain_id=domain_id,
            method=body.method,
            token=body.token,
            actor_principal_id=actor["principal"]["principal_id"],
        )
    except DomainVerificationUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return _domain_view(row)


# ---------------------------------------------------------------------------
# 工作空间（组织视图下：只列，不建 —— 建空间属 R1.4 之后的迭代）
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/workspaces")
def list_workspaces(organization_id: str, actor: dict = Depends(_get_actor)):
    """本组织工作空间清单。要求 workspace_manage（组织层的跨空间视野）。"""
    db = get_db()
    org_actor = _org_actor(db, actor, organization_id)
    _require_org_permission(org_actor, organization_id, "workspace_manage")
    items = []
    for ws in db.list_workspaces(organization_id=organization_id):
        membership = db.fetch_workspace_membership(
            ws["workspace_id"], actor["principal"]["principal_id"]
        )
        items.append(
            {
                "workspace_id": ws["workspace_id"],
                "name": ws.get("name"),
                "created_at": ws.get("created_at"),
                "my_workspace_role": (membership or {}).get("role"),
            }
        )
    return {"organization_id": organization_id, "items": items}
