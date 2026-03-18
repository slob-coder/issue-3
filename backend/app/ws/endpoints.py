"""WebSocket endpoints for agents and spectators."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.engine.game_engine import GameEngine
from app.models.agent import Agent
from app.models.player import Player
from app.schemas.action import ActionSubmit
from app.ws.hub import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/agent/{room_id}")
async def agent_ws_endpoint(ws: WebSocket, room_id: str):
    """Agent WebSocket - bidirectional game communication."""
    redis = ws.app.state.redis

    # Authenticate
    api_key = ws.query_params.get("api_key")
    if not api_key:
        await ws.close(code=4001, reason="Missing API key")
        return

    # Look up agent
    session_factory = ws.app.state.session_factory
    async with session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.api_key == api_key, Agent.is_active == True)  # noqa: E712
        )
        agent = result.scalar_one_or_none()

    if not agent:
        await ws.close(code=4003, reason="Invalid API key")
        return

    agent_id = str(agent.id)
    await manager.connect_agent(ws, agent_id, room_id)
    await ws.app.state.scheduler.track_connection(room_id, agent_id, connected=True)

    # Subscribe to agent's channel
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"channel:room:{room_id}:agent:{agent_id}")

    async def forward_redis_to_ws():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await ws.send_text(message["data"])
        except Exception:
            pass

    async def receive_agent_actions():
        try:
            while True:
                data = await ws.receive_json()
                action = ActionSubmit.model_validate(data)
                engine = GameEngine.get_engine(room_id)
                if engine:
                    async with session_factory() as db:
                        result = await db.execute(
                            select(Player).where(
                                Player.room_id == room_id,
                                Player.agent_id == agent_id,
                            )
                        )
                        player = result.scalar_one_or_none()
                    if player:
                        await engine.handle_action(
                            room_id, str(player.id), action.model_dump()
                        )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Agent WS error: %s", e)

    # Run both tasks concurrently
    redis_task = asyncio.create_task(forward_redis_to_ws())
    action_task = asyncio.create_task(receive_agent_actions())

    try:
        done, pending = await asyncio.wait(
            [redis_task, action_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    finally:
        await manager.disconnect_agent(agent_id)
        await ws.app.state.scheduler.track_connection(room_id, agent_id, connected=False)
        await pubsub.unsubscribe()
        await pubsub.close()


@router.websocket("/ws/spectate/{room_id}")
async def spectator_ws_endpoint(ws: WebSocket, room_id: str):
    """Spectator WebSocket - receive-only game events with god view."""
    redis = ws.app.state.redis

    await manager.connect_spectator(ws, room_id)

    pubsub = redis.pubsub()
    await pubsub.subscribe(f"channel:room:{room_id}:spectators")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Spectator WS error: %s", e)
    finally:
        await manager.disconnect_spectator(ws, room_id)
        await pubsub.unsubscribe()
        await pubsub.close()
