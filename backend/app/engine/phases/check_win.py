"""Check win phase handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.engine.phases.base import PhaseHandler

if TYPE_CHECKING:
    from app.engine.game_state import GameState


class CheckWinPhaseHandler(PhaseHandler):
    """Check if either faction has won. If not, go to next night."""

    async def enter(self, game_state: GameState, **kwargs) -> None:
        game_state.phase = "check_win"
        winner = self._check_winner(game_state)

        if winner:
            await self.engine.end_game(game_state, winner)
        elif game_state.eliminated_last_night or any(
            not p.is_alive for p in game_state.players.values()
        ):
            # After result phase → go to day_speech
            # After execution → go to next night
            # Determine by what happened before
            prev = kwargs.get("from_phase")
            if prev == "execution" or (
                game_state.speeches_this_round  # speeches happened means we're post-vote
            ):
                game_state.speeches_this_round = []
                await self.engine.transition_to("night", game_state)
            else:
                await self.engine.transition_to("day_speech", game_state)
        else:
            # First entry from result phase → day_speech
            await self.engine.transition_to("day_speech", game_state)

    def _check_winner(self, game_state: GameState) -> Optional[str]:
        alive = game_state.alive_players
        werewolves = [p for p in alive if p.role == "werewolf"]
        villagers = [p for p in alive if p.role != "werewolf"]

        if len(werewolves) == 0:
            return "villager"
        if len(werewolves) >= len(villagers):
            return "werewolf"
        return None

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        pass

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        pass
