import html
import re
from io import BytesIO
from uuid import UUID

import httpx
from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.bot.client import BackendClient, BackendError
from app.config import Settings
from app.qr import QRDecodeError, create_qr_png, decode_qr_image
from app.schemas import CATEGORIES

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)

BONUS_REASONS = {
    5: "Активность на мероприятии",
    10: "Участие в задании",
    20: "Победа в конкурсе",
}


class Registration(StatesGroup):
    name = State()
    category = State()


class ManualBonus(StatesGroup):
    details = State()


def is_organizer(telegram_id: int, settings: Settings) -> bool:
    return telegram_id in settings.trusted_organizers


def card_buttons(card: dict) -> InlineKeyboardMarkup:
    guest_id = card["guest_id"]
    buttons = []
    if not card["checked_in"]:
        buttons.append(
            [InlineKeyboardButton(text="✅ Отметить приход", callback_data=f"ci:{guest_id}")]
        )
    buttons.append(
        [
            InlineKeyboardButton(text=f"+{points}", callback_data=f"b:{guest_id}:{points}")
            for points in BONUS_REASONS
        ]
    )
    buttons.append(
        [InlineKeyboardButton(text="✏️ Другая сумма и причина", callback_data=f"custom:{guest_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def card_text(card: dict) -> str:
    status = "✅ Приход отмечен" if card["checked_in"] else "⬜ Приход ещё не отмечен"
    return (
        "<b>Карточка гостя</b>\n"
        f"👤 {html.escape(card['name'])}\n"
        f"🏷 Категория: {html.escape(card['category'])}\n"
        f"⭐ Баллы: <b>{card['total_points']}</b>\n"
        f"{status}"
    )


async def send_pass(message: Message, data: dict) -> None:
    png = create_qr_png(data["qr_payload"])
    caption = (
        f"🎫 <b>Ваш персональный QR-пропуск</b>\n"
        f"{html.escape(data['name'])} · {html.escape(data['category'])}\n\n"
        "Покажите этот код организатору при входе. Не публикуйте его."
    )
    await message.answer_photo(
        BufferedInputFile(png, filename="club_pass.png"), caption=caption
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(CommandStart())
async def start(
    message: Message, state: FSMContext, backend: BackendClient, settings: Settings
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    if is_organizer(message.from_user.id, settings):
        await message.answer(
            "👋 Вы вошли как организатор.\n\n"
            "Пришлите фото QR-кода, изображение файлом или строку из QR. "
            "Я покажу карточку гостя и кнопки начисления баллов."
        )
        return
    try:
        data = await backend.get_pass(message.from_user.id)
    except BackendError as exc:
        if exc.status != 404:
            raise
        await message.answer(
            "👋 Добро пожаловать! Для получения пропуска отправьте /register."
        )
    else:
        await message.answer("Вы уже зарегистрированы. Ваш пропуск: /qr")
        await send_pass(message, data)


@router.message(Command("register"))
async def register(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None:
        return
    if is_organizer(message.from_user.id, settings):
        await message.answer("Регистрация для гостей. Вы указаны как организатор.")
        return
    await state.set_state(Registration.name)
    await message.answer("Как вас зовут? Введите имя и фамилию (2–100 символов).")


@router.message(Registration.name, F.text)
async def registration_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if name.startswith("/") or not 2 <= len(name) <= 100 or any(ord(c) < 32 for c in name):
        await message.answer("Введите корректное имя (2–100 символов). Или /cancel")
        return
    await state.update_data(name=name)
    await state.set_state(Registration.category)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x)] for x in CATEGORIES],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Выберите категорию:", reply_markup=keyboard)


@router.message(Registration.category, F.text)
async def registration_category(
    message: Message, state: FSMContext, backend: BackendClient
) -> None:
    if message.text not in CATEGORIES:
        await message.answer("Выберите категорию с клавиатуры.")
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    try:
        guest = await backend.register(message.from_user.id, data["name"], message.text)
    except BackendError as exc:
        if exc.status == 409:
            await state.clear()
            await message.answer(
                "Вы уже зарегистрированы. Используйте /qr.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        raise
    await state.clear()
    await message.answer("Регистрация завершена!", reply_markup=ReplyKeyboardRemove())
    await send_pass(message, guest)


@router.message(Command("qr"))
async def my_qr(message: Message, backend: BackendClient, settings: Settings) -> None:
    if message.from_user is None:
        return
    if is_organizer(message.from_user.id, settings):
        await message.answer("Пришлите QR гостя, чтобы открыть его карточку.")
        return
    try:
        guest = await backend.get_pass(message.from_user.id)
    except BackendError as exc:
        if exc.status == 404:
            await message.answer("Вы ещё не зарегистрированы. Отправьте /register.")
            return
        raise
    await send_pass(message, guest)


@router.message(Command("history"))
async def history(message: Message, backend: BackendClient, settings: Settings) -> None:
    if message.from_user is None:
        return
    if is_organizer(message.from_user.id, settings):
        await message.answer("История доступна гостям. Организатору доступна карточка по QR.")
        return
    try:
        events = await backend.history(message.from_user.id)
    except BackendError as exc:
        if exc.status == 404:
            await message.answer("Сначала зарегистрируйтесь: /register")
            return
        raise
    if not events:
        await message.answer("Начислений пока нет.")
        return
    lines = ["<b>Последние начисления:</b>"]
    for event in events:
        date = event["created_at"][:16].replace("T", " ")
        lines.append(f"{date} UTC · +{event['points']} — {html.escape(event['reason'])}")
    lines.append("\nПоказаны последние 20 записей.")
    await message.answer("\n".join(lines))


async def lookup_and_show(message: Message, code: str, backend: BackendClient) -> None:
    if message.from_user is None:
        return
    try:
        card = await backend.lookup(message.from_user.id, code)
    except BackendError as exc:
        if exc.status == 404:
            await message.answer("Пропуск недействителен или не найден.")
            return
        raise
    await message.answer(card_text(card), reply_markup=card_buttons(card))


async def handle_image(
    message: Message, bot: Bot, backend: BackendClient, settings: Settings
) -> None:
    if message.from_user is None or not is_organizer(message.from_user.id, settings):
        await message.answer("Сканирование доступно только организаторам.")
        return
    media = message.photo[-1] if message.photo else message.document
    if media is None:
        return
    if media.file_size is not None and media.file_size > 8 * 1024 * 1024:
        await message.answer("Файл слишком большой (максимум 8 МБ).")
        return
    buffer = BytesIO()
    await bot.download(media, destination=buffer)
    try:
        code = decode_qr_image(buffer.getvalue())
    except QRDecodeError as exc:
        await message.answer(str(exc))
        return
    await lookup_and_show(message, code, backend)


@router.message(F.photo)
async def photo(
    message: Message, bot: Bot, backend: BackendClient, settings: Settings
) -> None:
    await handle_image(message, bot, backend, settings)


@router.message(F.document)
async def document(
    message: Message, bot: Bot, backend: BackendClient, settings: Settings
) -> None:
    if not message.document or not (message.document.mime_type or "").startswith("image/"):
        await message.answer("Нужна фотография или файл изображения с QR-кодом.")
        return
    await handle_image(message, bot, backend, settings)


@router.message(ManualBonus.details, F.text)
async def manual_bonus(
    message: Message, state: FSMContext, backend: BackendClient, settings: Settings
) -> None:
    if message.from_user is None or not is_organizer(message.from_user.id, settings):
        await state.clear()
        return
    text = (message.text or "").strip()
    match = re.fullmatch(r"(\d{1,4})\s+(.+)", text, flags=re.DOTALL)
    if (
        not match
        or not 1 <= int(match.group(1)) <= 1000
        or not 3 <= len(match.group(2).strip()) <= 140
    ):
        await message.answer(
            "Формат: <code>15 Победа в викторине</code> (1–1000 баллов). Или /cancel"
        )
        return
    data = await state.get_data()
    guest_id = data.get("guest_id")
    if not guest_id:
        await state.clear()
        await message.answer("Не выбрана карточка гостя. Пришлите QR заново.")
        return
    result = await backend.bonus(
        message.from_user.id, guest_id, int(match.group(1)), match.group(2).strip()
    )
    await state.clear()
    await message.answer(
        "✅ Баллы начислены.\n" + card_text(result["card"]),
        reply_markup=card_buttons(result["card"]),
    )


@router.message(F.text)
async def text_qr(message: Message, backend: BackendClient, settings: Settings) -> None:
    if message.from_user is None:
        return
    if not is_organizer(message.from_user.id, settings):
        await message.answer("Получить QR: /qr · история баллов: /history")
        return
    if not (message.text or "").strip().startswith("bc1."):
        await message.answer("Пришлите фото QR-кода или текст, который в нём зашифрован.")
        return
    await lookup_and_show(message, message.text or "", backend)


@router.callback_query(F.data.startswith("ci:"))
async def callback_checkin(
    callback: CallbackQuery, backend: BackendClient, settings: Settings
) -> None:
    if not is_organizer(callback.from_user.id, settings):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    guest_id = (callback.data or "").removeprefix("ci:")
    try:
        UUID(guest_id)
        result = await backend.checkin(callback.from_user.id, guest_id)
    except (ValueError, BackendError):
        await callback.answer("Не удалось отметить приход", show_alert=True)
        return
    await callback.answer(
        "Приход отмечен" if result["awarded"] else "Уже отмечен ранее",
        show_alert=True,
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            card_text(result["card"]), reply_markup=card_buttons(result["card"])
        )


@router.callback_query(F.data.startswith("b:"))
async def callback_bonus(
    callback: CallbackQuery, backend: BackendClient, settings: Settings
) -> None:
    if not is_organizer(callback.from_user.id, settings):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    _, guest_id, amount = parts
    try:
        UUID(guest_id)
        points = int(amount)
        reason = BONUS_REASONS[points]
        result = await backend.bonus(callback.from_user.id, guest_id, points, reason)
    except (ValueError, KeyError, BackendError):
        await callback.answer("Не удалось начислить баллы", show_alert=True)
        return
    await callback.answer(f"Начислено +{points}", show_alert=True)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            card_text(result["card"]), reply_markup=card_buttons(result["card"])
        )


@router.callback_query(F.data.startswith("custom:"))
async def callback_custom(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not is_organizer(callback.from_user.id, settings):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    guest_id = (callback.data or "").removeprefix("custom:")
    try:
        UUID(guest_id)
    except ValueError:
        await callback.answer("Некорректная карточка", show_alert=True)
        return
    await state.set_state(ManualBonus.details)
    await state.update_data(guest_id=guest_id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "Введите количество баллов и причину одним сообщением.\n"
            "Например: <code>15 Победа в викторине</code>\n"
            "Отмена: /cancel"
        )
