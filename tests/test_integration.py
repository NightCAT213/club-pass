"""Runs only with TEST_DATABASE_URL set; never uses the application database."""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.schemas import RegisterGuest
from app.service import (
    AlreadyRegistered,
    award_bonus,
    check_in,
    guest_card,
    points_history,
    register_guest,
)


@pytest.fixture
async def db_factory():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Integration tests require an isolated TEST_DATABASE_URL")
    engine = create_async_engine(url, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_single_checkin_even_when_scanned_at_once(db_factory) -> None:
    async with db_factory() as db:
        guest = await register_guest(
            db, RegisterGuest(telegram_id=1234, name="Тестовый Гость", category="Гость")
        )
        guest_id = guest.id

    async def scan(organizer_id: int) -> bool:
        async with db_factory() as session:
            return await check_in(session, guest_id, organizer_id, 10)

    results = await asyncio.gather(scan(11), scan(22), scan(33))
    assert sum(results) == 1

    async with db_factory() as db:
        card = await guest_card(db, guest_id)
        history = await points_history(db, guest_id)
        assert card.checked_in is True
        assert card.total_points == 10
        assert len(history) == 1
        assert history[0].points == 10
        assert history[0].kind == "checkin"

        await award_bonus(db, guest_id, organizer_id=11, points=5, reason="Задание")
        card = await guest_card(db, guest_id)
        history = await points_history(db, guest_id)
        assert card.total_points == 15
        assert len(history) == 2
        assert {x.reason for x in history} == {"Задание", "Посещение мероприятия"}


async def test_duplicate_registration(db_factory) -> None:
    async with db_factory() as db:
        await register_guest(db, RegisterGuest(telegram_id=1001, name="Мария", category="VIP"))
        with pytest.raises(AlreadyRegistered):
            await register_guest(db, RegisterGuest(telegram_id=1001, name="Мария", category="VIP"))
