from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    pass_nonce: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Checkin(Base):
    __tablename__ = "checkins"

    # Primary key ensures only one check-in for each guest, even under concurrent requests.
    guest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("guests.id", ondelete="RESTRICT"), primary_key=True
    )
    organizer_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PointEvent(Base):
    __tablename__ = "point_events"
    __table_args__ = (
        CheckConstraint("points BETWEEN 1 AND 1000", name="valid_points"),
        CheckConstraint("kind IN ('checkin', 'bonus')", name="valid_kind"),
        Index("ix_point_events_guest_created", "guest_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    guest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False
    )
    organizer_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
