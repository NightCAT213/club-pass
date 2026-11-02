"""Create guests, unique check-ins and full points history.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("pass_nonce", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_table(
        "checkins",
        sa.Column(
            "guest_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guests.id", ondelete="RESTRICT"), primary_key=True,
        ),
        sa.Column("organizer_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_table(
        "point_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "guest_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("organizer_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint("points BETWEEN 1 AND 1000", name="valid_points"),
        sa.CheckConstraint("kind IN ('checkin', 'bonus')", name="valid_kind"),
    )
    op.create_index("ix_point_events_guest_created", "point_events", ["guest_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_point_events_guest_created", table_name="point_events")
    op.drop_table("point_events")
    op.drop_table("checkins")
    op.drop_table("guests")
