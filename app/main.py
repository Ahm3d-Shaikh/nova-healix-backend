import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.errors import DomainError, InvalidDayError, NoValidResponsesError, UnknownAstronautError
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.routers import crew, dashboard, isolation, mirror_gap, space_weather
from app.routers import settings as settings_router
from app.services.donki_client import DonkiClient

DISCLAIMER = (
    "Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data."
)
STATUS_BY_ERROR: dict[type[DomainError], int] = {
    UnknownAstronautError: 404,
    InvalidDayError: 422,
    NoValidResponsesError: 422,
}
log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if container is not None:
            app.state.container = container
            yield
            return
        async with httpx.AsyncClient() as http:
            donki = DonkiClient(http, settings.donki_base_url, settings.nasa_api_key, settings.donki_timeout_seconds)
            app.state.container = build_container(settings, donki)
            if settings.nasa_api_key == "DEMO_KEY":
                log.warning("Using DEMO_KEY: heavily rate-limited. Set NASA_API_KEY for live DONKI data.")
            # Warm the DONKI cache so the first dashboard request does not wait on NASA.
            warmup = asyncio.create_task(app.state.container.weather.get())
            try:
                yield
            finally:
                warmup.cancel()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=f"RIDGE Monitor backend. **{DISCLAIMER}**",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = next((code for cls, code in STATUS_BY_ERROR.items() if isinstance(exc, cls)), 400)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    for router in (
        space_weather.router,
        crew.router,
        dashboard.router,
        isolation.router,
        mirror_gap.router,
        settings_router.router,
    ):
        app.include_router(router)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"message": "RIDGE Monitor backend is running!", "disclaimer": DISCLAIMER, "docs": "/docs"}

    @app.get("/health", tags=["meta"])
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "version": settings.app_version}

    return app


app = create_app()
