"""Agent schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    owner: Optional[str] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    api_key: str
    created_at: datetime

    model_config = {"from_attributes": True}
