"""Agent API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_agent_service
from app.schemas.agent import AgentCreate, AgentResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=201)
async def register_agent(
    data: AgentCreate,
    agent_service: AgentService = Depends(get_agent_service),
):
    agent = await agent_service.register(data)
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    agent_service: AgentService = Depends(get_agent_service),
):
    agent = await agent_service.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return AgentResponse.model_validate(agent)
