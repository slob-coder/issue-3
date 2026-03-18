"""Check win phase handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.engine.phases.base import PhaseHandler

if TYPE_CHECKING:
    from app.engine.game_state import GameState


class CheckWinPhaseHandler(PhaseHandler):
    """Check if either faction has won. If not, go to next phase.

    Uses from_phase to determine what comes next:
    - from result → day_speech
    - from execution → night
    """

    async def enter(self, game_state: GameState, **kwargs) -> None:
        game_state.phase = "check_win"
        winner = self._check_winner(game_state)

        if winner:
            await self.engine.end_game(game_state, winner)
        else:
            from_phase = kwargs.get("from_phase")
            if from_phase == "execution":
                # After execution → go to next night
                game_state.speeches_this_round = []
                await self.engine.transition_to("night", game_state)
            else:
                # After result phase → go to day_speech
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
