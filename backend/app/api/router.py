"""API router aggregation."""

from fastapi import APIRouter

from app.api import actions, agents, replay, rooms

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(rooms.router)
api_router.include_router(agents.router)
api_router.include_router(actions.router)
api_router.include_router(replay.router)
