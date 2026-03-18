"""Role registry - maps role_id to RoleStrategy."""

from __future__ import annotations

from app.engine.roles.base import RoleStrategy
from app.engine.roles.hunter import HunterStrategy
from app.engine.roles.seer import SeerStrategy
from app.engine.roles.villager import VillagerStrategy
from app.engine.roles.werewolf import WerewolfStrategy
from app.engine.roles.witch import WitchStrategy


class RoleRegistry:
    _strategies: dict[str, RoleStrategy] = {}

    @classmethod
    def get(cls, role_id: str) -> RoleStrategy:
        if role_id not in cls._strategies:
            raise ValueError(f"Unknown role: {role_id}")
        return cls._strategies[role_id]

    @classmethod
    def register(cls, strategy: RoleStrategy) -> None:
        cls._strategies[strategy.role_id] = strategy

    @classmethod
    def load_defaults(cls) -> None:
        cls.register(WerewolfStrategy())
        cls.register(SeerStrategy())
        cls.register(WitchStrategy())
        cls.register(HunterStrategy())
        cls.register(VillagerStrategy())
