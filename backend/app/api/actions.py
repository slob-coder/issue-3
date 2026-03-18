"""Action API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_db
from app.engine.game_engine import GameEngine
from app.middleware.auth import get_current_agent
from app.models.agent import Agent
from app.models.player import Player
from app.schemas.action import ActionSubmit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/rooms/{room_id}/actions", tags=["actions"])


async def _get_player(db: AsyncSession, room_id: str, agent_id: str) -> Player:
    result = await db.execute(
        select(Player).where(Player.room_id == room_id, Player.agent_id == agent_id)
    )
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(404, "Not a player in this room")
    return player


@router.post("")
async def submit_action(
    room_id: uuid.UUID,
    action: ActionSubmit,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    engine = GameEngine.get_engine(str(room_id))
    if not engine:
        raise HTTPException(400, "Game not active")

    player = await _get_player(db, str(room_id), str(agent.id))
    await engine.handle_action(str(room_id), str(player.id), action.model_dump())
    return {"status": "accepted"}
