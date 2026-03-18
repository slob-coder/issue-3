"""Tests for agent API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_agent(client: AsyncClient):
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "my-ai-agent"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my-ai-agent"
    assert data["api_key"].startswith("ww_")


@pytest.mark.asyncio
async def test_get_agent(client: AsyncClient, api_key: str):
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "lookup-agent"},
    )
    agent_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "lookup-agent"
