"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import Settings
from app.db.redis import create_redis
from app.db.session import create_session_factory
from app.engine.roles.registry import RoleRegistry
from app.exceptions import GameError, game_error_handler
from app.services.agent_scheduler import AgentScheduler
from app.services.event_bus import EventBus
from app.ws.endpoints import router as ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    settings = Settings()
    app.state.settings = settings

    # Database
    app.state.session_factory = create_session_factory(settings.database_url)

    # Redis
    app.state.redis = await create_redis(settings.redis_url)

    # Event bus
    app.state.event_bus = EventBus(app.state.redis)

    # Scheduler
    app.state.scheduler = AgentScheduler(app.state.redis, app.state.event_bus)

    # Load roles
    RoleRegistry.load_defaults()

    # CORS (configured via settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Start timeout checker
    timeout_task = asyncio.create_task(
        app.state.scheduler.run_timeout_checker(settings.timeout_check_interval)
    )

    logger.info("Werewolf Arena backend started")
    yield

    # Shutdown
    app.state.scheduler.stop()
    timeout_task.cancel()
    try:
        await timeout_task
    except asyncio.CancelledError:
        pass
    await app.state.redis.close()
    logger.info("Werewolf Arena backend stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Werewolf Arena",
        description="AI Agent Werewolf Game Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Exception handlers
    app.add_exception_handler(GameError, game_error_handler)

    # Routers
    app.include_router(api_router)
    app.include_router(ws_router)

    # Health checks
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        try:
            await app.state.redis.ping()
            return {"status": "ready", "redis": "ok"}
        except Exception:
            return {"status": "not_ready", "redis": "error"}

    return app


app = create_app()
