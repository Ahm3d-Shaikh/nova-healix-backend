import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types as genai_types

from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, DomainError, InvalidInputError, NotFoundError, UnavailableError
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.reference import DISCLAIMER
from app.db.base import Database, DatabaseError
from app.db.memory import InMemoryDatabase
from app.db.supabase import SupabaseDatabase
from app.repositories.cache import CacheRepository
from app.ridge_container import RidgeContainer, build_ridge_container
from app.routers import (
    actions,
    assessment,
    companion,
    crew,
    crew_mode,
    dashboard,
    distance,
    isolation,
    mission,
    mobility,
    ridge_crew,
    ridge_mobility,
    telemetry,
)
from app.services.companion import GeminiReplier
from app.services.donki_client import DonkiClient
from app.services.echo_companion import GeminiCompanion
from app.services.horizons_client import HorizonsClient
from app.services.nasa import NasaDataService

log = logging.getLogger(__name__)
MOBILITY_PAGE_DIR = Path(__file__).parent / "static" / "mobility"

STATUS_BY_ERROR: list[tuple[type[DomainError], int]] = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (UnavailableError, 503),
    (InvalidInputError, 422),
]


def create_app(  # noqa: PLR0915 - the lifespan wires both APIs
    settings: Settings | None = None, container: Container | None = None, ridge: RidgeContainer | None = None
) -> FastAPI:
    """One service, two APIs: Nova Healix v2 (`container`) and the RIDGE API with ECHO and distance (`ridge`)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if container is not None:
            app.state.container = container
            app.state.ridge = ridge
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
                log.warning(
                    "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: using an in-memory store (lost on restart)."
                )
                db = InMemoryDatabase()
            gemini = (
                genai.Client(
                    api_key=settings.gemini_api_key,
                    http_options=genai_types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
                )
                if settings.gemini_api_key
                else None
            )
            echo = (
                GeminiCompanion(
                    gemini, settings.gemini_model, settings.gemini_chat_model, settings.gemini_chat_timeout_seconds
                )
                if gemini
                else None
            )
            replier = (
                GeminiReplier(gemini, settings.gemini_chat_model, settings.gemini_chat_timeout_seconds)
                if gemini
                else None
            )
            if gemini is None:
                log.info("GEMINI_API_KEY not set: Nova uses its rules only and ECHO check-ins return 503.")
            built = await build_container(settings, db, replier)
            ridge_built = await build_ridge_container(settings, donki, horizons, db, echo)
            app.state.container = built
            app.state.ridge = ridge_built
            if settings.nasa_api_key == "DEMO_KEY":
                log.warning("Using DEMO_KEY: heavily rate-limited. Set NASA_API_KEY for live DONKI data.")
            nasa = NasaDataService(
                weather=ridge_built.weather,  # one DONKI feed shared by both APIs
                horizons=horizons,
                cache=CacheRepository(db),
                data=built.data,
                trajectory=built.trajectory,
                clock=built.clock,
            )

            # Warm the NASA feeds so no request waits on them; the APIs run on defaults meanwhile.
            async def warm() -> None:
                await asyncio.gather(nasa.refresh(), ridge_built.crew.distance_series(), return_exceptions=True)

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
        description=f"Nova Healix backend. **{DISCLAIMER}**",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = next((code for cls, code in STATUS_BY_ERROR if isinstance(exc, cls)), 400)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(DatabaseError)
    async def handle_database_error(_: Request, exc: DatabaseError) -> JSONResponse:
        log.error("Database error: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable; please retry"})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # A readable message, and never an echo of the submitted values (Nova bodies are private).
        parts = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
            parts.append(f"{where}: {err['msg']}" if where else str(err["msg"]))
        return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "Invalid request"})

    for router in (
        # Nova Healix API v2 (the frontend guide) and its additive Mobility & Balance Check
        mission.router,
        crew.router,
        telemetry.router,
        assessment.router,
        crew_mode.router,
        companion.router,
        actions.router,
        mobility.router,
        # RIDGE API: dashboard, alerts, ECHO check-in chat, distance; crew and mobility live under /api/ridge/
        ridge_crew.router,
        dashboard.router,
        distance.router,
        isolation.router,
        ridge_mobility.router,
    ):
        app.include_router(router)

    # Browser test page for the Mobility & Balance Check (MediaPipe runs in the browser, not on the server)
    if MOBILITY_PAGE_DIR.is_dir():
        app.mount("/demo/mobility", StaticFiles(directory=MOBILITY_PAGE_DIR, html=True), name="mobility-demo")

    @app.get("/", tags=["ops"])
    async def root() -> dict[str, str]:
        return {"message": "Nova Healix backend is running!", "disclaimer": DISCLAIMER, "docs": "/docs"}

    @app.get("/health", tags=["ops"])
    async def health_check(request: Request) -> dict[str, str | float | bool]:
        c: Container = request.app.state.container
        r: RidgeContainer | None = getattr(request.app.state, "ridge", None)
        return {
            "status": "ok",
            "version": settings.app_version,
            "companion": c.companion.mode,  # Nova: "gemini" | "rules" | "off"
            "missionHour": round(c.clock.now_hour(), 2),
            "database": c.database,
            "ai_checkin": bool(r and r.ai_checkin_enabled),  # ECHO (RIDGE isolation check-in chat)
        }

    return app


app = create_app()
