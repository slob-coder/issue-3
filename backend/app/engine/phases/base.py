"""Phase handler base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_engine import GameEngine
    from app.engine.game_state import GameState
    from app.services.event_bus import EventBus


class PhaseHandler(ABC):
    def __init__(self, engine: GameEngine):
        self.engine = engine
        self.event_bus: EventBus = engine.event_bus

    @abstractmethod
    async def enter(self, game_state: GameState) -> None:
        """Called when entering this phase."""
        ...

    @abstractmethod
    async def handle_action(
        self, game_state: GameState, player_id: str, action: dict
    ) -> None:
        """Handle an agent action during this phase."""
        ...

    @abstractmethod
    async def on_timeout(self, game_state: GameState, player_id: str) -> None:
        """Called when an agent times out."""
        ...
