import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fleet_api import __version__
from fleet_api.api.admin import router as admin_router
from fleet_api.api.auth import router as auth_router
from fleet_api.api.driver import router as driver_router
from fleet_api.api.owner import router as owner_router
from fleet_api.api.owner_assignments import router as owner_assignments_router
from fleet_api.api.owner_deployments import router as owner_deployments_router
from fleet_api.api.owner_fuel import router as owner_fuel_router
from fleet_api.api.owner_future import document_router, feature_router, maintenance_router
from fleet_api.api.owner_notifications import router as owner_notifications_router
from fleet_api.api.owner_people_sites import router as owner_people_sites_router
from fleet_api.api.owner_report_templates import router as owner_report_templates_router
from fleet_api.api.owner_telematics import router as owner_telematics_router
from fleet_api.api.owner_workforce import (
    location_driver_router,
    location_owner_router,
    workforce_router,
)
from fleet_api.api.reports import router as reports_router
from fleet_api.api.supervisor import router as supervisor_router
from fleet_api.core.config import Settings, get_settings
from fleet_api.core.request_id import RequestIdMiddleware
from fleet_api.core.structured_logging import configure_logging
from fleet_api.db.session import check_database
from fleet_api.domain.errors import ObjectStorageUnavailableError
from fleet_api.storage.objects import build_object_storage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("fleet_manager_api_started")
    yield
    logger.info("fleet_manager_api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    app = FastAPI(
        title="Fleet Manager API",
        version=__version__,
        description="Fleet operations API for construction assets.",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(driver_router)
    app.include_router(owner_router)
    app.include_router(owner_assignments_router)
    app.include_router(owner_people_sites_router)
    app.include_router(maintenance_router)
    app.include_router(document_router)
    app.include_router(feature_router)
    app.include_router(owner_notifications_router)
    app.include_router(owner_telematics_router)
    app.include_router(owner_fuel_router)
    app.include_router(workforce_router)
    app.include_router(location_owner_router)
    app.include_router(location_driver_router)
    app.include_router(owner_deployments_router)
    app.include_router(owner_report_templates_router)
    app.include_router(supervisor_router)
    app.include_router(reports_router)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=[
            "X-Fleet-Evidence-Event-Type",
            "X-Fleet-Evidence-Driver",
            "X-Fleet-Evidence-Tipper",
            "X-Fleet-Evidence-Timestamp",
        ],
    )
    if "*" not in runtime_settings.allowed_host_values:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=runtime_settings.allowed_host_values,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, _: Exception) -> JSONResponse:
        request_id = request.headers.get("x-request-id")
        logger.exception("unhandled_request_error", extra={"path": request.url.path})
        body: dict[str, Any] = {"detail": "Internal server error"}
        if request_id:
            body["request_id"] = request_id
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "fleet-manager-api", "version": __version__}

    @app.get("/ready", response_model=None, tags=["system"])
    async def readiness() -> JSONResponse | dict[str, str]:
        if not check_database():
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": "unavailable"},
            )
        try:
            build_object_storage(runtime_settings).check_ready()
        except ObjectStorageUnavailableError:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "database": "available",
                    "object_storage": "unavailable",
                },
            )
        return {
            "status": "ready",
            "database": "available",
            "object_storage": "available",
        }

    return app


app = create_app()
