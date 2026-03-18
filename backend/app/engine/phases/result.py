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
    """Announce night results and transition to day or check_win.

    If the hunter is killed at night, prompts for their death shot before
    proceeding.
    """

    async def enter(self, game_state: GameState, **kwargs) -> None:
        game_state.phase = "result"
        eliminated: list[dict] = []
        hunter_death_pending = False
        hunter_player = None

        # Werewolf kill
        if game_state.night_kill_target:
            target = game_state.get_player_by_seat(game_state.night_kill_target)
            if target and target.is_alive:
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "killed"
                eliminated.append({"seat": target.seat_number, "reason": "killed"})
                await self._update_player_db(target)
                if target.role == "hunter":
                    hunter_death_pending = True
                    hunter_player = target

        # Witch poison
        if game_state.night_poison_target:
            target = game_state.get_player_by_seat(game_state.night_poison_target)
            if target and target.is_alive:
                target.is_alive = False
                target.eliminated_at_round = game_state.round_number
                target.elimination_reason = "poisoned"
                eliminated.append({"seat": target.seat_number, "reason": "poisoned"})
                await self._update_player_db(target)
                # Hunter poisoned by witch cannot shoot (standard rule)
                if target.role == "hunter":
                    # Poisoned hunter cannot use ability
                    pass

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

        # Also notify eliminated players (they need to see the result)
        for e in eliminated:
            dead_player = game_state.get_player_by_seat(e["seat"])
            if dead_player:
                await self.event_bus.publish_to_agent(
                    game_state.room_id,
                    dead_player.agent_id,
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
        async with self.engine.session_factory() as db:
            await self.engine.event_bus.persist_event(
                db,
                GameEvent(event="phase.result", room_id=game_state.room_id, data=result_data),
                game_state.round_number,
                "result",
            )

        # Hunter killed by werewolf gets to shoot
        if hunter_death_pending and hunter_player:
            await self._handle_hunter_death(game_state, hunter_player)
        else:
            # Check win before going to day
            await self.engine.transition_to("check_win", game_state, from_phase="result")

    async def _handle_hunter_death(
        self, game_state: GameState, hunter: PlayerState
    ) -> None:
        """Prompt the hunter to use their death shot ability."""
        await self.event_bus.publish_to_agent(
            game_state.room_id,
            hunter.agent_id,
            GameEvent(
                event="phase.hunter.shoot",
                room_id=game_state.room_id,
                data={
                    "your_seat": hunter.seat_number,
                    "reason": "killed",
                    "available_targets": list(game_state.alive_seats),
                    "timeout": self.engine.settings.default_action_timeout,
                    "message": "你被杀害了！作为猎人，你可以开枪带走一名玩家。",
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
        """Handle hunter's death shot during result phase."""
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

                # Broadcast hunter shot
                shot_data = {
                    "round": game_state.round_number,
                    "hunter_seat": player.seat_number,
                    "target_seat": target_seat,
                    "message": f"猎人 {player.seat_number} 号开枪带走了 {target_seat} 号",
                }
                for p in game_state.alive_players:
                    await self.event_bus.publish_to_agent(
                        game_state.room_id,
                        p.agent_id,
                        GameEvent(event="phase.hunter.shot", room_id=game_state.room_id, data=shot_data),
                    )
                await self.event_bus.publish_to_spectators(
                    game_state.room_id,
                    GameEvent(
                        event="phase.hunter.shot",
                        room_id=game_state.room_id,
                        data={**shot_data, "target_role": target.role},
                    ),
                )

        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, "hunter_shoot"
        )
        await self.engine.transition_to("check_win", game_state, from_phase="result")

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        """Hunter didn't shoot — move on."""
        player = game_state.get_player_by_id(player_id)
        if player:
            logger.info("Hunter shoot timeout: seat=%d (skip)", player.seat_number)
        await self.engine.transition_to("check_win", game_state, from_phase="result")

    def _build_message(self, eliminated: list[dict]) -> str:
        if not eliminated:
            return "昨晚是平安夜，无人遇害"
        seats = ", ".join(str(e["seat"]) for e in eliminated)
        return f"昨晚 {seats} 号被杀害"

    async def _update_player_db(self, player_state: PlayerState) -> None:
        async with self.engine.session_factory() as db:
            await db.execute(
                update(Player)
                .where(Player.id == player_state.player_id)
                .values(
                    is_alive=player_state.is_alive,
                    eliminated_at_round=player_state.eliminated_at_round,
                    elimination_reason=player_state.elimination_reason,
                )
            )
            await db.commit()
