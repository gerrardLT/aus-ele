"""Knowledge base health API route（2026-08-13）。

GET /api/knowledge/health — 知识库健康报告（运营节奏自动化体检）。
公开端点：报告不含用户数据，仅知识库维护状态。
"""

from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter

from deps import get_cache
from services.knowledge_health import build_health_report

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])

_CACHE_SCOPE = "api_knowledge_health_v1"
_CACHE_TTL_SECONDS = 6 * 60 * 60


@router.get(
    "/api/knowledge/health",
    summary="Knowledge base health report",
    description=(
        "Weekly-automated health check of all knowledge bases (pipeline freshness, "
        "rule review dates, benchmark calibration cadence, event case backlog). "
        "Statuses: ok / due_soon / overdue / informational. See "
        "docs/deployment/运营节奏清单.md for the maintenance SOP."
    ),
)
def get_knowledge_health():
    cache = get_cache()
    cache_key = hashlib.sha256(json.dumps({"endpoint": "health"}, sort_keys=True).encode()).hexdigest()
    cached = cache.get_json(_CACHE_SCOPE, cache_key)
    if cached is not None:
        return cached

    report = build_health_report()
    cache.set_json(_CACHE_SCOPE, cache_key, report, _CACHE_TTL_SECONDS)
    return report
