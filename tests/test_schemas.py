from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import AwardPoints, RegisterGuest


def test_guest_validation() -> None:
    guest = RegisterGuest(telegram_id=42, name="  Анна   Иванова ", category="VIP")
    assert guest.name == "Анна Иванова"
    with pytest.raises(ValidationError):
        RegisterGuest(telegram_id=42, name="А", category="VIP")
    with pytest.raises(ValidationError):
        RegisterGuest(telegram_id=42, name="Анна", category="Админ")


def test_bonus_limits() -> None:
    data = dict(organizer_id=1, guest_id=uuid4(), reason="Участие в конкурсе")
    assert AwardPoints(**data, points=1000).points == 1000
    with pytest.raises(ValidationError):
        AwardPoints(**data, points=1001)
    with pytest.raises(ValidationError):
        AwardPoints(**{**data, "reason": "x"}, points=5)
