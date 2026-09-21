import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fleet_api import __version__
from fleet_api.api.admin import router as admin_router
from fleet_api.api.auth import router as auth_router
from fleet_api.api.driver import router as driver_router
from fleet_api.core.config import Settings, get_settings
from fleet_api.core.request_id import RequestIdMiddleware
from fleet_api.core.structured_logging import configure_logging
from fleet_api.db.session import check_database

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
        description="Foundation API for company-owned construction tippers.",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(driver_router)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

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
        return {"status": "ready", "database": "available"}

    return app


app = create_app()
