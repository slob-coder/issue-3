"""Replay service - game history and replay data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.exceptions import GameError
from app.models.game_event import GameEvent as GameEventModel
from app.models.player import Player
from app.models.room import Room

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ReplayService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_full_replay(self, room_id: str) -> dict:
        room = await self.db.get(Room, room_id)
        if not room or room.status != "finished":
            raise GameError("游戏尚未结束")

        events = await self.db.execute(
            select(GameEventModel)
            .where(GameEventModel.room_id == room_id)
            .order_by(GameEventModel.id)
        )
        events_list = events.scalars().all()

        players = await self.db.execute(
            select(Player)
            .where(Player.room_id == room_id)
            .options(joinedload(Player.agent))
            .order_by(Player.seat_number)
        )
        players_list = players.scalars().all()

        return {
            "room": {
                "id": str(room.id),
                "name": room.name,
                "config": room.config,
                "winner": room.winner,
                "started_at": room.started_at.isoformat() if room.started_at else None,
                "finished_at": room.finished_at.isoformat() if room.finished_at else None,
            },
            "players": [
                {
                    "seat": p.seat_number,
                    "role": p.role,
                    "agent_name": p.agent.name if p.agent else "Unknown",
                    "eliminated_at_round": p.eliminated_at_round,
                    "elimination_reason": p.elimination_reason,
                }
                for p in players_list
            ],
            "events": [
                {
                    "id": e.id,
                    "round": e.round_number,
                    "phase": e.phase,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "timestamp": e.created_at.isoformat(),
                }
                for e in events_list
            ],
            "total_rounds": max((e.round_number for e in events_list), default=0),
        }

    async def get_round_replay(self, room_id: str, round_num: int) -> dict:
        events = await self.db.execute(
            select(GameEventModel)
            .where(
                GameEventModel.room_id == room_id,
                GameEventModel.round_number == round_num,
            )
            .order_by(GameEventModel.id)
        )
        return {
            "round": round_num,
            "events": [
                {
                    "id": e.id,
                    "phase": e.phase,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "timestamp": e.created_at.isoformat(),
                }
                for e in events.scalars().all()
            ],
        }

    async def get_public_history(self, room_id: str) -> list[dict]:
        """Get public events (speeches, votes, results) for a room."""
        public_types = {"day.speech", "phase.result", "phase.execution", "game.start", "game.end"}
        events = await self.db.execute(
            select(GameEventModel)
            .where(
                GameEventModel.room_id == room_id,
                GameEventModel.event_type.in_(public_types),
            )
            .order_by(GameEventModel.id)
        )
        return [
            {
                "round": e.round_number,
                "phase": e.phase,
                "event_type": e.event_type,
                "payload": e.payload,
                "timestamp": e.created_at.isoformat(),
            }
            for e in events.scalars().all()
        ]
