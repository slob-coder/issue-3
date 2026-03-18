"""Game event model for replay data."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GameEvent(Base):
    __tablename__ = "game_events"
    __table_args__ = (
        Index("idx_events_room_round", "room_id", "round_number", "phase"),
        Index("idx_events_room_id", "room_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE")
    )
    round_number: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(30))
    event_type: Mapped[str] = mapped_column(String(50))
    actor_player_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )
    target_player_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    room: Mapped["Room"] = relationship(back_populates="events")  # noqa: F821
