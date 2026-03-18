"""Tests for room API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_room(client: AsyncClient):
    resp = await client.post(
        "/api/v1/rooms",
        json={
            "name": "Test Room",
            "config": {
                "player_count": 8,
                "roles": {
                    "werewolf": 2,
                    "seer": 1,
                    "witch": 1,
                    "hunter": 1,
                    "villager": 3,
                },
            },
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Room"
    assert data["status"] == "waiting"


@pytest.mark.asyncio
async def test_list_rooms(client: AsyncClient):
    resp = await client.get("/api/v1/rooms")
    assert resp.status_code == 200
    data = resp.json()
    assert "rooms" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_create_room_invalid_roles(client: AsyncClient):
    resp = await client.post(
        "/api/v1/rooms",
        json={
            "name": "Bad Room",
            "config": {
                "player_count": 8,
                "roles": {"werewolf": 5, "villager": 3},
            },
        },
    )
    assert resp.status_code == 422  # Validation error
