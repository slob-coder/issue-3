"""Agent base class with WebSocket support."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class AgentBase(ABC):
    """Base class for building a Werewolf Arena agent.

    Subclass this and implement the action handlers:
    - on_game_start
    - on_night_action
    - on_speech_request
    - on_vote_request
    - on_hunter_shoot
    """

    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.my_role: Optional[str] = None
        self.my_seat: Optional[int] = None
        self.room_id: Optional[str] = None
        self._ws = None
        self._running = False

    @abstractmethod
    async def on_game_start(self, data: dict) -> None:
        """Called when game starts. data contains role, seat, player info."""
        ...

    @abstractmethod
    async def on_night_action(self, data: dict) -> dict:
        """Called during night phase. Return action dict."""
        ...

    @abstractmethod
    async def on_speech_request(self, data: dict) -> dict:
        """Called when it's your turn to speak. Return speech dict."""
        ...

    @abstractmethod
    async def on_vote_request(self, data: dict) -> dict:
        """Called during vote phase. Return vote dict."""
        ...

    async def on_hunter_shoot(self, data: dict) -> dict:
        """Called when hunter dies. Override if playing hunter."""
        return {"target_seat": None}

    async def on_game_end(self, data: dict) -> None:
        """Called when game ends."""
        logger.info("Game ended: winner=%s", data.get("winner"))

    async def connect_and_play(self, room_id: str) -> None:
        """Connect to a room via WebSocket and play the game."""
        self.room_id = room_id
        self._running = True
        ws_url = self.base_url.replace("http", "ws")

        try:
            import websockets

            async with websockets.connect(
                f"{ws_url}/ws/agent/{room_id}?api_key={self.api_key}"
            ) as ws:
                self._ws = ws
                while self._running:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120)
                        message = json.loads(raw)
                        await self._handle_message(message)
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error("WS error: %s", e)
                        break
        except ImportError:
            logger.error("Install websockets: pip install websockets")

    async def _handle_message(self, message: dict) -> None:
        event = message.get("event", "")
        data = message.get("data", {})

        if event == "game.start":
            self.my_role = data.get("your_role")
            self.my_seat = data.get("your_seat")
            await self.on_game_start(data)

        elif event == "phase.night":
            response = await self.on_night_action(data)
            await self._send_action("night_action", response)

        elif event == "phase.day.speech":
            response = await self.on_speech_request(data)
            await self._send_action("speech", response)

        elif event == "phase.day.vote":
            response = await self.on_vote_request(data)
            await self._send_action("vote", response)

        elif event == "phase.hunter.shoot":
            response = await self.on_hunter_shoot(data)
            await self._send_action("hunter_shoot", response)

        elif event == "game.end":
            await self.on_game_end(data)
            self._running = False

    async def _send_action(self, action_type: str, data: dict) -> None:
        if self._ws:
            await self._ws.send(
                json.dumps({"action": action_type, "data": data})
            )
