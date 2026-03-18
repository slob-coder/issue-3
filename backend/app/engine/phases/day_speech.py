"""Day speech phase handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.engine.phases.base import PhaseHandler
from app.services.event_bus import GameEvent

if TYPE_CHECKING:
    from app.engine.game_state import GameState

logger = logging.getLogger(__name__)


class DaySpeechPhaseHandler(PhaseHandler):
    """Handle sequential speeches by alive players."""

    async def enter(self, game_state: GameState) -> None:
        game_state.phase = "day_speech"
        game_state.speeches_this_round = []
        game_state.speaker_order = list(game_state.alive_seats)
        game_state.speaker_index = 0
        await game_state.sync_to_redis(self.engine.redis)

        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="phase.day",
                room_id=game_state.room_id,
                data={
                    "round": game_state.round_number,
                    "message": "白天讨论阶段开始",
                    "speaker_order": game_state.speaker_order,
                },
            ),
        )

        await self._prompt_next_speaker(game_state)

    async def _prompt_next_speaker(self, game_state: GameState) -> None:
        if game_state.speaker_index >= len(game_state.speaker_order):
            # All done, transition to vote
            await self.engine.transition_to("day_vote", game_state)
            return

        seat = game_state.speaker_order[game_state.speaker_index]
        game_state.current_speaker_seat = seat
        player = game_state.get_player_by_seat(seat)
        if not player or not player.is_alive:
            game_state.speaker_index += 1
            await self._prompt_next_speaker(game_state)
            return

        event_data = {
            "round": game_state.round_number,
            "your_seat": seat,
            "current_speaker": seat,
            "timeout": self.engine.settings.default_speech_timeout,
            "previous_speeches": game_state.speeches_this_round,
            "context": {
                "alive_players": game_state.alive_seats,
                "eliminated_last_night": game_state.eliminated_last_night,
                "speaker_order": game_state.speaker_order,
                "speakers_remaining": game_state.speaker_order[game_state.speaker_index + 1 :],
            },
        }

        await self.event_bus.publish_to_agent(
            game_state.room_id,
            player.agent_id,
            GameEvent(event="phase.day.speech", room_id=game_state.room_id, data=event_data),
        )
        await self.engine.scheduler.request_action(
            game_state.room_id,
            player.player_id,
            "speech",
            self.engine.settings.default_speech_timeout,
        )

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player:
            return

        # Verify it's this player's turn
        if player.seat_number != game_state.current_speaker_seat:
            return

        data = action.get("data", action)
        content = data.get("content", "（无发言）")
        cot = data.get("chain_of_thought")

        speech = {"seat": player.seat_number, "content": content}
        game_state.speeches_this_round.append(speech)

        # Cancel timeout
        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, "speech"
        )

        # Broadcast speech to all agents + spectators
        broadcast_data = {
            "round": game_state.round_number,
            "seat": player.seat_number,
            "content": content,
        }
        agent_ids = [p.agent_id for p in game_state.alive_players]
        await self.event_bus.publish_public(
            game_state.room_id,
            GameEvent(event="day.speech.broadcast", room_id=game_state.room_id, data=broadcast_data),
            agent_ids,
        )

        # Send CoT only to spectators
        if cot:
            await self.event_bus.publish_to_spectators(
                game_state.room_id,
                GameEvent(
                    event="day.speech.cot",
                    room_id=game_state.room_id,
                    data={"seat": player.seat_number, "chain_of_thought": cot},
                ),
            )

        # Persist
        await self.event_bus.persist_event(
            self.engine.db,
            GameEvent(event="day.speech", room_id=game_state.room_id, data=broadcast_data),
            game_state.round_number,
            "day_speech",
            actor_id=player.player_id,
        )

        # Next speaker
        game_state.speaker_index += 1
        await self._prompt_next_speaker(game_state)

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        player = game_state.get_player_by_id(player_id)
        if player:
            speech = {"seat": player.seat_number, "content": "（超时未发言）"}
            game_state.speeches_this_round.append(speech)
            logger.info("Speech timeout: seat=%d", player.seat_number)

        game_state.speaker_index += 1
        await self._prompt_next_speaker(game_state)
