"""Infographic static page routes.

Serves the technical panorama infographic HTML directly via backend route.
No frontend entry needed — access via URL path only.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["infographic"])

# Resolve HTML file path: project_root/aus-ele-design-demo/方向三-图谱箭头.html
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_INFOGRAPHIC_DIR = _PROJECT_ROOT / "aus-ele-design-demo"
_TECH_PANORAMA_HTML = _INFOGRAPHIC_DIR / "方向三-图谱箭头.html"


@router.get("/api/infographic/tech-panorama", response_class=HTMLResponse)
def serve_tech_panorama():
    """Serve the AEMO BESS technical panorama infographic (方向三-图谱箭头).

    Returns the full interactive HTML with React 18 + KaTeX formulas.
    """
    if not _TECH_PANORAMA_HTML.exists():
        return HTMLResponse(
            content="<h1>404</h1><p>Infographic HTML not found at expected path.</p>",
            status_code=404,
        )
    html = _TECH_PANORAMA_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/api/infographic/list")
def list_infographics():
    """List all available infographic pages."""
    infographics = []
    if _INFOGRAPHIC_DIR.exists():
        for f in sorted(_INFOGRAPHIC_DIR.glob("*.html")):
            infographics.append({
                "name": f.stem,
                "path": f"/api/infographic/{f.stem}",
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return {"infographics": infographics}
