"""账户数据权利端点（R1.7，2026-09-06）：自助导出 + 软删除 + 宽限期撤销。

前缀沿用 ``/api/v1/account``（``account_routes`` 已占该前缀，但 ``/export``、``/delete``
两条路径在其中不存在 → 无碰撞）。为什么不另起前缀：Spec 的验收口径就是
``POST /account/export`` 与 ``POST /account/delete``，而账户中心前端已经在同一个 API 基
路径下取数，换个前缀只会让「哪个端点属于账户」这件事在代码里出现两种答案。

三条鉴权纪律，逐条都是必要的：

1. 每个端点都要真实 Bearer（``_get_actor``），且写端点再过一道 ``_assert_human_write``
   —— 匿名 bootstrap 身份（``pr_websession``）绝不能触发导出别人的账户，更不能提交删除。
2. **只按 actor 自己的 principal_id 取数**，路径里不接受 principal_id。导出端点一旦能
   指定他人，就是一个比 SQL 注入更省事的数据外泄接口。
3. 删除的下游后果是**自杀式**的：受理成功即撤销申请人全部会话与令牌，所以响应之后
   紧接着的请求一定是 401。这是正确的（「我已要求删除」与「这个会话还能读我的数据」不能
   同时为真），但前端必须按「先落提示再跳登录页」处理，不能按普通 201 刷新页面 ——
   否则用户看到的是一个莫名其妙的登录墙，而它会被人当成 bug 报回来。
   宽限期内允许重新登录同样是故意的：撤销删除请求只能靠登录后点取消。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from deps import get_db
from routes.account_routes import _assert_human_write, _get_actor
from services import data_rights

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/account", tags=["data-rights"])

# 导出是一次可能很重的读（agent_execution_log 单行可带完整 trajectory JSON）。
# 同一账户排队中/进行中的导出只保留一个，避免「连点十次 = 十份全量读表」。
_ACTIVE_EXPORT_STATUSES = ("queued", "running")


class DeletionCancelRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=120, description="撤销原因（仅入审计）")


def _export_view(row: dict | None) -> dict | None:
    if row is None:
        return None
    counts = None
    if row.get("section_counts_json"):
        try:
            counts = json.loads(row["section_counts_json"])
        except (TypeError, ValueError):
            counts = None
    return {
        "export_id": row["export_id"],
        "status": row["status"],
        "requested_at": row["requested_at"],
        "completed_at": row.get("completed_at"),
        "section_counts": counts,
        "error": row.get("error"),
        "download_ready": row["status"] == "completed" and bool(row.get("artifact_path")),
    }


def _deletion_view(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "status": row["status"],
        "requested_at": row["requested_at"],
        "scheduled_delete_at": row["scheduled_delete_at"],
        "grace_days": row["grace_days"],
        "cancelled_at": row.get("cancelled_at"),
        "revoked_sessions": row.get("revoke_session_count"),
        "revoked_tokens": row.get("revoke_token_count"),
    }


@router.post("/export", status_code=202)
def request_account_export(actor: dict = Depends(_get_actor)) -> dict:
    """提交一次账户数据导出作业（异步，Spec R1.7 要求走 submit_as_job）。

    为什么异步而不是同步返 JSON：导出要扫 17 张表并含 agent 全量对话轨迹，同步实现会在
    大账户上顶穿网关超时，而一个「有时能有时不能」的权利行使端点比没有更糟。
    """
    _assert_human_write(actor, action="account.export_requested")
    db = get_db()
    principal_id = actor["principal"]["principal_id"]

    latest = data_rights.get_export(db, principal_id=principal_id)
    if latest and latest["status"] in _ACTIVE_EXPORT_STATUSES:
        # 202 而不是 409：调用方的意图（「给我一份导出」）已经被在先的那次满足了，
        # 报错误导前端去提示失败。
        # ``status`` 必须写在 ``**_export_view(...)`` **之后**：视图里自带一个 status 键，
        # 先写的字面量会被后展开的视图悄悄覆盖回 "queued" —— 那样「重复提交」与「首次受理」
        # 在响应上就完全无法区分了，而这两件事对客户端的意义不同（一个没建新作业）。
        return {
            **_export_view(latest),
            "status": "already_queued",
            "message": "已有一次导出正在处理，完成后即可下载",
        }

    record = data_rights.create_export_record(db, principal_id=principal_id)
    from cache_utils import submit_as_job

    job = submit_as_job(
        "account_data_export",
        {"export_id": record["export_id"], "principal_id": principal_id},
        queue_name="analysis",
        source_key="account_export",
    )
    return {
        "status": "queued",
        "export_id": record["export_id"],
        "job_id": job["job_id"],
        "requested_at": record["requested_at"],
        "message": "导出已开始，稍后用 GET /api/v1/account/export 查询并下载",
    }


@router.get("/export")
def get_account_export(actor: dict = Depends(_get_actor)) -> dict:
    """最近一次导出的状态（含未完成态，前端轮询用）。"""
    _assert_human_write(actor, action="account.export_read")
    row = data_rights.get_export(
        get_db(), principal_id=actor["principal"]["principal_id"]
    )
    if row is None:
        return {"status": "none", "export_id": None}
    return _export_view(row)


@router.get("/export/{export_id}/download")
def download_account_export(export_id: str, actor: dict = Depends(_get_actor)) -> FileResponse:
    """下载导出文件。

    路径来自我们自己写的表行，且取行时已按 principal_id 收敛 —— 但**仍然**不直接把表里的
    路径交给 ``FileResponse``：表里存的绝对路径一旦因为任何原因（运维搬盘、误写）指向仓库
    其它文件，这个端点就成了任意文件读。所以要断言它落在 lake 根目录之下。
    """
    _assert_human_write(actor, action="account.export_download")
    db = get_db()
    row = data_rights.get_export(
        db, principal_id=actor["principal"]["principal_id"], export_id=export_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Export not found")
    if row["status"] != "completed" or not row.get("artifact_path"):
        raise HTTPException(status_code=409, detail=f"Export not ready (status={row['status']})")

    path = Path(row["artifact_path"]).resolve()
    lake_root = Path(data_rights.lake_root_dir()).resolve()
    if not str(path).startswith(str(lake_root)):
        logger.error("Export artifact %s escaped lake root %s", path, lake_root)
        raise HTTPException(status_code=500, detail="Export artifact path is not trusted")
    if not path.exists():
        # 文件没了但行还在：必须报「重新生成」而不是 500，否则用户卡在一个无解的界面上。
        raise HTTPException(status_code=410, detail="Export file expired; request a new export")
    return FileResponse(
        path=str(path),
        media_type="application/json",
        filename=f"account-export-{export_id}.json",
    )


@router.post("/delete", status_code=202)
def request_account_deletion(actor: dict = Depends(_get_actor)) -> dict:
    """提交账户删除请求（软删除 + 宽限期，期内可撤销）。"""
    _assert_human_write(actor, action="account.deletion_requested")
    db = get_db()
    principal_id = actor["principal"]["principal_id"]
    try:
        record = data_rights.request_account_deletion(db, principal_id=principal_id)
    except data_rights.DeletionBlockedByOwnership as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ownership_transfer_required",
                "message": "你仍是以下组织的所有者，请先移交所有权或解散组织",
                "organizations": exc.organizations,
                "next_action": "POST /api/v1/organizations/{organization_id}/transfer-owner",
            },
        ) from exc
    except data_rights.DeletionAlreadyPending as exc:
        # 同 /export 的 already_queued：``status`` 必须放在视图展开之后，否则会被
        # _deletion_view 自带的 "pending" 覆盖，重复提交与首次受理就分不出来了。
        return {
            **_deletion_view(exc.request),
            "status": "already_pending",
            "message": "删除请求已在处理中；如需反悔请调用撤销端点",
        }
    return {
        **_deletion_view(record),
        "status": "pending",
        # 这句不是客套：响应之后当前令牌已失效，前端不照做就会把成功当成失败。
        "session_revoked": True,
        "message": "删除请求已受理，当前所有会话已注销；宽限期内重新登录可撤销",
    }


@router.get("/delete")
def get_account_deletion(actor: dict = Depends(_get_actor)) -> dict:
    """查询自己的删除请求状态（无请求时 status=none）。"""
    _assert_human_write(actor, action="account.deletion_read")
    row = data_rights.get_deletion_request(
        get_db(), principal_id=actor["principal"]["principal_id"]
    )
    if row is None:
        return {"status": "none"}
    return _deletion_view(row)


@router.post("/delete/cancel")
def cancel_account_deletion(
    body: DeletionCancelRequest, actor: dict = Depends(_get_actor)
) -> dict:
    """在宽限期内撤销删除请求。必须已登录，所以这条路由天然要求一枚有效令牌。"""
    _assert_human_write(actor, action="account.deletion_cancelled")
    db = get_db()
    principal_id = actor["principal"]["principal_id"]
    try:
        record = data_rights.cancel_account_deletion(db, principal_id=principal_id)
    except data_rights.DeletionAlreadyPending:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "no_pending_deletion",
                "message": "没有待执行的删除请求（可能已撤销或已执行）",
            },
        )
    view = _deletion_view(record)
    view["reason"] = body.reason
    return {"status": "cancelled", **view}
