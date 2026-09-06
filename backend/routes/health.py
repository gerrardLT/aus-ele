"""
Health check endpoint for the Tianshu platform.

Reports overall system status and lists any degraded route modules.  Also
publishes the OpenAPI document under ``/api/`` (see ``openapi_document``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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


@router.get("/api/openapi.json")
async def openapi_document(request: Request) -> JSONResponse:
    """Serve the OpenAPI document under the ``/api/`` prefix.

    Why re-home a path FastAPI already publishes: ``/openapi.json`` is only
    reachable on the bare backend origin.  In production nginx matches it with
    ``location /`` and answers with ``index.html`` (SPA fallback), and the Vite
    dev server proxies nothing outside ``/api`` -- so a browser-side consumer
    would silently receive HTML instead of the document.  ``/api/openapi.json``
    is the single URL that works identically for dev, docker and a plain uvicorn
    origin, which is what the ⌘K command index (R3.4) needs in order to avoid a
    hand-maintained endpoint list (234 operations as measured on 2026-09-06).

    Unauthenticated by design: FastAPI already publishes the same document at
    ``/openapi.json`` without auth, so this adds no exposure.
    """
    return JSONResponse(request.app.openapi())
