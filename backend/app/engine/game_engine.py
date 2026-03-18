"""Game engine - main controller for a game room."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import update

from app.engine.game_state import GameState, PlayerState
from app.engine.phases.check_win import CheckWinPhaseHandler
from app.engine.phases.day_speech import DaySpeechPhaseHandler
from app.engine.phases.day_vote import DayVotePhaseHandler
from app.engine.phases.execution import ExecutionPhaseHandler
from app.engine.phases.night import NightPhaseHandler
from app.engine.phases.result import ResultPhaseHandler
from app.engine.roles.registry import RoleRegistry
from app.models.room import Room
from app.services.event_bus import GameEvent

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings
    from app.models.player import Player
    from app.services.agent_scheduler import AgentScheduler
    from app.services.event_bus import EventBus

logger = logging.getLogger(__name__)


class GameEngine:
    """Game engine - one per active room."""

    _active_engines: dict[str, "GameEngine"] = {}

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        event_bus: EventBus,
        scheduler: AgentScheduler,
        settings: Settings,
    ):
        self.db = db
        self.redis = redis
        self.event_bus = event_bus
        self.scheduler = scheduler
        self.settings = settings
        self._game_states: dict[str, GameState] = {}

        self.phase_handlers = {
            "night": NightPhaseHandler(self),
            "result": ResultPhaseHandler(self),
            "day_speech": DaySpeechPhaseHandler(self),
            "day_vote": DayVotePhaseHandler(self),
            "execution": ExecutionPhaseHandler(self),
            "check_win": CheckWinPhaseHandler(self),
        }

    @classmethod
    def get_engine(cls, room_id: str) -> Optional["GameEngine"]:
        return cls._active_engines.get(room_id)

    async def start_game(self, room_id: str, players: list[Player]) -> GameState:
        """Initialize and start a game."""
        game_state = GameState(room_id=room_id)

        for player in players:
            game_state.players[player.seat_number] = PlayerState(
                player_id=str(player.id),
                agent_id=str(player.agent_id),
                seat_number=player.seat_number,
                role=player.role,
            )

        self._game_states[room_id] = game_state
        self._active_engines[room_id] = self

        # Notify each agent of their role
        for ps in game_state.players.values():
            await self.event_bus.publish_to_agent(
                room_id,
                ps.agent_id,
                GameEvent(
                    event="game.start",
                    room_id=room_id,
                    data={
                        "room_id": room_id,
                        "your_role": ps.role,
                        "your_seat": ps.seat_number,
                        "player_count": len(game_state.players),
                        "players": [
                            {"seat": p.seat_number, "is_alive": True}
                            for p in game_state.players.values()
                        ],
                        "config": {
                            "speech_timeout": self.settings.default_speech_timeout,
                            "action_timeout": self.settings.default_action_timeout,
                            "vote_timeout": self.settings.default_vote_timeout,
                        },
                    },
                ),
            )

        # Spectators see all roles
        await self.event_bus.publish_to_spectators(
            room_id,
            GameEvent(
                event="game.start",
                room_id=room_id,
                data={
                    "room_id": room_id,
                    "player_count": len(game_state.players),
                    "players": [
                        {"seat": p.seat_number, "role": p.role, "is_alive": True}
                        for p in game_state.players.values()
                    ],
                },
            ),
        )

        # Persist game.start event
        await self.event_bus.persist_event(
            self.db,
            GameEvent(
                event="game.start",
                room_id=room_id,
                data={"player_count": len(players)},
            ),
            0,
            "start",
        )

        logger.info("Game started: room=%s players=%d", room_id, len(players))
        await self.transition_to("night", game_state)
        return game_state

    async def transition_to(self, phase: str, game_state: GameState, **kwargs) -> None:
        """Transition to a new phase."""
        game_state.phase = phase
        await game_state.sync_to_redis(self.redis)

        handler = self.phase_handlers.get(phase)
        if handler:
            await handler.enter(game_state, **kwargs)

    async def handle_action(
        self, room_id: str, player_id: str, action: dict
    ) -> None:
        """Route an agent action to the current phase handler."""
        game_state = self._game_states.get(room_id)
        if not game_state:
            return

        handler = self.phase_handlers.get(game_state.phase)
        if handler:
            await handler.handle_action(game_state, player_id, action)

    async def end_game(self, game_state: GameState, winner: str) -> None:
        """End the game and clean up."""
        room_id = game_state.room_id

        await self.db.execute(
            update(Room)
            .where(Room.id == room_id)
            .values(
                status="finished",
                winner=winner,
                finished_at=datetime.utcnow(),
            )
        )
        await self.db.commit()

        all_roles = {str(p.seat_number): p.role for p in game_state.players.values()}

        for ps in game_state.players.values():
            await self.event_bus.publish_to_agent(
                room_id,
                ps.agent_id,
                GameEvent(
                    event="game.end",
                    room_id=room_id,
                    data={
                        "winner": winner,
                        "your_role": ps.role,
                        "all_roles": all_roles,
                        "rounds_played": game_state.round_number,
                        "replay_url": f"/api/v1/rooms/{room_id}/replay",
                    },
                ),
            )

        await self.event_bus.publish_to_spectators(
            room_id,
            GameEvent(
                event="game.end",
                room_id=room_id,
                data={
                    "winner": winner,
                    "all_roles": all_roles,
                    "rounds_played": game_state.round_number,
                },
            ),
        )

        # Persist
        await self.event_bus.persist_event(
            self.db,
            GameEvent(
                event="game.end",
                room_id=room_id,
                data={"winner": winner, "rounds_played": game_state.round_number},
            ),
            game_state.round_number,
            "end",
        )

        logger.info("Game ended: room=%s winner=%s rounds=%d", room_id, winner, game_state.round_number)

        # Clean up
        self._active_engines.pop(room_id, None)
        self._game_states.pop(room_id, None)
