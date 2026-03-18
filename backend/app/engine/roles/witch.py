"""Witch role strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.engine.roles.base import ActionResult, RoleStrategy

if TYPE_CHECKING:
    from app.engine.game_state import GameState, PlayerState


class WitchStrategy(RoleStrategy):
    role_id = "witch"
    role_name = "女巫"
    faction = "villager"

    def get_night_action_type(self) -> Optional[str]:
        return "heal_or_poison"

    def get_available_targets(
        self, player: PlayerState, alive_players: list[PlayerState]
    ) -> list[int]:
        return [p.seat_number for p in alive_players if p.seat_number != player.seat_number]

    async def execute_night_action(
        self, player: PlayerState, action: dict, game_state: GameState
    ) -> ActionResult:
        action_type = action.get("action_type", "skip")

        if action_type == "heal":
            if game_state.witch_heal_remaining <= 0:
                return ActionResult(type="skip")
            return ActionResult(type="heal", cancel_kill=True)

        if action_type == "poison":
            if game_state.witch_poison_remaining <= 0:
                return ActionResult(type="skip")
            target_seat = action.get("target_seat")
            return ActionResult(type="poison", target_seat=target_seat)

        return ActionResult(type="skip")
