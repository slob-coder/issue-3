"""Player model."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("room_id", "seat_number"),
        UniqueConstraint("room_id", "agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE")
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    seat_number: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(30))
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    eliminated_at_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    elimination_reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    room: Mapped["Room"] = relationship(back_populates="players")  # noqa: F821
    agent: Mapped["Agent"] = relationship()  # noqa: F821
