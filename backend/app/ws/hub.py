"""WebSocket connection manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.agent_connections: dict[str, WebSocket] = {}
        self.spectator_connections: dict[str, list[WebSocket]] = {}

    async def connect_agent(
        self, ws: WebSocket, agent_id: str, room_id: str, *, accept: bool = True
    ) -> None:
        if accept:
            await ws.accept()
        self.agent_connections[agent_id] = ws
        logger.info("Agent %s connected to room %s", agent_id, room_id)

    async def disconnect_agent(self, agent_id: str) -> None:
        self.agent_connections.pop(agent_id, None)

    async def connect_spectator(self, ws: WebSocket, room_id: str) -> None:
        await ws.accept()
        self.spectator_connections.setdefault(room_id, []).append(ws)
        logger.info("Spectator connected to room %s", room_id)

    async def disconnect_spectator(self, ws: WebSocket, room_id: str) -> None:
        if room_id in self.spectator_connections:
            self.spectator_connections[room_id] = [
                c for c in self.spectator_connections[room_id] if c != ws
            ]


manager = ConnectionManager()
