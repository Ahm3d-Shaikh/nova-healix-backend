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
from app.core.errors import ConflictError, DomainError, InvalidAnswersError, NotFoundError, UnavailableError
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.reference import DISCLAIMER
from app.db.base import Database, DatabaseError
from app.db.memory import InMemoryDatabase
from app.db.supabase import SupabaseDatabase
from app.repositories.cache import CacheRepository
from app.routers import actions, assessment, companion, crew, crew_mode, mission, mobility, telemetry
from app.services.companion import GeminiReplier
from app.services.donki_client import DonkiClient
from app.services.horizons_client import HorizonsClient
from app.services.nasa import NasaDataService
from app.services.space_weather_service import SpaceWeatherService

log = logging.getLogger(__name__)
MOBILITY_PAGE_DIR = Path(__file__).parent / "static" / "mobility"

STATUS_BY_ERROR: list[tuple[type[DomainError], int]] = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (UnavailableError, 503),
    (InvalidAnswersError, 422),
]


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
                    http_options=genai_types.HttpOptions(timeout=int(settings.gemini_chat_timeout_seconds * 1000)),
                )
                if settings.gemini_api_key
                else None
            )
            replier = (
                GeminiReplier(gemini, settings.gemini_chat_model, settings.gemini_chat_timeout_seconds)
                if gemini
                else None
            )
            if replier is None:
                log.info("GEMINI_API_KEY not set: Nova uses its deterministic rules for every reply.")
            built = await build_container(settings, db, replier)
            app.state.container = built
            if settings.nasa_api_key == "DEMO_KEY":
                log.warning("Using DEMO_KEY: heavily rate-limited. Set NASA_API_KEY for live DONKI data.")
            cache = CacheRepository(db)
            nasa = NasaDataService(
                weather=SpaceWeatherService(
                    DonkiClient(http, settings.donki_base_url, settings.nasa_api_key, settings.donki_timeout_seconds),
                    settings.storm_window_start,
                    settings.storm_window_end,
                    settings.donki_snapshot_path,
                    cache=cache,
                    cache_ttl_seconds=settings.donki_cache_ttl_seconds,
                    fetch_timeout_seconds=settings.donki_total_timeout_seconds,
                ),
                horizons=HorizonsClient(http, settings.horizons_base_url, settings.horizons_timeout_seconds),
                cache=cache,
                data=built.data,
                trajectory=built.trajectory,
                clock=built.clock,
            )
            refresh = asyncio.create_task(nasa.refresh())  # never blocks startup; the API runs on defaults meanwhile
            try:
                yield
            finally:
                refresh.cancel()
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
        mission.router,
        crew.router,
        telemetry.router,
        assessment.router,
        crew_mode.router,
        companion.router,
        actions.router,
        mobility.router,
    ):
        app.include_router(router)

    # Browser test page for the Mobility & Balance Check (MediaPipe runs in the browser, not on the server)
    if MOBILITY_PAGE_DIR.is_dir():
        app.mount("/demo/mobility", StaticFiles(directory=MOBILITY_PAGE_DIR, html=True), name="mobility-demo")

    @app.get("/", tags=["ops"])
    async def root() -> dict[str, str]:
        return {"message": "Nova Healix backend is running!", "disclaimer": DISCLAIMER, "docs": "/docs"}

    @app.get("/health", tags=["ops"])
    async def health_check(request: Request) -> dict[str, str | float]:
        c: Container = request.app.state.container
        return {"status": "ok", "companion": c.companion.mode, "missionHour": round(c.clock.now_hour(), 2)}

    return app


app = create_app()
