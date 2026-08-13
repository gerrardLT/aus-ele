"""
Route registration module for the AEMO Intelligence platform.

Provides centralized route module loading with graceful degradation:
individual module failures are logged but do not prevent other modules
from starting.

Also registers the MarketModuleError exception handler so all market
module endpoints return structured error responses.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

ROUTE_MODULES = [
    "routes.auth_routes",
    "routes.price_routes",
    "routes.revenue_routes",
    "routes.investment_routes",
    "routes.fcas_routes",
    "routes.data_quality_routes",
    "routes.finland_routes",
    "routes.admin_routes",
    "routes.external_api_routes",
    "routes.aggregation_routes",
    "routes.spike_routes",
    "routes.saturation_routes",
    "routes.ranking_routes",
    "routes.coopt_routes",
    "routes.wem_modules_routes",
    "routes.wem_csv_upload",
    "routes.outlook_routes",
    "routes.cost_structure_routes",
    "routes.forward_price_routes",
    "routes.benchmark_routes",
    "routes.knowledge_routes",
    "routes.narrative_routes",
    "routes.agent_routes",
    "routes.anomaly_routes",
]

# Module-level state tracking degraded modules for health reporting
_degraded_modules: list[str] = []


def get_degraded_modules() -> list[str]:
    """Return the list of route modules that failed to load."""
    return list(_degraded_modules)


def register_all_routes(app: "FastAPI", *, degraded_modules: list[str] | None = None) -> list[str]:
    """Register all route modules with graceful degradation.

    Each module is loaded independently — a failure in one module does not
    prevent the remaining modules from being registered.

    Args:
        app: The FastAPI application instance.
        degraded_modules: Optional pre-existing list to append failures to.
            If None, uses the module-level _degraded_modules list.

    Returns:
        List of module paths that failed to load.
    """
    global _degraded_modules

    degraded = degraded_modules if degraded_modules is not None else _degraded_modules
    # Reset module-level state when using internal list
    if degraded_modules is None:
        _degraded_modules = []
        degraded = _degraded_modules

    for module_path in ROUTE_MODULES:
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, "router"):
                app.include_router(mod.router)
                logger.info(f"Registered route module: {module_path}")
            else:
                logger.warning(
                    f"Route module {module_path} has no 'router' attribute, skipping"
                )
                degraded.append(module_path)
        except Exception as exc:
            logger.error(f"Failed to load route module {module_path}: {exc}")
            degraded.append(module_path)

    if degraded:
        logger.warning(f"Degraded modules ({len(degraded)}): {degraded}")

    # Register the MarketModuleError exception handler
    _register_market_module_error_handler(app)

    return degraded


def _register_market_module_error_handler(app: "FastAPI") -> None:
    """Register a global exception handler for MarketModuleError.

    Returns a structured JSON response with error_code, message, and
    suggested_action fields as required by Requirement 12.6.
    """
    from fastapi.responses import JSONResponse

    from exceptions import MarketModuleError

    @app.exception_handler(MarketModuleError)
    async def _handle_market_module_error(request, exc: MarketModuleError):  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "suggested_action": exc.suggested_action,
            },
        )
