from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.routers import crew, mirror_gap, settings as settings_router, space_weather
from app.services.donki_client import DonkiClient

DISCLAIMER = (
    "Decision support prototype, not a medical device. "
    "Crew data is simulated; space-weather data is real NASA data."
)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if container is not None:
            app.state.container = container
            yield
            return
        async with httpx.AsyncClient() as http:
            donki = DonkiClient(http, settings.donki_base_url, settings.nasa_api_key,
                                settings.donki_timeout_seconds)
            app.state.container = build_container(settings, donki)
            yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=f"RIDGE Monitor backend. **{DISCLAIMER}**",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["*"], allow_headers=["*"],
    )
    for r in (space_weather.router, crew.router, mirror_gap.router, settings_router.router):
        app.include_router(r)

    @app.get("/", tags=["meta"])
    async def root():
        return {"message": "RIDGE Monitor backend is running!", "disclaimer": DISCLAIMER, "docs": "/docs"}

    @app.get("/health", tags=["meta"])
    async def health_check():
        return {"status": "healthy"}

    return app


app = create_app()
