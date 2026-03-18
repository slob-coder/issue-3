"""Werewolf Arena API client."""

from __future__ import annotations

from typing import Optional

import httpx


class WerewolfClient:
    """HTTP client for the Werewolf Arena platform."""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._build_headers(),
            timeout=30.0,
        )

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def register_agent(self, name: str, owner: Optional[str] = None) -> dict:
        """Register a new agent and get API key."""
        resp = await self._client.post("/api/v1/agents", json={"name": name, "owner": owner})
        resp.raise_for_status()
        data = resp.json()
        self.api_key = data["api_key"]
        self._client.headers["X-API-Key"] = data["api_key"]
        return data

    async def create_room(
        self, name: str, player_count: int = 8, roles: Optional[dict] = None
    ) -> dict:
        """Create a game room."""
        if roles is None:
            roles = {
                "werewolf": 2,
                "seer": 1,
                "witch": 1,
                "hunter": 1,
                "villager": player_count - 5,
            }
        resp = await self._client.post(
            "/api/v1/rooms",
            json={
                "name": name,
                "config": {"player_count": player_count, "roles": roles},
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def join_room(self, room_id: str) -> dict:
        """Join a game room."""
        resp = await self._client.post(f"/api/v1/rooms/{room_id}/join")
        resp.raise_for_status()
        return resp.json()

    async def list_rooms(self, status: Optional[str] = None) -> dict:
        """List available rooms."""
        params = {}
        if status:
            params["status"] = status
        resp = await self._client.get("/api/v1/rooms", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_room_state(self, room_id: str) -> dict:
        """Get current room state."""
        resp = await self._client.get(f"/api/v1/rooms/{room_id}/state")
        resp.raise_for_status()
        return resp.json()

    async def submit_action(self, room_id: str, action: str, data: dict) -> dict:
        """Submit a game action."""
        resp = await self._client.post(
            f"/api/v1/rooms/{room_id}/actions",
            json={"action": action, "data": data},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_replay(self, room_id: str) -> dict:
        """Get full game replay."""
        resp = await self._client.get(f"/api/v1/rooms/{room_id}/replay")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
