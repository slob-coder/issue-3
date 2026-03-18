"""Night phase handler - sequential role-based actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.engine.phases.base import PhaseHandler
from app.engine.roles.registry import RoleRegistry
from app.services.event_bus import GameEvent

if TYPE_CHECKING:
    from app.engine.game_state import GameState

logger = logging.getLogger(__name__)

# Night action processing order: werewolves first, then seer, then witch
NIGHT_ORDER = ["werewolf", "seer", "witch"]


class NightPhaseHandler(PhaseHandler):
    """Handle the night phase - each role acts in sequential priority order.

    Roles are prompted one at a time in NIGHT_ORDER. The next role is only
    prompted after the previous role has acted (or timed out). This ensures
    the witch can see the werewolf kill target before deciding.
    """

    async def enter(self, game_state: GameState, **kwargs) -> None:
        game_state.phase = "night"
        game_state.round_number += 1
        game_state.night_kill_target = None
        game_state.night_poison_target = None
        game_state.night_actions_received = {}
        game_state.eliminated_last_night = []
        game_state.night_pending_werewolf_votes = {}
        await game_state.sync_to_redis(self.engine.redis)

        # Notify spectators
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="phase.night",
                room_id=game_state.room_id,
                data={
                    "round": game_state.round_number,
                    "message": f"第{game_state.round_number}轮夜晚开始",
                },
            ),
        )

        # Start sequential prompting from the first role
        await self._prompt_next_role(game_state)

    async def _prompt_next_role(self, game_state: GameState) -> None:
        """Find the next role that hasn't acted yet and prompt it."""
        for role_id in NIGHT_ORDER:
            if role_id in game_state.night_actions_received:
                continue

            strategy = RoleRegistry.get(role_id)
            action_type = strategy.get_night_action_type()
            if not action_type:
                game_state.night_actions_received[role_id] = True
                continue

            alive_role_players = game_state.get_players_by_role(role_id)
            if not alive_role_players:
                game_state.night_actions_received[role_id] = True
                continue

            # Prompt all players of this role
            for player in alive_role_players:
                targets = strategy.get_available_targets(player, game_state.alive_players)
                event_data = {
                    "round": game_state.round_number,
                    "your_role": player.role,
                    "action_type": action_type,
                    "available_targets": targets,
                    "timeout": self.engine.settings.default_action_timeout,
                    "context": {"alive_players": game_state.alive_seats},
                }
                # Witch gets extra info (kill target is now resolved)
                if role_id == "witch":
                    event_data["werewolf_kill_target"] = game_state.night_kill_target
                    event_data["heal_remaining"] = game_state.witch_heal_remaining
                    event_data["poison_remaining"] = game_state.witch_poison_remaining
                    event_data["available_poison_targets"] = targets

                await self.event_bus.publish_to_agent(
                    game_state.room_id,
                    player.agent_id,
                    GameEvent(event="phase.night", room_id=game_state.room_id, data=event_data),
                )
                await self.engine.scheduler.request_action(
                    game_state.room_id,
                    player.player_id,
                    f"night_{role_id}",
                    self.engine.settings.default_action_timeout,
                )
            return  # Wait for this role to act before prompting next

        # All roles have acted — transition to result
        await self.engine.transition_to("result", game_state)

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player:
            return

        role_id = player.role
        strategy = RoleRegistry.get(role_id)
        result = await strategy.execute_night_action(player, action.get("data", action), game_state)

        # Process result
        if result.type == "kill":
            if role_id == "werewolf":
                # Werewolf consensus: record each wolf's vote, resolve on last
                game_state.night_pending_werewolf_votes[player.player_id] = result.target_seat
                all_wolves = game_state.get_players_by_role("werewolf")
                all_voted = all(
                    w.player_id in game_state.night_pending_werewolf_votes
                    for w in all_wolves
                )
                if all_voted:
                    # Majority vote to determine kill target
                    game_state.night_kill_target = self._resolve_werewolf_consensus(
                        game_state.night_pending_werewolf_votes
                    )
                    game_state.night_actions_received["werewolf"] = True
                    # Cancel all wolf timeouts
                    for w in all_wolves:
                        await self.engine.scheduler.cancel_timeout(
                            game_state.room_id, w.player_id, "night_werewolf"
                        )
                else:
                    # Still waiting for other wolves — cancel this wolf's timeout only
                    await self.engine.scheduler.cancel_timeout(
                        game_state.room_id, player_id, f"night_{role_id}"
                    )
                    return  # Don't prompt next role yet
            else:
                game_state.night_kill_target = result.target_seat
        elif result.type == "investigate":
            # Send private result to seer
            await self.event_bus.publish_to_agent(
                game_state.room_id,
                player.agent_id,
                GameEvent(
                    event="phase.night.result",
                    room_id=game_state.room_id,
                    data={"investigation_result": result.result},
                ),
            )
        elif result.type == "heal":
            game_state.witch_heal_remaining -= 1
            game_state.night_kill_target = None  # Cancel the kill
        elif result.type == "poison":
            game_state.witch_poison_remaining -= 1
            game_state.night_poison_target = result.target_seat

        # Cancel timeout
        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, f"night_{role_id}"
        )

        # Notify spectators
        await self.event_bus.publish_to_spectators(
            game_state.room_id,
            GameEvent(
                event="phase.night.action",
                room_id=game_state.room_id,
                data={
                    "role": player.role,
                    "seat": player.seat_number,
                    "action": result.type,
                    "target_seat": result.target_seat,
                    "chain_of_thought": action.get("data", {}).get("chain_of_thought"),
                },
            ),
        )

        # For non-werewolf single-player roles, mark as done
        if role_id != "werewolf":
            game_state.night_actions_received[role_id] = True

        # Prompt next role in sequence
        await self._prompt_next_role(game_state)

    def _resolve_werewolf_consensus(self, votes: dict[str, int | None]) -> int | None:
        """Resolve werewolf kill target by majority vote.

        If there's a tie, pick the target that appears first (deterministic).
        If all wolves chose None/skip, return None.
        """
        from collections import Counter
        valid_votes = [v for v in votes.values() if v is not None]
        if not valid_votes:
            return None
        counts = Counter(valid_votes)
        max_count = max(counts.values())
        # Among tied targets, pick the lowest seat for determinism
        candidates = sorted(s for s, c in counts.items() if c == max_count)
        return candidates[0]

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player:
            return

        role_id = player.role
        logger.info("Night timeout: player=%s role=%s (skip)", player_id, role_id)

        if role_id == "werewolf":
            # Treat timeout as abstain (None)
            game_state.night_pending_werewolf_votes[player_id] = None
            all_wolves = game_state.get_players_by_role("werewolf")
            all_voted = all(
                w.player_id in game_state.night_pending_werewolf_votes
                for w in all_wolves
            )
            if all_voted:
                game_state.night_kill_target = self._resolve_werewolf_consensus(
                    game_state.night_pending_werewolf_votes
                )
                game_state.night_actions_received["werewolf"] = True
                await self._prompt_next_role(game_state)
        else:
            game_state.night_actions_received[role_id] = True
            await self._prompt_next_role(game_state)
