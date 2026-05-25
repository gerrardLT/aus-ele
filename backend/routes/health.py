"""
Health check endpoint for the AEMO Intelligence platform.

Reports overall system status and lists any degraded route modules.
"""

from __future__ import annotations

from fastapi import APIRouter

from routes import get_degraded_modules

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health_check() -> dict:
    """Return platform health status including degraded module list.

    Returns a JSON object with:
    - status: "healthy" if no modules are degraded, "degraded" otherwise
    - degraded_modules: list of module paths that failed to load
    """
    degraded = get_degraded_modules()
    status = "degraded" if degraded else "healthy"
    return {
        "status": status,
        "degraded_modules": degraded,
    }
