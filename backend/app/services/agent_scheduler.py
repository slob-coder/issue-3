"""Agent scheduler - timeout management and connection tracking."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.services.event_bus import EventBus

logger = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(self, redis: Redis, event_bus: EventBus):
        self.redis = redis
        self.event_bus = event_bus
        self._running = False

    async def request_action(
        self, room_id: str, player_id: str, action_type: str, timeout: int
    ) -> None:
        expiry = time.time() + timeout
        await self.redis.zadd(
            "room:timeouts",
            {f"{room_id}:{player_id}:{action_type}": expiry},
        )

    async def cancel_timeout(
        self, room_id: str, player_id: str, action_type: str
    ) -> None:
        await self.redis.zrem("room:timeouts", f"{room_id}:{player_id}:{action_type}")

    async def run_timeout_checker(self, interval: float = 1.0) -> None:
        """Background task that fires timeout callbacks."""
        self._running = True
        while self._running:
            now = time.time()
            expired = await self.redis.zrangebyscore("room:timeouts", 0, now)
            for key in expired:
                await self.redis.zrem("room:timeouts", key)
                parts = key.split(":", 2)
                if len(parts) == 3:
                    room_id, player_id, action_type = parts
                    await self._handle_timeout(room_id, player_id, action_type)
            await asyncio.sleep(interval)

    async def _handle_timeout(
        self, room_id: str, player_id: str, action_type: str
    ) -> None:
        from app.engine.game_engine import GameEngine

        engine = GameEngine.get_engine(room_id)
        if engine and room_id in engine._game_states:
            game_state = engine._game_states[room_id]
            handler = engine.phase_handlers.get(game_state.phase)
            if handler:
                logger.info(
                    "Timeout: room=%s player=%s action=%s", room_id, player_id, action_type
                )
                await handler.on_timeout(game_state, player_id)

    async def track_connection(
        self, room_id: str, agent_id: str, connected: bool
    ) -> None:
        await self.redis.hset(
            f"room:{room_id}:connections",
            mapping={
                agent_id: "connected" if connected else "disconnected",
                f"{agent_id}:last_seen": str(time.time()),
            },
        )

    def stop(self) -> None:
        self._running = False
