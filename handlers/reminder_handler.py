# handlers/reminder_handler.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import dateparser
import re

from services.scheduler import schedule_reminder, scheduler, snooze_reminder, cancel_reminder
from services.utils import check_usage_limits, increment_usage
from database.db import Reminder, session, UserSettings

router = Router()
ALMATY_TZ = ZoneInfo("Asia/Almaty")


# ---------- Вспомогательные клавиатуры ----------
def build_reminder_kb(rem_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="😴 +10м", callback_data=f"snooze_10m_{rem_id}"),
                InlineKeyboardButton(text="😴 +1ч", callback_data=f"snooze_1h_{rem_id}"),
            ],
            [
                InlineKeyboardButton(text="📅 Завтра", callback_data=f"snooze_tomorrow_{rem_id}"),
                InlineKeyboardButton(text="✅ Готово", callback_data=f"done_{rem_id}"),
            ],
        ]
    )


def build_delete_kb(rem_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{rem_id}")]]
    )


# ---------- Настройки пользователя ----------
def get_user_prefs(user_id: int):
    s = session.query(UserSettings).filter_by(user_id=user_id).first()
    return {
        "tz": (s.tz if s and s.tz else "Asia/Almaty"),
        "morning": (s.morning_time if s and s.morning_time else "09:00"),
        "midday": (s.midday_time if s and s.midday_time else "12:00"),
        "evening": (s.evening_time if s and s.evening_time else "19:00"),
        "is_premium": bool(s and s.is_premium),
    }


# ---------- FSM ----------
class ReminderForm(StatesGroup):
    waiting_for_datetime = State()
    waiting_for_text = State()


# ---------- Парсер естественных дат ----------
def parse_natural_dt(text: str, prefs: dict | None = None) -> datetime | None:
    prefs = prefs or {"tz": "Asia/Almaty", "morning": "09:00", "midday": "12:00", "evening": "19:00"}
    tz = ZoneInfo(prefs.get("tz", "Asia/Almaty"))

    def hm_to_tuple(hm: str):
        h, m = hm.split(":")
        return int(h), int(m)

    MORNING_H, MORNING_M = hm_to_tuple(prefs.get("morning", "09:00"))
    MIDDAY_H, MIDDAY_M = hm_to_tuple(prefs.get("midday", "12:00"))
    EVENING_H, EVENING_M = hm_to_tuple(prefs.get("evening", "19:00"))

    t = text.strip().lower()
    now = datetime.now(tz)

    if re.fullmatch(r"(в\s*)?\d{1,2}([:.,]\d{2})?", t):
        t = "сегодня " + t.replace(".", ":").replace(",", ":")

    quick_map = {
        "сегодня утром": f"сегодня {MORNING_H:02d}:{MORNING_M:02d}",
        "сегодня днём": f"сегодня {MIDDAY_H:02d}:{MIDDAY_M:02d}",
        "сегодня днем": f"сегодня {MIDDAY_H:02d}:{MIDDAY_M:02d}",
        "сегодня вечером": f"сегодня {EVENING_H:02d}:{EVENING_M:02d}",
        "завтра утром": f"завтра {MORNING_H:02d}:{MORNING_M:02d}",
        "завтра днём": f"завтра {MIDDAY_H:02d}:{MIDDAY_M:02d}",
        "завтра днем": f"завтра {MIDDAY_H:02d}:{MIDDAY_M:02d}",
        "завтра вечером": f"завтра {EVENING_H:02d}:{EVENING_M:02d}",
        "послезавтра": f"через 2 дня {MORNING_H:02d}:{MORNING_M:02d}",
        "через неделю": f"через 7 дней {MORNING_H:02d}:{MORNING_M:02d}",
    }
    if t in quick_map:
        t = quick_map[t]

    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": prefs.get("tz", "Asia/Almaty"),
        "RETURN_AS_TIMEZONE_AWARE": True,
        "DATE_ORDER": "DMY",
        "RELATIVE_BASE": now,
    }

    dt = dateparser.parse(t, languages=["ru", "en"], settings=settings)
    if not dt:
        return None

    if dt.hour == 0 and not re.search(r"\d{1,2}[:.,]\d{2}", t):
        dt = dt.replace(hour=MORNING_H, minute=MORNING_M, second=0, microsecond=0)

    return dt.astimezone(tz)


# ---------- Команда /remind ----------
@router.message(Command("remind"))
async def remind_start(message: types.Message, state: FSMContext):
    print("⚡ Команда /remind получена!")

    user_id = message.from_user.id
    prefs = get_user_prefs(user_id)
    is_premium = prefs["is_premium"]

    # 🔍 Проверяем лимиты
    limit = check_usage_limits(user_id, is_premium)
    if not limit["ok"]:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium_open")]
            ]
        )
        reason = limit.get("reason")
        if reason == "remind_limit":
            await message.answer("⚠️ Лимит напоминаний (3/день) исчерпан. Купите Premium 💎", reply_markup=kb)
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="через 10 минут"), KeyboardButton(text="через 30 минут")],
            [KeyboardButton(text="через час"), KeyboardButton(text="сегодня вечером")],
            [KeyboardButton(text="завтра утром"), KeyboardButton(text="завтра в 9")],
            [KeyboardButton(text="отмена")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "🗓 Когда напомнить?\n"
        "Можно писать свободно: *через 10 минут*, *завтра в 9*, *25 октября 18:30*",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await state.set_state(ReminderForm.waiting_for_datetime)


@router.message(ReminderForm.waiting_for_datetime)
async def process_datetime(message: types.Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt == "отмена":
        await message.answer("❌ Напоминание отменено.", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    prefs = get_user_prefs(message.from_user.id)
    dt = parse_natural_dt(txt, prefs=prefs)

    if not dt:
        await message.answer(
            "❌ Не понял дату. Примеры: 'через 10 минут', 'завтра в 9', '25 октября 18:30'."
        )
        return

    await state.update_data(remind_time=dt)
    await message.answer("💬 Что напомнить?", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReminderForm.waiting_for_text)


@router.message(ReminderForm.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    remind_time: datetime = data["remind_time"]
    text = message.text.strip()

    schedule_reminder(message.from_user.id, text, remind_time)
    increment_usage(message.from_user.id, "remind")  # ✅ Увеличиваем счётчик

    now = datetime.now(ALMATY_TZ)
    delta = remind_time - now
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    mins = (total_seconds % 3600) // 60

    chunks = []
    if days > 0:
        chunks.append(f"{days}д")
    if hours > 0:
        chunks.append(f"{hours}ч")
    if mins > 0:
        chunks.append(f"{mins}м")
    if not chunks:
        chunks = ["менее минуты"]

    await message.answer(
        f"✅ Напоминание установлено на {remind_time.strftime('%d.%m %H:%M')} "
        f"(через {' '.join(chunks)}) — “{text}”"
    )
    await state.clear()


# ---------- Список напоминаний ----------
@router.message(Command("list_reminders"))
async def list_reminders(message: types.Message):
    reminders = (
        session.query(Reminder)
        .filter_by(user_id=message.from_user.id)
        .order_by(Reminder.date.asc())
        .all()
    )
    if not reminders:
        await message.answer("📭 У тебя нет активных напоминаний.")
        return

    syllabus_rems = [r for r in reminders if getattr(r, "source", "manual") == "syllabus"]
    manual_rems = [r for r in reminders if getattr(r, "source", "manual") == "manual"]

    if syllabus_rems:
        await message.answer("📚 *Из силлабуса:*", parse_mode="Markdown")
        for r in syllabus_rems:
            dt_str = r.date.strftime("%d.%m %H:%M")
            text = f"🗓 {dt_str}\n💬 {r.text}"
            await message.answer(text, reply_markup=build_delete_kb(r.id))

    if manual_rems:
        await message.answer("✏️ *Мои напоминания:*", parse_mode="Markdown")
        for r in manual_rems:
            dt_str = r.date.strftime("%d.%m %H:%M")
            text = f"🗓 {dt_str}\n💬 {r.text}"
            await message.answer(text, reply_markup=build_delete_kb(r.id))


# ---------- Удаление и Snooze ----------
@router.callback_query(F.data.startswith("del_"))
async def delete_reminder_callback(callback: types.CallbackQuery):
    try:
        rem_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Некорректный ID.", show_alert=True)
        return

    reminder = session.query(Reminder).filter_by(id=rem_id, user_id=callback.from_user.id).first()
    if not reminder:
        await callback.message.edit_text("⚠️ Напоминание уже удалено или не найдено.")
        await callback.answer()
        return

    for j in scheduler.get_jobs():
        try:
            if len(j.args) >= 3 and j.args[2] == rem_id:
                scheduler.remove_job(j.id)
        except Exception:
            pass

    session.delete(reminder)
    session.commit()

    await callback.message.edit_text(f"❌ Напоминание удалено: {reminder.text}")
    await callback.answer()


@router.callback_query(F.data.startswith("snooze_"))
async def cb_snooze(callback: types.CallbackQuery):
    print("⚡ callback received:", callback.data)

    try:
        _, kind, rem_id = callback.data.split("_")
        rem_id = int(rem_id)
    except Exception:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    if kind == "10m":
        ok = snooze_reminder(rem_id, delta=timedelta(minutes=10))
    elif kind == "1h":
        ok = snooze_reminder(rem_id, delta=timedelta(hours=1))
    elif kind == "tomorrow":
        ok = snooze_reminder(rem_id, to_tomorrow_same_time=True)
    else:
        ok = False

    if ok:
        await callback.answer("Отложено 💤")
        await callback.message.edit_reply_markup()
        await callback.message.edit_text(callback.message.text + "\n\n🕓 Отложено.")
    else:
        await callback.answer("Не получилось отложить.", show_alert=True)


@router.callback_query(F.data.startswith("done_"))
async def cb_done(callback: types.CallbackQuery):
    print("⚡ callback received:", callback.data)

    try:
        rem_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    ok = cancel_reminder(rem_id)
    if ok:
        await callback.answer("Готово ✅")
        await callback.message.edit_reply_markup()
        await callback.message.edit_text(callback.message.text + "\n\n✅ Отмечено как выполнено.")
    else:
        await callback.answer("Напоминание уже отсутствует.", show_alert=True)
