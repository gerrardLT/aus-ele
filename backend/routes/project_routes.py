"""项目/资产实体 API（R4.1，2026-09-06）。

把 7 阶段漏斗的分析结果从「一次性的 HTTP 响应」变成「版本化的项目资产」——这是诊断
§2 判定的最高价值单点改造：此前全站没有 project/asset 概念，用户只能反复重跑并自己
截图存档。表结构见 ``database.ensure_asset_project_tables``。

三条设计判定（对应诊断里用户可感知的断点）：

1. **参数快照存在项目里，不引用全局 ``assumptions_registry``**。登记表是全局单值，
   表达不了「项目 A 用压缩因子 0.92、项目 B 用 0.88」；``config_json`` 就是项目级参数
   的权威来源。
2. **版本挂载是显式动作**（用户点「保存这一版」），不是每次分析自动写——自动写等于把
   ``analysis_cache`` 换个名字，用户会被几百个无意义版本淹没。``data_version`` 由服务端
   取 ``db.get_last_update_time()`` 存进版本行，三个月后重算能核对「上游数据变没变」，
   而不是只看到数字不同却无从归因。
3. **删除是归档不是物理删**：版本链是用户的工作成果，误删不可逆比占点空间贵得多。

鉴权复用既有链路（``_get_actor`` + ``_assert_human_write``），与 data_rights_routes 同一
纪律：真实 Bearer + 拒绝匿名 bootstrap 身份；跨 workspace 一律 404（存在性不外泄）。
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_db
from routes.account_routes import _assert_human_write, _get_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# config / payload 是用户自己的分析上下文，不是导出通道；512KB 足够装下 7 阶段摘要
# 与参数快照，装不下就该存在 artifact lake 里挂路径。超限 413（请求体本身合法，只是太大）。
_MAX_JSON_CHARS = 512_000


def _utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _json_chars(value) -> int:
    return len(json.dumps(value or {}, ensure_ascii=False))


def _project_view(record: dict | None) -> dict | None:
    if not record:
        return None
    return {
        "project_id": record["project_id"],
        "workspace_id": record["workspace_id"],
        "name": record["name"],
        "description": record["description"],
        "market": record["market"],
        "region": record["region"],
        "config": record["config"],
        "status": record["status"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def _load_owned_project(db, project_id: str, actor: dict) -> dict:
    """归属校验统一 404：不区分「不存在」与「不是你这个 workspace 的」，
    否则项目 id 成了跨租户存在性探针。"""
    record = db.fetch_asset_project(project_id)
    if not record or record["workspace_id"] != actor["workspace"]["workspace_id"]:
        raise HTTPException(status_code=404, detail="Project not found")
    return record


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)
    market: str | None = Field(None, max_length=16)
    region: str | None = Field(None, max_length=16)
    config: dict | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)
    market: str | None = Field(None, max_length=16)
    region: str | None = Field(None, max_length=16)
    config: dict | None = None


class VersionCreate(BaseModel):
    label: str | None = Field(None, max_length=160)
    payload: dict | None = None


@router.post("", status_code=201)
def create_project(body: ProjectCreate, actor: dict = Depends(_get_actor)) -> dict:
    _assert_human_write(actor, action="project.create_denied")
    if _json_chars(body.config) > _MAX_JSON_CHARS:
        raise HTTPException(status_code=413, detail="Project config too large")
    db = get_db()
    now = _utc_iso()
    record = db.insert_asset_project({
        "project_id": f"proj_{uuid.uuid4().hex[:16]}",
        "workspace_id": actor["workspace"]["workspace_id"],
        "created_by": actor["principal"]["principal_id"],
        "name": body.name.strip(),
        "description": body.description,
        "market": body.market,
        "region": body.region,
        "config": body.config or {},
        "created_at": now,
        "updated_at": now,
    })
    return _project_view(record)


@router.get("")
def list_projects(
    include_archived: bool = False, actor: dict = Depends(_get_actor)
) -> dict:
    db = get_db()
    rows = db.list_asset_projects(
        actor["workspace"]["workspace_id"], include_archived=include_archived
    )
    return {"projects": [_project_view(row) for row in rows]}


@router.get("/{project_id}")
def get_project(project_id: str, actor: dict = Depends(_get_actor)) -> dict:
    db = get_db()
    record = _load_owned_project(db, project_id, actor)
    return _project_view(record)


@router.patch("/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, actor: dict = Depends(_get_actor)) -> dict:
    _assert_human_write(actor, action="project.update_denied")
    db = get_db()
    _load_owned_project(db, project_id, actor)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update")
    if "config" in fields and _json_chars(fields["config"]) > _MAX_JSON_CHARS:
        raise HTTPException(status_code=413, detail="Project config too large")
    record = db.update_asset_project(
        project_id, actor["workspace"]["workspace_id"], fields=fields, updated_at=_utc_iso()
    )
    return _project_view(record)


@router.delete("/{project_id}")
def archive_project(project_id: str, actor: dict = Depends(_get_actor)) -> dict:
    _assert_human_write(actor, action="project.archive_denied")
    db = get_db()
    _load_owned_project(db, project_id, actor)
    ok = db.archive_asset_project(
        project_id, actor["workspace"]["workspace_id"], archived=True, updated_at=_utc_iso()
    )
    return {"archived": bool(ok), "project_id": project_id}


@router.post("/{project_id}/versions", status_code=201)
def create_project_version(
    project_id: str, body: VersionCreate, actor: dict = Depends(_get_actor)
) -> dict:
    _assert_human_write(actor, action="project.version_create_denied")
    if _json_chars(body.payload) > _MAX_JSON_CHARS:
        raise HTTPException(status_code=413, detail="Version payload too large")
    db = get_db()
    _load_owned_project(db, project_id, actor)
    try:
        record = db.insert_asset_project_version({
            "project_id": project_id,
            "label": body.label,
            # data_version 由服务端取（客户端给不可信）：与 analysis_cache 的键化口径
            # 一致，「同一 data_version ⇒ 同一上游数据」这个等式才有意义。
            "data_version": db.get_last_update_time(),
            "payload": body.payload or {},
            "created_by": actor["principal"]["principal_id"],
            "created_at": _utc_iso(),
        })
    except Exception as exc:  # 主键冲突（并发同号）等：不覆盖既有版本，直接报错
        logger.warning("project version insert failed: %s", exc)
        raise HTTPException(status_code=409, detail="Version conflict, please retry")
    view = {
        "project_id": record["project_id"],
        "version_no": record["version_no"],
        "label": record["label"],
        "data_version": record["data_version"],
        "created_at": record["created_at"],
    }
    return view


@router.get("/{project_id}/versions")
def list_project_versions(
    project_id: str, actor: dict = Depends(_get_actor)
) -> dict:
    db = get_db()
    _load_owned_project(db, project_id, actor)
    rows = db.list_asset_project_versions(project_id)
    return {
        "versions": [
            {
                "version_no": row["version_no"],
                "label": row["label"],
                "data_version": row["data_version"],
                "payload": row["payload"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    }
