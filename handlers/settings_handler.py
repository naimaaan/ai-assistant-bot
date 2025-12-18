from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from datetime import datetime
import re

from database.db import session, UserSettings

router = Router()

# Временное хранилище для ожидания ввода значения
pending_time_change = {}


# ==============================
# Вспомогательные функции
# ==============================
def _get_or_create_settings(user_id: int) -> UserSettings:
    """Возвращает настройки пользователя или создаёт их, если не существуют."""
    s = session.query(UserSettings).filter_by(user_id=user_id).first()
    if not s:
        s = UserSettings(
            user_id=user_id,
            tz="Asia/Almaty",
            morning_time="09:00",
            midday_time="12:00",
            evening_time="19:00",
        )
        session.add(s)
        session.commit()
    return s


def _build_settings_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру настроек."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Изменить утро 🌅", callback_data="set_morning"),
            InlineKeyboardButton(text="Изменить день 🌞", callback_data="set_midday"),
        ],
        [
            InlineKeyboardButton(text="Изменить вечер 🌙", callback_data="set_evening"),
        ],
        [
            InlineKeyboardButton(text="Сменить таймзону 🌍", callback_data="set_tz"),
        ],
    ])


# ==============================
# /settings — показать настройки
# ==============================
@router.message(Command("settings"))
async def open_settings(message: Message):
    s = _get_or_create_settings(message.from_user.id)

    text = (
        "⚙️ *Настройки*\n\n"
        f"🌅 Утреннее время: *{s.morning_time}*\n"
        f"🌞 Дневное время: *{s.midday_time}*\n"
        f"🌙 Вечернее время: *{s.evening_time}*\n"
        f"🌍 Таймзона: *{s.tz}*\n"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=_build_settings_keyboard())


# ==============================
# Callback — выбор параметра для изменения
# ==============================
@router.callback_query(F.data.in_(["set_morning", "set_midday", "set_evening", "set_tz"]))
async def change_setting(callback: CallbackQuery):
    user_id = callback.from_user.id

    if callback.data == "set_morning":
        pending_time_change[user_id] = "morning_time"
        await callback.message.answer("🌅 Введи *утреннее* время (формат HH:MM)", parse_mode="Markdown")

    elif callback.data == "set_midday":
        pending_time_change[user_id] = "midday_time"
        await callback.message.answer("🌞 Введи *дневное* время (формат HH:MM)", parse_mode="Markdown")

    elif callback.data == "set_evening":
        pending_time_change[user_id] = "evening_time"
        await callback.message.answer("🌙 Введи *вечернее* время (формат HH:MM)", parse_mode="Markdown")

    elif callback.data == "set_tz":
        pending_time_change[user_id] = "tz"
        await callback.message.answer("🌍 Введи новую таймзону, например: `Asia/Almaty`", parse_mode="Markdown")

    await callback.answer()


# ==============================
# Пользователь вводит новое значение
# ==============================
@router.message()
async def handle_new_value(message: Message):
    user_id = message.from_user.id
    if user_id not in pending_time_change:
        return  # бот не ждёт ввода

    field = pending_time_change.pop(user_id)
    value = message.text.strip()
    s = _get_or_create_settings(user_id)

    if field in ("morning_time", "midday_time", "evening_time"):
        if not re.fullmatch(r"\d{1,2}:\d{2}", value):
            await message.answer("❌ Неверный формат. Пример: 09:00")
            return

        try:
            datetime.strptime(value, "%H:%M")  # Проверка формата
            setattr(s, field, value)
            session.commit()
            label = {
                "morning_time": "Утреннее",
                "midday_time": "Дневное",
                "evening_time": "Вечернее"
            }[field]
            await message.answer(f"✅ {label} время установлено на {value}")
        except Exception as e:
            await message.answer(f"⚠ Ошибка: {e}")

    elif field == "tz":
        s.tz = value
        session.commit()
        await message.answer(f"✅ Таймзона установлена на {value}")

    # После изменения — показать обновлённые настройки
    updated = _get_or_create_settings(user_id)
    text = (
        "⚙️ *Текущие настройки*\n\n"
        f"🌅 Утреннее время: *{updated.morning_time}*\n"
        f"🌞 Дневное время: *{updated.midday_time}*\n"
        f"🌙 Вечернее время: *{updated.evening_time}*\n"
        f"🌍 Таймзона: *{updated.tz}*\n"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=_build_settings_keyboard())
