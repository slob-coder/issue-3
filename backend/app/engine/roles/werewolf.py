"""Werewolf role strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.engine.roles.base import ActionResult, RoleStrategy

if TYPE_CHECKING:
    from app.engine.game_state import GameState, PlayerState


class WerewolfStrategy(RoleStrategy):
    role_id = "werewolf"
    role_name = "狼人"
    faction = "werewolf"

    def get_night_action_type(self) -> Optional[str]:
        return "kill"

    def get_available_targets(
        self, player: PlayerState, alive_players: list[PlayerState]
    ) -> list[int]:
        return [p.seat_number for p in alive_players if p.role != "werewolf"]

    async def execute_night_action(
        self, player: PlayerState, action: dict, game_state: GameState
    ) -> ActionResult:
        target_seat = action.get("target_seat")
        return ActionResult(type="kill", target_seat=target_seat)
