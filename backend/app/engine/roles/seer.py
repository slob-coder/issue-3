"""Seer role strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.engine.roles.base import ActionResult, RoleStrategy

if TYPE_CHECKING:
    from app.engine.game_state import GameState, PlayerState


class SeerStrategy(RoleStrategy):
    role_id = "seer"
    role_name = "预言家"
    faction = "villager"

    def get_night_action_type(self) -> Optional[str]:
        return "investigate"

    def get_available_targets(
        self, player: PlayerState, alive_players: list[PlayerState]
    ) -> list[int]:
        return [p.seat_number for p in alive_players if p.seat_number != player.seat_number]

    async def execute_night_action(
        self, player: PlayerState, action: dict, game_state: GameState
    ) -> ActionResult:
        target_seat = action.get("target_seat")
        target = game_state.get_player_by_seat(target_seat)
        if not target:
            return ActionResult(type="skip")
        faction = "werewolf" if target.role == "werewolf" else "villager"
        return ActionResult(
            type="investigate",
            target_seat=target_seat,
            result={"faction": faction, "seat": target_seat},
        )
