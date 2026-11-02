from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Checkin, Guest, PointEvent
from app.schemas import GuestCard, PointHistoryItem, RegisterGuest
from app.security import new_nonce, read_pass


class GuestNotFound(Exception):
    pass


class InvalidPass(Exception):
    pass


class AlreadyRegistered(Exception):
    pass


async def register_guest(db: AsyncSession, data: RegisterGuest) -> Guest:
    existing = await db.scalar(select(Guest.id).where(Guest.telegram_id == data.telegram_id))
    if existing is not None:
        raise AlreadyRegistered
    guest = Guest(
        telegram_id=data.telegram_id,
        name=data.name,
        category=data.category,
        pass_nonce=new_nonce(),
    )
    # The unique index on telegram_id also prevents duplicate registration in races.
    db.add(guest)
    await db.commit()
    await db.refresh(guest)
    return guest


async def find_guest_by_telegram(db: AsyncSession, telegram_id: int) -> Guest:
    guest = await db.scalar(select(Guest).where(Guest.telegram_id == telegram_id))
    if guest is None:
        raise GuestNotFound
    return guest


async def find_guest_by_pass(db: AsyncSession, code: str, signing_key: str) -> Guest:
    nonce = read_pass(code, signing_key)
    if nonce is None:
        raise InvalidPass
    guest = await db.scalar(select(Guest).where(Guest.pass_nonce == nonce))
    if guest is None:
        raise InvalidPass
    return guest


async def guest_card(db: AsyncSession, guest_id: UUID) -> GuestCard:
    guest = await db.get(Guest, guest_id)
    if guest is None:
        raise GuestNotFound
    total = await db.scalar(
        select(func.coalesce(func.sum(PointEvent.points), 0)).where(
            PointEvent.guest_id == guest_id
        )
    )
    checkin = await db.get(Checkin, guest_id)
    return GuestCard(
        guest_id=guest.id,
        name=guest.name,
        category=guest.category,
        total_points=total or 0,
        checked_in=checkin is not None,
        checked_in_at=checkin.created_at if checkin else None,
    )


async def check_in(
    db: AsyncSession, guest_id: UUID, organizer_id: int, points: int
) -> bool:
    async with db.begin():
        if await db.get(Guest, guest_id) is None:
            raise GuestNotFound
        stmt = (
            pg_insert(Checkin)
            .values(guest_id=guest_id, organizer_telegram_id=organizer_id)
            .on_conflict_do_nothing(index_elements=[Checkin.guest_id])
            .returning(Checkin.guest_id)
        )
        # The unique guest_id prevents concurrent duplicate check-ins.
        # The check-in and the corresponding points are committed together.
        created = (await db.execute(stmt)).scalar_one_or_none() is not None
        if created:
            db.add(
                PointEvent(
                    guest_id=guest_id,
                    organizer_telegram_id=organizer_id,
                    kind="checkin",
                    points=points,
                    reason="Посещение мероприятия",
                )
            )
    return created


async def award_bonus(
    db: AsyncSession, guest_id: UUID, organizer_id: int, points: int, reason: str
) -> None:
    async with db.begin():
        if await db.get(Guest, guest_id) is None:
            raise GuestNotFound
        db.add(
            PointEvent(
                guest_id=guest_id,
                organizer_telegram_id=organizer_id,
                kind="bonus",
                points=points,
                reason=reason,
            )
        )


async def points_history(
    db: AsyncSession, guest_id: UUID, limit: int = 20, offset: int = 0
) -> list[PointHistoryItem]:
    if await db.get(Guest, guest_id) is None:
        raise GuestNotFound
    result = await db.scalars(
        select(PointEvent)
        .where(PointEvent.guest_id == guest_id)
        .order_by(PointEvent.created_at.desc(), PointEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        PointHistoryItem(
            points=x.points,
            kind=x.kind,
            reason=x.reason,
            organizer_id=x.organizer_telegram_id,
            created_at=x.created_at,
        )
        for x in result
    ]
