from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

CATEGORIES = ("Гость", "VIP", "Спикер")


class RegisterGuest(BaseModel):
    telegram_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=100)
    category: str

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid guest name")
        return value

    @field_validator("category")
    @classmethod
    def allowed_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("Unknown guest category")
        return value


class PassResponse(BaseModel):
    guest_id: UUID
    name: str
    category: str
    qr_payload: str


class GuestCard(BaseModel):
    guest_id: UUID
    name: str
    category: str
    total_points: int
    checked_in: bool
    checked_in_at: datetime | None


class OrganizerLookup(BaseModel):
    organizer_id: int
    qr_payload: str = Field(min_length=1, max_length=256)


class OrganizerAction(BaseModel):
    organizer_id: int
    guest_id: UUID


class AwardPoints(OrganizerAction):
    points: int = Field(ge=1, le=1000)
    reason: str = Field(min_length=3, max_length=140)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("Reason must be at least 3 characters")
        return value


class ActionResult(BaseModel):
    awarded: bool
    card: GuestCard


class PointHistoryItem(BaseModel):
    points: int
    kind: str
    reason: str
    organizer_id: int
    created_at: datetime
