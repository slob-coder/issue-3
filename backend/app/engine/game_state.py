"""Game state dataclass - maintained in memory, synced to Redis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from redis.asyncio import Redis


@dataclass
class PlayerState:
    player_id: str
    agent_id: str
    seat_number: int
    role: str
    is_alive: bool = True
    eliminated_at_round: Optional[int] = None
    elimination_reason: Optional[str] = None


@dataclass
class GameState:
    """In-memory game state, synced with Redis for crash recovery."""

    room_id: str
    phase: str = "waiting"
    round_number: int = 0
    players: dict[int, PlayerState] = field(default_factory=dict)  # seat -> PlayerState
    current_speaker_seat: Optional[int] = None
    speaker_order: list[int] = field(default_factory=list)
    speaker_index: int = 0
    night_kill_target: Optional[int] = None
    night_poison_target: Optional[int] = None
    night_actions_received: dict[str, bool] = field(default_factory=dict)  # role -> done
    night_pending_werewolf_votes: dict[str, int | None] = field(default_factory=dict)  # player_id -> target_seat
    witch_heal_remaining: int = 1
    witch_poison_remaining: int = 1
    day_votes: dict[str, int] = field(default_factory=dict)  # player_id -> target_seat
    speeches_this_round: list[dict] = field(default_factory=list)
    eliminated_last_night: list[dict] = field(default_factory=list)

    @property
    def alive_players(self) -> list[PlayerState]:
        return [p for p in self.players.values() if p.is_alive]

    @property
    def alive_seats(self) -> list[int]:
        return sorted([p.seat_number for p in self.alive_players])

    def get_player_by_seat(self, seat: int) -> Optional[PlayerState]:
        return self.players.get(seat)

    def get_player_by_id(self, player_id: str) -> Optional[PlayerState]:
        for p in self.players.values():
            if p.player_id == player_id:
                return p
        return None

    def get_players_by_role(self, role: str) -> list[PlayerState]:
        return [p for p in self.players.values() if p.role == role and p.is_alive]

    async def sync_to_redis(self, redis: Redis) -> None:
        """Sync critical state to Redis for crash recovery."""
        await redis.hset(
            f"room:{self.room_id}:state",
            mapping={
                "phase": self.phase,
                "round": str(self.round_number),
                "alive_seats": json.dumps(self.alive_seats),
                "current_speaker_seat": str(self.current_speaker_seat or ""),
                "night_kill_target": str(self.night_kill_target or ""),
            },
        )
