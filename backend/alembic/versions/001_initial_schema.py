"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2026-03-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_key", sa.String(64), unique=True, nullable=False),
        sa.Column("owner", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean, default=True),
    )

    op.create_table(
        "rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), default="waiting"),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("winner", sa.String(20), nullable=True),
    )

    op.create_table(
        "players",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),
        sa.Column("seat_number", sa.Integer, nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("is_alive", sa.Boolean, default=True),
        sa.Column("eliminated_at_round", sa.Integer, nullable=True),
        sa.Column("elimination_reason", sa.String(30), nullable=True),
        sa.UniqueConstraint("room_id", "seat_number"),
        sa.UniqueConstraint("room_id", "agent_id"),
    )

    op.create_table(
        "game_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round_number", sa.Integer, nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "actor_player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id"),
            nullable=True,
        ),
        sa.Column(
            "target_player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id"),
            nullable=True,
        ),
        sa.Column("payload", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_events_room_round", "game_events", ["room_id", "round_number", "phase"])
    op.create_index("idx_events_room_id", "game_events", ["room_id"])


def downgrade() -> None:
    op.drop_table("game_events")
    op.drop_table("players")
    op.drop_table("rooms")
    op.drop_table("agents")
