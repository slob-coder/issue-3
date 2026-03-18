"""Execution phase handler - apply vote results."""

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


class ExecutionPhaseHandler(PhaseHandler):
    """Execute the voted player and handle hunter death."""

    async def enter(self, game_state: GameState, **kwargs) -> None:
        game_state.phase = "execution"
        eliminated_seat = kwargs.get("eliminated_seat")
        vote_counts = kwargs.get("vote_counts", {})

        target_player = None
        hunter_death_pending = False

        if eliminated_seat:
            target_player = game_state.get_player_by_seat(eliminated_seat)
            if target_player and target_player.is_alive:
                target_player.is_alive = False
                target_player.eliminated_at_round = game_state.round_number
                target_player.elimination_reason = "voted"
                await self._update_player_db(target_player)

                if target_player.role == "hunter":
                    hunter_death_pending = True

        result_data = {
            "round": game_state.round_number,
            "eliminated_seat": eliminated_seat,
            "vote_counts": vote_counts,
            "is_tie": eliminated_seat is None and bool(vote_counts),
        }

        # Broadcast to agents
        for player in game_state.alive_players:
            await self.event_bus.publish_to_agent(
                game_state.room_id,
                player.agent_id,
                GameEvent(event="phase.execution", room_id=game_state.room_id, data=result_data),
            )

        # Spectators get role info
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="phase.execution",
                room_id=game_state.room_id,
                data={
                    **result_data,
                    "eliminated_role": target_player.role if target_player else None,
                },
            ),
        )

        # Persist
        await self.event_bus.persist_event(
            self.engine.db,
            GameEvent(event="phase.execution", room_id=game_state.room_id, data=result_data),
            game_state.round_number,
            "execution",
        )

        if hunter_death_pending and target_player:
            await self._handle_hunter_death(game_state, target_player)
        else:
            await self.engine.transition_to("check_win", game_state)

    async def _handle_hunter_death(
        self, game_state: GameState, hunter: PlayerState
    ) -> None:
        await self.event_bus.publish_to_agent(
            game_state.room_id,
            hunter.agent_id,
            GameEvent(
                event="phase.hunter.shoot",
                room_id=game_state.room_id,
                data={
                    "your_seat": hunter.seat_number,
                    "available_targets": [s for s in game_state.alive_seats],
                    "timeout": self.engine.settings.default_action_timeout,
                },
            ),
        )
        await self.engine.scheduler.request_action(
            game_state.room_id,
            hunter.player_id,
            "hunter_shoot",
            self.engine.settings.default_action_timeout,
        )

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player or player.role != "hunter":
            return

        data = action.get("data", action)
        target_seat = data.get("target_seat")
        if target_seat and target_seat in game_state.alive_seats:
            target = game_state.get_player_by_seat(target_seat)
            if target:
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "hunter_shot"
                await self._update_player_db(target)

        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, "hunter_shoot"
        )
        await self.engine.transition_to("check_win", game_state)

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        # Hunter didn't shoot — move on
        await self.engine.transition_to("check_win", game_state)

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
