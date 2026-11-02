import asyncio
import logging

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from app.bot.client import BackendClient, BackendError
from app.bot.handlers import router
from app.config import get_settings


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    backend = BackendClient(settings.api_url, settings.internal_api_key)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    @dispatcher.errors()
    async def errors_handler(event) -> bool:
        exception = event.exception
        logging.error(
            "Telegram update failed: %s", exception,
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        if event.update.message:
            if isinstance(exception, (BackendError, httpx.HTTPError)):
                await event.update.message.answer(
                    "Сервис временно недоступен. Повторите действие позже."
                )
            else:
                await event.update.message.answer("Не удалось обработать запрос.")
        if event.update.callback_query:
            try:
                await event.update.callback_query.answer(
                    "Не удалось обработать запрос. Повторите позже.", show_alert=True
                )
            except TelegramAPIError:
                pass
        return True

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(
            bot, backend=backend, settings=settings, close_bot_session=False
        )
    finally:
        await backend.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
