"""API response payload contracts (R4.3, 2026-09-06).

Single source of truth for the response-model classes that route modules need
at decoration time. They used to live in server.py, which forced route modules
into a module-level ``from server import X`` — and that import, when the route
module itself was the first place ``server`` got loaded mid-``register_all_routes``,
left the triggering module partially initialized (no ``router`` attribute yet),
so the recursive registration skipped it and its endpoints silently vanished
from ``server.app``. Moving the classes into a leaf module breaks that cycle:
``routes/*`` imports ``models.api_payloads`` (no server involvement), and
server.py re-exports the same names for backwards compatibility.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataQualitySummaryPayload(BaseModel):
    summary: dict = Field(default_factory=dict)
    markets: dict = Field(default_factory=dict)


class DataQualityIssueRowsPayload(BaseModel):
    items: list[dict] = Field(default_factory=list)


class ObservabilityStatusPayload(BaseModel):
    sources: list[dict] = Field(default_factory=list)
    job_summary: dict = Field(default_factory=dict)
    telemetry: dict = Field(default_factory=dict)
    openlineage: dict = Field(default_factory=dict)
    collector: dict = Field(default_factory=dict)


class ExternalApiBillingSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    window: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    ledger: dict[str, Any] = Field(default_factory=dict)


class AlertRuleRecordPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    rule_id: str
    name: str
    rule_type: str
    market: str
    region_or_zone: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    channel_type: str
    channel_target: str
    enabled: bool = True
    organization_id: str | None = None
    workspace_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AlertRuleListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class AcceptedJobActionPayload(BaseModel):
    status: str
    detail: str | None = None
    job_id: str | None = None
    dataset_id: str | None = None
    mode: str | None = None
    job: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class JobListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class RunNextJobPayload(BaseModel):
    status: str
    result: dict[str, Any] | None = None


class FinlandMarketModelPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    country: str
    market: str
    model_status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    live_signals: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
