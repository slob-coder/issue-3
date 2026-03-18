"""Role strategy base class and ActionResult."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.engine.game_state import GameState, PlayerState


@dataclass
class ActionResult:
    type: str  # kill / investigate / heal / poison / shoot / skip
    target_seat: Optional[int] = None
    result: Optional[dict] = None
    cancel_kill: bool = False


class RoleStrategy(ABC):
    """Base class for role behaviour."""

    role_id: str
    role_name: str
    faction: str  # "werewolf" | "villager"

    @abstractmethod
    def get_night_action_type(self) -> Optional[str]:
        ...

    @abstractmethod
    def get_available_targets(
        self, player: PlayerState, alive_players: list[PlayerState]
    ) -> list[int]:
        ...

    @abstractmethod
    async def execute_night_action(
        self, player: PlayerState, action: dict, game_state: GameState
    ) -> ActionResult:
        ...

    def validate_action(self, action: dict, player: PlayerState, game_state: GameState) -> bool:
        target_seat = action.get("target_seat")
        if target_seat is not None:
            available = self.get_available_targets(player, game_state.alive_players)
            return target_seat in available
        return True
