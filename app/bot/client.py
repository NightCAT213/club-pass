from typing import Any
from uuid import UUID

import httpx


class BackendError(Exception):
    def __init__(self, status: int, detail: str = "") -> None:
        super().__init__(detail)
        self.status = status


class BackendClient:
    def __init__(self, url: str, api_key: str):
        self.http = httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(15),
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        response = await self.http.request(method, url, **kwargs)
        if response.is_error:
            try:
                detail = str(response.json().get("detail", ""))
            except (ValueError, AttributeError):
                detail = ""
            raise BackendError(response.status_code, detail)
        return response.json()

    async def register(self, telegram_id: int, name: str, category: str) -> dict:
        return await self.request(
            "POST", "/api/v1/guests",
            json={"telegram_id": telegram_id, "name": name, "category": category},
        )

    async def get_pass(self, telegram_id: int) -> dict:
        return await self.request("GET", f"/api/v1/guests/by-telegram/{telegram_id}")

    async def history(self, telegram_id: int) -> list[dict]:
        return await self.request("GET", f"/api/v1/guests/by-telegram/{telegram_id}/history")

    async def lookup(self, organizer_id: int, qr_payload: str) -> dict:
        return await self.request(
            "POST", "/api/v1/organizer/lookup",
            json={"organizer_id": organizer_id, "qr_payload": qr_payload},
        )

    async def card(self, organizer_id: int, guest_id: UUID | str) -> dict:
        return await self.request(
            "GET", f"/api/v1/organizer/guests/{guest_id}",
            params={"organizer_id": organizer_id},
        )

    async def checkin(self, organizer_id: int, guest_id: str) -> dict:
        return await self.request(
            "POST", "/api/v1/organizer/checkin",
            json={"organizer_id": organizer_id, "guest_id": guest_id},
        )

    async def bonus(self, organizer_id: int, guest_id: str, points: int, reason: str) -> dict:
        return await self.request(
            "POST", "/api/v1/organizer/bonus",
            json={
                "organizer_id": organizer_id,
                "guest_id": guest_id,
                "points": points,
                "reason": reason,
            },
        )
