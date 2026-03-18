"""Tests for role strategies."""

import pytest

from app.engine.game_state import GameState, PlayerState
from app.engine.roles.werewolf import WerewolfStrategy
from app.engine.roles.seer import SeerStrategy
from app.engine.roles.witch import WitchStrategy
from app.engine.roles.hunter import HunterStrategy
from app.engine.roles.villager import VillagerStrategy


def _make_state() -> GameState:
    gs = GameState(room_id="test")
    for seat, role in [(1, "werewolf"), (2, "seer"), (3, "witch"), (4, "villager")]:
        gs.players[seat] = PlayerState(
            player_id=f"p{seat}", agent_id=f"a{seat}",
            seat_number=seat, role=role,
        )
    return gs


class TestWerewolf:
    def test_targets_exclude_werewolves(self):
        gs = _make_state()
        strategy = WerewolfStrategy()
        targets = strategy.get_available_targets(gs.players[1], gs.alive_players)
        assert 1 not in targets
        assert 2 in targets

    def test_night_action_type(self):
        assert WerewolfStrategy().get_night_action_type() == "kill"


class TestSeer:
    def test_targets_exclude_self(self):
        gs = _make_state()
        strategy = SeerStrategy()
        targets = strategy.get_available_targets(gs.players[2], gs.alive_players)
        assert 2 not in targets
        assert 1 in targets

    @pytest.mark.asyncio
    async def test_investigate_werewolf(self):
        gs = _make_state()
        strategy = SeerStrategy()
        result = await strategy.execute_night_action(
            gs.players[2], {"target_seat": 1}, gs
        )
        assert result.type == "investigate"
        assert result.result["faction"] == "werewolf"

    @pytest.mark.asyncio
    async def test_investigate_villager(self):
        gs = _make_state()
        strategy = SeerStrategy()
        result = await strategy.execute_night_action(
            gs.players[2], {"target_seat": 4}, gs
        )
        assert result.result["faction"] == "villager"


class TestWitch:
    @pytest.mark.asyncio
    async def test_heal(self):
        gs = _make_state()
        gs.witch_heal_remaining = 1
        strategy = WitchStrategy()
        result = await strategy.execute_night_action(
            gs.players[3], {"action_type": "heal"}, gs
        )
        assert result.type == "heal"
        assert result.cancel_kill is True

    @pytest.mark.asyncio
    async def test_poison(self):
        gs = _make_state()
        gs.witch_poison_remaining = 1
        strategy = WitchStrategy()
        result = await strategy.execute_night_action(
            gs.players[3], {"action_type": "poison", "target_seat": 1}, gs
        )
        assert result.type == "poison"
        assert result.target_seat == 1

    @pytest.mark.asyncio
    async def test_heal_no_remaining(self):
        gs = _make_state()
        gs.witch_heal_remaining = 0
        strategy = WitchStrategy()
        result = await strategy.execute_night_action(
            gs.players[3], {"action_type": "heal"}, gs
        )
        assert result.type == "skip"


class TestHunter:
    def test_no_night_action(self):
        assert HunterStrategy().get_night_action_type() is None


class TestVillager:
    def test_no_night_action(self):
        assert VillagerStrategy().get_night_action_type() is None

    def test_no_targets(self):
        gs = _make_state()
        strategy = VillagerStrategy()
        assert strategy.get_available_targets(gs.players[4], gs.alive_players) == []
