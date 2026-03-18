"""Authentication middleware and dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import Depends, Header, HTTPException

from app.models.agent import Agent
from app.services.agent_service import AgentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_agent(
    x_api_key: str = Header(..., alias="X-API-Key"),
    agent_service: AgentService = Depends(),
) -> Agent:
    agent = await agent_service.get_by_api_key(x_api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return agent


async def get_optional_agent(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    agent_service: AgentService = Depends(),
) -> Optional[Agent]:
    if not x_api_key:
        return None
    agent = await agent_service.get_by_api_key(x_api_key)
    return agent
