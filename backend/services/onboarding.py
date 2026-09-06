"""新用户开通编排（R1.1/R1.2 共用，2026-09-06）。

自助注册与社交登录都要「建 principal + 建 org + 建 workspace + 授双层 owner 资格」，
两者必须走同一段代码：否则社交登录首登建出来的账户会在权限语义上与密码注册账户悄悄
不同（这类差异没有报错，只会表现为「同一用户两种方式登进来看到不同界面」）。

全部资格授予都复用 ``access_control`` 里已有单测覆盖的 seed 函数，本模块只做编排与
前置约束，不新造权限写入路径。
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# 注册者拿到的资格：与既有「创建组织后唯一管理员」语义一致（org_owner + ws owner）。
REGISTRATION_ORG_ROLE = "org_owner"
REGISTRATION_WS_ROLE = "owner"
DEFAULT_WORKSPACE_NAME = "default"


def normalize_email(raw: str) -> str:
    """邮箱归一：小写 + 去空白。

    刻意不做 RFC 完备校验、也不去掉 ``+tag``：``+tag`` 是用户真实的邮箱别名习惯，
    拒掉它只会把人挡在门外；而 pydantic 的 ``EmailStr``/格式校验不是本模块的职责。
    唯一必须拒的是「没有 @」—— 它会直接撞进 ``access_control`` 里按域名判定授权的
    分支（``email.split("@")``），把一个畸形邮箱变成一条不确定的授权路径。
    """
    value = (raw or "").strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise HTTPException(status_code=422, detail="Invalid email address")
    return value


def assert_email_available(db, email: str) -> None:
    """邮箱占用检查。

    409 而不是 401/404：注册端点必然要泄露「该邮箱已存在」（否则无法提示用户换邮箱），
    这是产品决策而非缺陷。要收敛成防枚举，只能在「已存在时不发确认邮件、不发链接」
    这一侧收敛 —— 本模块正是这么做：占用即止，不产生任何挑战记录。

    detail 带 ``recovery``：经组织邀请进来的账户可能**没有密码**（历史上组织级邀请不
    设密码），这类用户看到「邮箱已被注册」会彻底卡住。出路一律给「登录或重置密码」，
    刻意不去区分「有没有密码」—— 那等于向未认证调用方披露账户的凭据形态。
    """
    if db.fetch_principal_by_email(email):
        raise HTTPException(status_code=409, detail={
            "message": "Email is already registered",
            "code": "email_taken",
            "recovery": "login_or_password_reset",
        })


def provision_account(db, *, email: str, display_name: str, password: str | None = None,
                      organization_name: str | None = None,
                      workspace_name: str = DEFAULT_WORKSPACE_NAME,
                      auth_method: str = "password") -> dict:
    """建账户与首个 org/ws，返回 ``{principal, organization, workspace}``。

    顺序是刻意的：先建 principal 再建 org/ws，最后授资格。中途失败（PG 报错）留下的
    孤立 principal 没有 membership，``_build_actor`` 会判为不完整上下文（401）→ 它
    既不是后门也不会被误授权；反过来先建 org 再失败会留下一个无人所有的组织。
    """
    from access_control import seed_principal, set_principal_password

    principal = seed_principal(db, email=email, display_name=display_name)
    if password:
        principal = set_principal_password(db, principal_id=principal["principal_id"], password=password)
    return attach_first_organization(
        db, principal=principal, organization_name=organization_name,
        workspace_name=workspace_name, auth_method=auth_method,
    )


def attach_first_organization(db, *, principal: dict, organization_name: str | None = None,
                              workspace_name: str = DEFAULT_WORKSPACE_NAME,
                              auth_method: str = "password") -> dict:
    """给一个**已存在**的 principal 建 org/ws 并授双层 owner。

    与 ``provision_account`` 分两个函数是为了社交登录：那条路径上 principal 可能早已
    存在（用户先用邮箱注册、后来才用 Google 登录），此时绝不能新建 principal。两条路径
    共用这一段，才能保证「密码注册的账户」与「社交登录的账户」在权限上完全同形。
    """
    from access_control import (
        seed_organization,
        seed_organization_membership,
        seed_workspace,
        seed_workspace_membership,
    )

    display_name = principal.get("display_name") or principal["email"]
    organization = seed_organization(db, name=organization_name or f"{display_name}'s organization")
    workspace = seed_workspace(db, organization_id=organization["organization_id"], name=workspace_name)
    seed_organization_membership(
        db,
        organization_id=organization["organization_id"],
        principal_id=principal["principal_id"],
        role=REGISTRATION_ORG_ROLE,
    )
    seed_workspace_membership(
        db,
        workspace_id=workspace["workspace_id"],
        principal_id=principal["principal_id"],
        role=REGISTRATION_WS_ROLE,
    )
    logger.info(
        "account provisioned: principal=%s org=%s ws=%s auth_method=%s",
        principal["principal_id"], organization["organization_id"],
        workspace["workspace_id"], auth_method,
    )
    return {"principal": principal, "organization": organization, "workspace": workspace}
