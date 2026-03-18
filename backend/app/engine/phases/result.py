"""Result phase handler - announce night results, then transition."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import update

from app.engine.phases.base import PhaseHandler
from app.models.player import Player
from app.services.event_bus import GameEvent

if TYPE_CHECKING:
    from app.engine.game_state import GameState, PlayerState

logger = logging.getLogger(__name__)


class ResultPhaseHandler(PhaseHandler):
    """Announce night results and transition to day or check_win."""

    async def enter(self, game_state: GameState) -> None:
        game_state.phase = "result"
        eliminated: list[dict] = []

        # Werewolf kill
        if game_state.night_kill_target:
            target = game_state.get_player_by_seat(game_state.night_kill_target)
            if target and target.is_alive:
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "killed"
                eliminated.append({"seat": target.seat_number, "reason": "killed"})
                await self._update_player_db(target)

        # Witch poison
        if game_state.night_poison_target:
            target = game_state.get_player_by_seat(game_state.night_poison_target)
            if target and target.is_alive:
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "poisoned"
                eliminated.append({"seat": target.seat_number, "reason": "poisoned"})
                await self._update_player_db(target)

        game_state.eliminated_last_night = eliminated

        # Announce to agents
        result_data = {
            "round": game_state.round_number,
            "phase": "night",
            "eliminated": [{"seat": e["seat"], "reason": e["reason"]} for e in eliminated],
            "message": self._build_message(eliminated),
        }

        for player in game_state.alive_players:
            await self.event_bus.publish_to_agent(
                game_state.room_id,
                player.agent_id,
                GameEvent(event="phase.result", room_id=game_state.room_id, data=result_data),
            )

        # Spectators get roles
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="phase.result",
                room_id=game_state.room_id,
                data={
                    **result_data,
                    "eliminated_roles": {
                        e["seat"]: game_state.get_player_by_seat(e["seat"]).role
                        for e in eliminated
                        if game_state.get_player_by_seat(e["seat"])
                    },
                },
            ),
        )

        # Persist
        await self.event_bus.persist_event(
            self.engine.db,
            GameEvent(event="phase.result", room_id=game_state.room_id, data=result_data),
            game_state.round_number,
            "result",
        )

        # Check win before going to day
        await self.engine.transition_to("check_win", game_state)

    def _build_message(self, eliminated: list[dict]) -> str:
        if not eliminated:
            return "昨晚是平安夜，无人遇害"
        seats = ", ".join(str(e["seat"]) for e in eliminated)
        return f"昨晚 {seats} 号被杀害"

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        pass  # No actions during result phase

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        pass

    async def _update_player_db(self, player_state: PlayerState) -> None:
        await self.engine.db.execute(
            update(Player)
            .where(Player.id == player_state.player_id)
            .values(
                is_alive=player_state.is_alive,
                eliminated_at_round=player_state.eliminated_at_round,
                elimination_reason=player_state.elimination_reason,
            )
        )
        await self.engine.db.commit()
