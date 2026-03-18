"""Event schemas for WebSocket messages."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GameEventSchema(BaseModel):
    event: str
    data: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    room_id: uuid.UUID
