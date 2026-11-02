import hmac
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import engine, get_session
from app.schemas import (
    ActionResult,
    AwardPoints,
    GuestCard,
    OrganizerAction,
    OrganizerLookup,
    PassResponse,
    PointHistoryItem,
    RegisterGuest,
)
from app.security import make_pass
from app.service import (
    AlreadyRegistered,
    GuestNotFound,
    InvalidPass,
    award_bonus,
    check_in,
    find_guest_by_pass,
    find_guest_by_telegram,
    guest_card,
    points_history,
    register_guest,
)

settings = get_settings()
auth_scheme = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Club Pass API", version="1.0.0", lifespan=lifespan)


def internal_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
) -> None:
    if (
        credentials is None
        or not hmac.compare_digest(credentials.credentials, settings.internal_api_key)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


def ensure_organizer(organizer_id: int) -> None:
    if organizer_id not in settings.trusted_organizers:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an organizer")


def missing_guest(_: GuestNotFound) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Guest not found")


@app.get("/health")
async def health(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable") from exc
    return {"status": "ok"}


@app.post(
    "/api/v1/guests", response_model=PassResponse, dependencies=[Depends(internal_auth)],
    status_code=201,
)
async def create_guest(
    data: RegisterGuest, db: AsyncSession = Depends(get_session)
) -> PassResponse:
    try:
        guest = await register_guest(db, data)
    except (AlreadyRegistered, IntegrityError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Guest already registered") from exc
    return PassResponse(
        guest_id=guest.id,
        name=guest.name,
        category=guest.category,
        qr_payload=make_pass(guest.pass_nonce, settings.signing_key),
    )


@app.get(
    "/api/v1/guests/by-telegram/{telegram_id}",
    response_model=PassResponse,
    dependencies=[Depends(internal_auth)],
)
async def get_guest_pass(telegram_id: int, db: AsyncSession = Depends(get_session)) -> PassResponse:
    try:
        guest = await find_guest_by_telegram(db, telegram_id)
    except GuestNotFound as exc:
        raise missing_guest(exc) from exc
    return PassResponse(
        guest_id=guest.id,
        name=guest.name,
        category=guest.category,
        qr_payload=make_pass(guest.pass_nonce, settings.signing_key),
    )


@app.get(
    "/api/v1/guests/by-telegram/{telegram_id}/history",
    response_model=list[PointHistoryItem],
    dependencies=[Depends(internal_auth)],
)
async def guest_history(
    telegram_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> list[PointHistoryItem]:
    try:
        guest = await find_guest_by_telegram(db, telegram_id)
        return await points_history(db, guest.id, limit, offset)
    except GuestNotFound as exc:
        raise missing_guest(exc) from exc


@app.post(
    "/api/v1/organizer/lookup",
    response_model=GuestCard,
    dependencies=[Depends(internal_auth)],
)
async def lookup(data: OrganizerLookup, db: AsyncSession = Depends(get_session)) -> GuestCard:
    ensure_organizer(data.organizer_id)
    try:
        guest = await find_guest_by_pass(db, data.qr_payload, settings.signing_key)
    except InvalidPass as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or unknown QR pass") from exc
    return await guest_card(db, guest.id)


@app.get(
    "/api/v1/organizer/guests/{guest_id}",
    response_model=GuestCard,
    dependencies=[Depends(internal_auth)],
)
async def organizer_guest(
    guest_id: UUID,
    organizer_id: int = Query(gt=0),
    db: AsyncSession = Depends(get_session),
) -> GuestCard:
    ensure_organizer(organizer_id)
    try:
        return await guest_card(db, guest_id)
    except GuestNotFound as exc:
        raise missing_guest(exc) from exc


@app.post(
    "/api/v1/organizer/checkin",
    response_model=ActionResult,
    dependencies=[Depends(internal_auth)],
)
async def checkin(data: OrganizerAction, db: AsyncSession = Depends(get_session)) -> ActionResult:
    ensure_organizer(data.organizer_id)
    try:
        awarded = await check_in(db, data.guest_id, data.organizer_id, settings.checkin_points)
        return ActionResult(awarded=awarded, card=await guest_card(db, data.guest_id))
    except GuestNotFound as exc:
        raise missing_guest(exc) from exc


@app.post(
    "/api/v1/organizer/bonus",
    response_model=ActionResult,
    dependencies=[Depends(internal_auth)],
)
async def bonus(data: AwardPoints, db: AsyncSession = Depends(get_session)) -> ActionResult:
    ensure_organizer(data.organizer_id)
    try:
        await award_bonus(db, data.guest_id, data.organizer_id, data.points, data.reason)
        return ActionResult(awarded=True, card=await guest_card(db, data.guest_id))
    except GuestNotFound as exc:
        raise missing_guest(exc) from exc
