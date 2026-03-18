"""Villager role strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.engine.roles.base import ActionResult, RoleStrategy

if TYPE_CHECKING:
    from app.engine.game_state import GameState, PlayerState


class VillagerStrategy(RoleStrategy):
    role_id = "villager"
    role_name = "村民"
    faction = "villager"

    def get_night_action_type(self) -> Optional[str]:
        return None

    def get_available_targets(
        self, player: PlayerState, alive_players: list[PlayerState]
    ) -> list[int]:
        return []

    async def execute_night_action(
        self, player: PlayerState, action: dict, game_state: GameState
    ) -> ActionResult:
        return ActionResult(type="skip")
