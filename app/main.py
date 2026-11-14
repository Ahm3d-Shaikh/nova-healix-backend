import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types as genai_types

from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.errors import (
    CompanionUnavailableError,
    DomainError,
    InvalidDayError,
    NotEnoughTurnsError,
    SessionClosedError,
    SessionNotFoundError,
    SessionTurnLimitError,
    UnknownAstronautError,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.reference import DISCLAIMER
from app.db.base import Database, DatabaseError
from app.db.memory import InMemoryDatabase
from app.db.supabase import SupabaseDatabase
from app.routers import crew, dashboard, distance, isolation, mobility
from app.services.companion import GeminiCompanion
from app.services.donki_client import DonkiClient
from app.services.horizons_client import HorizonsClient

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    UnknownAstronautError: 404,
    InvalidDayError: 422,
    SessionNotFoundError: 404,
    SessionClosedError: 409,
    SessionTurnLimitError: 409,
    NotEnoughTurnsError: 409,
    CompanionUnavailableError: 503,
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
            horizons = HorizonsClient(http, settings.horizons_base_url, settings.horizons_timeout_seconds)
            db: Database
            if settings.use_supabase:
                db = SupabaseDatabase(
                    http, settings.supabase_url, settings.supabase_service_role_key, settings.supabase_timeout_seconds
                )
            else:
                log.warning("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: using an in-memory store.")
                db = InMemoryDatabase()
            gemini = (
                genai.Client(
                    api_key=settings.gemini_api_key,
                    http_options=genai_types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
                )
                if settings.gemini_api_key
                else None
            )
            companion = (
                GeminiCompanion(
                    gemini, settings.gemini_model, settings.gemini_chat_model, settings.gemini_chat_timeout_seconds
                )
                if gemini
                else None
            )
            if companion is None:
                log.warning("GEMINI_API_KEY not set: AI isolation check-ins are disabled.")
            app.state.container = await build_container(settings, donki, horizons, db, companion)
            if settings.nasa_api_key == "DEMO_KEY":
                log.warning("Using DEMO_KEY: heavily rate-limited. Set NASA_API_KEY for live DONKI data.")

            # Warm the NASA caches so the first dashboard request does not wait on them.
            async def warm() -> None:
                await asyncio.gather(
                    app.state.container.weather.get(),
                    app.state.container.crew.distance_series(),
                    return_exceptions=True,
                )

            warmup = asyncio.create_task(warm())
            try:
                yield
            finally:
                warmup.cancel()
                if gemini is not None:
                    await gemini.aio.aclose()

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

    @app.exception_handler(DatabaseError)
    async def handle_database_error(_: Request, exc: DatabaseError) -> JSONResponse:
        log.error("Database error: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable; please retry"})

    for router in (crew.router, dashboard.router, distance.router, isolation.router, mobility.router):
        app.include_router(router)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"message": "RIDGE Monitor backend is running!", "disclaimer": DISCLAIMER, "docs": "/docs"}

    @app.get("/health", tags=["meta"])
    async def health_check(request: Request) -> dict[str, str | bool]:
        c: Container = request.app.state.container
        return {
            "status": "healthy",
            "version": settings.app_version,
            "database": c.database,
            "ai_checkin": c.ai_checkin_enabled,
        }

    return app


app = create_app()
