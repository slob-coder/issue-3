"""Replay API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.deps import get_replay_service
from app.services.replay_service import ReplayService

router = APIRouter(prefix="/rooms/{room_id}/replay", tags=["replay"])


@router.get("")
async def get_replay(
    room_id: uuid.UUID,
    replay_service: ReplayService = Depends(get_replay_service),
):
    return await replay_service.get_full_replay(str(room_id))


@router.get("/rounds/{round_num}")
async def get_round_replay(
    room_id: uuid.UUID,
    round_num: int,
    replay_service: ReplayService = Depends(get_replay_service),
):
    return await replay_service.get_round_replay(str(room_id), round_num)
