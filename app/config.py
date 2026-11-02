from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    signing_key: str
    internal_api_key: str
    organizer_ids: str
    database_url: str = ""
    api_url: str = "http://api:8000"
    checkin_points: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("signing_key", "internal_api_key")
    @classmethod
    def secure_secret(cls, value: str) -> str:
        if len(value) < 32 or "REPLACE" in value.upper():
            raise ValueError("Secrets must contain at least 32 random characters")
        return value

    @field_validator("bot_token")
    @classmethod
    def valid_bot_token(cls, value: str) -> str:
        if not value or value == "PASTE_TELEGRAM_BOT_TOKEN":
            raise ValueError("Set BOT_TOKEN from BotFather")
        return value

    @field_validator("organizer_ids")
    @classmethod
    def valid_organizers(cls, value: str) -> str:
        ids = [part.strip() for part in value.split(",")]
        if not ids or not all(x.isdecimal() and int(x) > 0 for x in ids):
            raise ValueError("ORGANIZER_IDS must be comma-separated Telegram user IDs")
        return value

    @field_validator("checkin_points")
    @classmethod
    def valid_points(cls, value: int) -> int:
        if not 1 <= value <= 1000:
            raise ValueError("CHECKIN_POINTS must be between 1 and 1000")
        return value

    @property
    def trusted_organizers(self) -> frozenset[int]:
        return frozenset(int(x.strip()) for x in self.organizer_ids.split(","))


@lru_cache
def get_settings() -> Settings:
    return Settings()
