"""FastAPI dependency injection."""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_service import AgentService
from app.services.event_bus import EventBus
from app.services.replay_service import ReplayService
from app.services.room_service import RoomService


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def get_session_factory(request: Request):
    return request.app.state.session_factory


async def get_redis(request: Request):
    return request.app.state.redis


async def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


async def get_scheduler(request: Request):
    return request.app.state.scheduler


async def get_settings(request: Request):
    return request.app.state.settings


async def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    return AgentService(db)


async def get_room_service(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    event_bus: EventBus = Depends(get_event_bus),
    scheduler=Depends(get_scheduler),
    settings=Depends(get_settings),
    session_factory=Depends(get_session_factory),
) -> RoomService:
    return RoomService(db, redis, event_bus, scheduler, settings, session_factory)


async def get_replay_service(db: AsyncSession = Depends(get_db)) -> ReplayService:
    return ReplayService(db)
