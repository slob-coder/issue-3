"""Night phase handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.engine.phases.base import PhaseHandler
from app.engine.roles.registry import RoleRegistry
from app.services.event_bus import GameEvent

if TYPE_CHECKING:
    from app.engine.game_state import GameState

logger = logging.getLogger(__name__)

# Night action processing order
NIGHT_ORDER = ["werewolf", "seer", "witch"]


class NightPhaseHandler(PhaseHandler):
    """Handle the night phase - each role acts in priority order."""

    async def enter(self, game_state: GameState) -> None:
        game_state.phase = "night"
        game_state.round_number += 1
        game_state.night_kill_target = None
        game_state.night_poison_target = None
        game_state.night_actions_received = {}
        game_state.eliminated_last_night = []
        await game_state.sync_to_redis(self.engine.redis)

        # Send night action requests to each role
        for role_id in NIGHT_ORDER:
            strategy = RoleRegistry.get(role_id)
            action_type = strategy.get_night_action_type()
            if not action_type:
                continue

            players = game_state.get_players_by_role(role_id)
            for player in players:
                targets = strategy.get_available_targets(player, game_state.alive_players)
                event_data = {
                    "round": game_state.round_number,
                    "your_role": player.role,
                    "action_type": action_type,
                    "available_targets": targets,
                    "timeout": self.engine.settings.default_action_timeout,
                    "context": {"alive_players": game_state.alive_seats},
                }
                # Witch gets extra info
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

        # If no roles have night actions, skip to result
        if not any(
            RoleRegistry.get(r).get_night_action_type()
            for r in NIGHT_ORDER
            if game_state.get_players_by_role(r)
        ):
            await self.engine.transition_to("result", game_state)

    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        player = game_state.get_player_by_id(player_id)
        if not player:
            return

        strategy = RoleRegistry.get(player.role)
        result = await strategy.execute_night_action(player, action.get("data", action), game_state)

        # Process result
        if result.type == "kill":
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

        # Mark role action as done
        game_state.night_actions_received[player.role] = True

        # Cancel timeout
        await self.engine.scheduler.cancel_timeout(
            game_state.room_id, player_id, f"night_{player.role}"
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

        # Check if all roles have acted
        await self._check_all_acted(game_state)

    async def _check_all_acted(self, game_state: GameState) -> None:
        for role_id in NIGHT_ORDER:
            if not game_state.get_players_by_role(role_id):
                continue
            strategy = RoleRegistry.get(role_id)
            if strategy.get_night_action_type() and role_id not in game_state.night_actions_received:
                return  # Still waiting

        await self.engine.transition_to("result", game_state)

    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        player = game_state.get_player_by_id(player_id)
        if player:
            game_state.night_actions_received[player.role] = True
            logger.info("Night timeout: player=%s role=%s (skip)", player_id, player.role)
            await self._check_all_acted(game_state)
