"""Room API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_replay_service, get_room_service
from app.middleware.auth import get_current_agent, get_optional_agent
from app.models.agent import Agent
from app.schemas.room import RoomCreate, RoomListResponse, RoomResponse
from app.services.replay_service import ReplayService
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(
    data: RoomCreate,
    room_service: RoomService = Depends(get_room_service),
):
    room = await room_service.create_room(data)
    return RoomResponse.model_validate(room)


@router.get("", response_model=RoomListResponse)
async def list_rooms(
    status: Optional[str] = Query(None, pattern="^(waiting|playing|finished)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    room_service: RoomService = Depends(get_room_service),
):
    rooms, total = await room_service.list_rooms(status, limit, offset)
    return RoomListResponse(
        rooms=[RoomResponse.model_validate(r) for r in rooms],
        total=total,
    )


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: uuid.UUID,
    room_service: RoomService = Depends(get_room_service),
):
    room = await room_service.get_room(str(room_id))
    if not room:
        raise HTTPException(404, "Room not found")
    return RoomResponse.model_validate(room)


@router.post("/{room_id}/join")
async def join_room(
    room_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    room_service: RoomService = Depends(get_room_service),
):
    player = await room_service.join_room(str(room_id), str(agent.id))
    return {"seat": player.seat_number, "player_id": str(player.id)}


@router.get("/{room_id}/state")
async def get_room_state(
    room_id: uuid.UUID,
    agent: Optional[Agent] = Depends(get_optional_agent),
    room_service: RoomService = Depends(get_room_service),
):
    agent_id = str(agent.id) if agent else None
    return await room_service.get_room_state(str(room_id), agent_id)


@router.get("/{room_id}/history")
async def get_room_history(
    room_id: uuid.UUID,
    replay_service: ReplayService = Depends(get_replay_service),
):
    return await replay_service.get_public_history(str(room_id))
