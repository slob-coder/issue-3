"""Room model."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    config: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    winner: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    players: Mapped[list["Player"]] = relationship(  # noqa: F821
        back_populates="room", cascade="all, delete-orphan"
    )
    events: Mapped[list["GameEvent"]] = relationship(  # noqa: F821
        back_populates="room", cascade="all, delete-orphan"
    )
