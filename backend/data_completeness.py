"""WEM data completeness status tracking.

Provides a model and helper to determine whether WEM modules (ESS, FCAS)
have complete data pipelines connected or are still in preview mode.
"""

from __future__ import annotations

from pydantic import BaseModel

from database import DatabaseManager


class DataCompletenessStatus(BaseModel):
    """WEM 模块数据完整性状态"""

    module: str  # "wem_ess" | "wem_fcas"
    status: str  # "complete" | "preview"
    label: str  # 显示标注文本
    last_sync: str | None  # 最后同步时间
    pipeline_connected: bool  # 管道是否已连接


# Label mapping per module when status is "preview"
_PREVIEW_LABELS: dict[str, str] = {
    "wem_ess": "预览 — ESS 管道未连接",
    "wem_fcas": "预览 — FCAS 数据有限",
}

_COMPLETE_LABEL = "完整数据"


def get_module_completeness(module: str, db: DatabaseManager) -> DataCompletenessStatus:
    """Determine the data completeness status for a WEM module.

    Checks the database system_status table for sync state and completeness
    markers. Returns a DataCompletenessStatus describing the current state.

    Args:
        module: One of "wem_ess" or "wem_fcas".
        db: DatabaseManager instance for querying system status.

    Returns:
        DataCompletenessStatus with the current completeness information.
    """
    if module not in ("wem_ess", "wem_fcas"):
        raise ValueError(f"Unknown module: {module}. Expected 'wem_ess' or 'wem_fcas'.")

    completeness_key = f"{module}_data_completeness"
    last_sync_key = f"{module}_last_sync"

    completeness_value = db.get_system_status(completeness_key)
    last_sync = db.get_system_status(last_sync_key)

    is_complete = completeness_value == "complete"
    pipeline_connected = last_sync is not None

    if is_complete:
        status = "complete"
        label = _COMPLETE_LABEL
    else:
        status = "preview"
        label = _PREVIEW_LABELS.get(module, f"预览 — {module}")

    return DataCompletenessStatus(
        module=module,
        status=status,
        label=label,
        last_sync=last_sync,
        pipeline_connected=pipeline_connected,
    )
