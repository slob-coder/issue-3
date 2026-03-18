"""Room schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class RoomConfig(BaseModel):
    player_count: int = Field(ge=6, le=12, default=8)
    roles: dict[str, int]
    speech_timeout: int = Field(ge=30, le=120, default=60)
    action_timeout: int = Field(ge=30, le=120, default=45)
    vote_timeout: int = Field(ge=30, le=120, default=30)

    @model_validator(mode="after")
    def validate_roles(self) -> "RoomConfig":
        total = sum(self.roles.values())
        if total != self.player_count:
            raise ValueError(f"角色总数 {total} != 玩家数 {self.player_count}")
        if self.roles.get("werewolf", 0) < 1:
            raise ValueError("至少需要1名狼人")
        villager_side = total - self.roles.get("werewolf", 0)
        if self.roles.get("werewolf", 0) >= villager_side:
            raise ValueError("狼人数量必须少于好人阵营")
        return self


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: RoomConfig


class RoomResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    config: dict
    created_at: datetime
    player_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    winner: Optional[str] = None

    model_config = {"from_attributes": True}


class RoomListResponse(BaseModel):
    rooms: list[RoomResponse]
    total: int
