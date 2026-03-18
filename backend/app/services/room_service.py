"""Room service - room lifecycle management."""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.engine.game_engine import GameEngine
from app.exceptions import GameError, RoomFullError, RoomNotFoundError
from app.models.player import Player
from app.models.room import Room
from app.schemas.room import RoomCreate

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.config import Settings
    from app.services.agent_scheduler import AgentScheduler
    from app.services.event_bus import EventBus

logger = logging.getLogger(__name__)


class RoomService:
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        event_bus: EventBus,
        scheduler: AgentScheduler,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.db = db
        self.redis = redis
        self.event_bus = event_bus
        self.scheduler = scheduler
        self.settings = settings
        self.session_factory = session_factory

    async def create_room(self, data: RoomCreate) -> Room:
        room = Room(name=data.name, config=data.config.model_dump(), status="waiting")
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)

        await self.redis.hset(
            f"room:{room.id}:state",
            mapping={"phase": "waiting", "round": "0", "alive_seats": "[]"},
        )
        return room

    async def join_room(self, room_id: str, agent_id: str) -> Player:
        room = await self._get_room(room_id)
        if room.status != "waiting":
            raise GameError("房间不在等待状态")

        existing = await self._get_room_players(room_id)
        if len(existing) >= room.config["player_count"]:
            raise RoomFullError()
        if any(str(p.agent_id) == agent_id for p in existing):
            raise GameError("已在房间中")

        seat = len(existing) + 1
        player = Player(
            room_id=room_id, agent_id=agent_id, seat_number=seat, role="unassigned"
        )
        self.db.add(player)
        await self.db.commit()
        await self.db.refresh(player)

        logger.info("Agent %s joined room %s (seat %d)", agent_id, room_id, seat)

        # Auto-start when full
        if len(existing) + 1 >= room.config["player_count"]:
            await self._start_game(room)

        return player

    async def _start_game(self, room: Room) -> None:
        players = await self._get_room_players(str(room.id))
        roles = self._distribute_roles(room.config["roles"], len(players))
        random.shuffle(roles)

        for player, role in zip(players, roles):
            player.role = role

        room.status = "playing"
        room.started_at = datetime.utcnow()
        await self.db.commit()

        engine = GameEngine(
            self.session_factory, self.redis, self.event_bus, self.scheduler, self.settings
        )
        await engine.start_game(str(room.id), players)

    def _distribute_roles(self, roles_config: dict, total: int) -> list[str]:
        roles: list[str] = []
        for role, count in roles_config.items():
            roles.extend([role] * count)
        return roles

    async def list_rooms(
        self, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Room], int]:
        query = select(Room).order_by(Room.created_at.desc())
        if status:
            query = query.where(Room.status == status)

        count_q = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_q)

        result = await self.db.execute(query.offset(offset).limit(limit))
        return list(result.scalars().all()), total or 0

    async def get_room(self, room_id: str) -> Optional[Room]:
        result = await self.db.execute(select(Room).where(Room.id == room_id))
        return result.scalar_one_or_none()

    async def get_room_state(
        self, room_id: str, requester_agent_id: Optional[str] = None
    ) -> dict:
        room = await self._get_room(room_id)
        players = await self._get_room_players(room_id)
        redis_state = await self.redis.hgetall(f"room:{room_id}:state")

        state: dict = {
            "room_id": str(room.id),
            "name": room.name,
            "status": room.status,
            "phase": redis_state.get("phase", room.status),
            "round": int(redis_state.get("round", 0)),
            "players": [],
        }

        for p in players:
            player_info: dict = {
                "seat": p.seat_number,
                "is_alive": p.is_alive,
                "agent_id": str(p.agent_id),
            }
            if requester_agent_id and str(p.agent_id) == requester_agent_id:
                player_info["role"] = p.role
            elif requester_agent_id is None:
                player_info["role"] = p.role  # Spectator sees all
            state["players"].append(player_info)

        return state

    async def _get_room(self, room_id: str) -> Room:
        result = await self.db.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        if not room:
            raise RoomNotFoundError(room_id)
        return room

    async def _get_room_players(self, room_id: str) -> list[Player]:
        result = await self.db.execute(
            select(Player)
            .where(Player.room_id == room_id)
            .options(joinedload(Player.agent))
            .order_by(Player.seat_number)
        )
        return list(result.scalars().all())
