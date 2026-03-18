"""Event bus - Redis Pub/Sub based event distribution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class GameEvent:
    event: str
    room_id: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        return json.dumps(
            {
                "event": self.event,
                "room_id": self.room_id,
                "data": self.data,
                "timestamp": self.timestamp.isoformat(),
            }
        )


class EventBus:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def publish_to_agent(self, room_id: str, agent_id: str, event: GameEvent) -> None:
        await self.redis.publish(f"channel:room:{room_id}:agent:{agent_id}", event.to_json())

    async def publish_to_spectators(self, room_id: str, event: GameEvent) -> None:
        await self.redis.publish(f"channel:room:{room_id}:spectators", event.to_json())

    async def publish_public(
        self, room_id: str, event: GameEvent, agent_ids: list[str]
    ) -> None:
        """Publish to all agents + spectators."""
        await self.publish_to_spectators(room_id, event)
        for agent_id in agent_ids:
            await self.publish_to_agent(room_id, agent_id, event)

    async def persist_event(
        self,
        db: AsyncSession,
        event: GameEvent,
        round_num: int,
        phase: str,
        actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> None:
        from app.models.game_event import GameEvent as GameEventModel

        game_event = GameEventModel(
            room_id=event.room_id,
            round_number=round_num,
            phase=phase,
            event_type=event.event,
            actor_player_id=actor_id,
            target_player_id=target_id,
            payload=event.data,
        )
        db.add(game_event)
        await db.commit()
