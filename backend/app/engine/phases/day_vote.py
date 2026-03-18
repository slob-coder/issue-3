"""Day vote phase handler."""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING

from app.engine.phases.base import PhaseHandler
from app.services.event_bus import GameEvent

if TYPE_CHECKING:
    from app.engine.game_state import GameState

logger = logging.getLogger(__name__)


class DayVotePhaseHandler(PhaseHandler):
    """Handle simultaneous voting."""

    async def enter(self, game_state: GameState) -> None:
        game_state.phase = "day_vote"
        game_state.day_votes = {}
        await game_state.sync_to_redis(self.engine.redis)

        candidates = game_state.alive_seats
        for player in game_state.alive_players:
            event_data = {
                "round": game_state.round_number,
                "your_seat": player.seat_number,
                "candidates": candidates,
                "timeout": self.engine.settings.default_vote_timeout,
                "speeches": game_state.speeches_this_round,
                "context": {"alive_players": candidates},
            }
            await self.event_bus.publish_to_agent(
                game_state.room_id,
                player.agent_id,
                GameEvent(event="phase.day.vote", room_id=game_state.room_id, data=event_data),
            )
            await self.engine.scheduler.request_action(
                game_state.room_id,
                player.player_id,
                "vote",
                self.engine.settings.default_vote_timeout,
            )

        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="phase.day.vote",
                room_id=game_state.room_id,
                data={
                    "round": game_state.round_number,
                    "candidates": candidates,
                    "message": "投票阶段开始",
                },
            ),
        )

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player or player_id in game_state.day_votes:
            return

        data = action.get("data", action)
        target_seat = data.get("target_seat", 0)
        game_state.day_votes[player_id] = target_seat

        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, "vote"
        )

        # Notify spectators of individual vote
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="day.vote.cast",
                room_id=game_state.room_id,
                data={
                    "from_seat": player.seat_number,
                    "to_seat": target_seat,
                    "chain_of_thought": data.get("chain_of_thought"),
                },
            ),
        )

        # Check if all alive players have voted
        if len(game_state.day_votes) >= len(game_state.alive_players):
            await self._tally_votes(game_state)

    async def _tally_votes(self, game_state: GameState) -> None:
        vote_counts: Counter = Counter()
        for player_id, target_seat in game_state.day_votes.items():
            if target_seat != 0:  # 0 = abstain
                vote_counts[target_seat] += 1

        eliminated_seat = None
        if vote_counts:
            max_votes = max(vote_counts.values())
            top = [s for s, c in vote_counts.items() if c == max_votes]
            if len(top) == 1:
                eliminated_seat = top[0]
            # Tie → no one eliminated

        await self.engine.transition_to("execution", game_state, eliminated_seat=eliminated_seat, vote_counts=dict(vote_counts))

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        if player_id not in game_state.day_votes:
            game_state.day_votes[player_id] = 0  # Abstain on timeout
            logger.info("Vote timeout: player=%s (abstain)", player_id)

            if len(game_state.day_votes) >= len(game_state.alive_players):
                await self._tally_votes(game_state)
