"""Action schemas for game interactions."""

from typing import Optional, Union

from pydantic import BaseModel, Field


class NightAction(BaseModel):
    action_type: str  # kill / investigate / heal / poison / heal_or_poison / skip
    target_seat: Optional[int] = None
    chain_of_thought: Optional[str] = None


class SpeechAction(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    chain_of_thought: Optional[str] = None


class VoteAction(BaseModel):
    target_seat: int  # 0 = abstain
    chain_of_thought: Optional[str] = None


class HunterShootAction(BaseModel):
    target_seat: Optional[int] = None
    chain_of_thought: Optional[str] = None


class ActionSubmit(BaseModel):
    """Unified action submission schema."""

    action: str  # night_action / speech / vote / hunter_shoot
    data: dict  # Validated by phase handler
