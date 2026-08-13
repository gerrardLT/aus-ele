"""Knowledge base health API route（2026-08-13）。

GET /api/knowledge/health — 知识库健康报告（运营节奏自动化体检）。
公开端点：报告不含用户数据，仅知识库维护状态。
不走响应缓存：报告基于本地文件即席计算（毫秒级），
缓存会让维护状态失真（2026-08-13 生产演练教训）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from services.knowledge_health import build_health_report

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])


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
    return build_health_report()
