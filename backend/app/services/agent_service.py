"""Agent service - registration and lookup."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from app.models.agent import Agent
from app.schemas.agent import AgentCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: AgentCreate) -> Agent:
        api_key = f"ww_{secrets.token_hex(24)}"
        agent = Agent(name=data.name, api_key=api_key, owner=data.owner)
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get_by_api_key(self, api_key: str) -> Optional[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.api_key == api_key, Agent.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()
