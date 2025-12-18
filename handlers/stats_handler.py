# handlers/stats_handler.py
from aiogram import Router, types
from aiogram.filters import Command
from datetime import datetime
from database.db import session, UserSettings, Reminder, UserUsage, Payment
from aiogram import F
router = Router()

ADMIN_ID = 1082863162  # замени на свой ID

print("📌 stats_handler импортирован")  # временно — проверка загрузки модуля

@router.message(Command("stats"))
async def show_stats(message: types.Message):
    print("📊 /stats получен!")  # 👈 временная проверка вызова
    try:
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ У тебя нет доступа к статистике.")
            return

        users = session.query(UserSettings).count()
        premium = session.query(UserSettings).filter(UserSettings.is_premium == True).count()
        reminders = session.query(Reminder).count()

        total_gpt = sum((u.gpt_requests or 0) for u in session.query(UserUsage).all())
        total_stars = sum((p.stars_amount or 0) for p in session.query(Payment).all())

        text = (
            "📊 <b>Статистика бота</b>\n\n"
            f"👥 Пользователей: <b>{users}</b>\n"
            f"💎 Premium: <b>{premium}</b>\n"
            f"📅 Напоминаний: <b>{reminders}</b>\n"
            f"💬 GPT-запросов: <b>{total_gpt}</b>\n"
            f"⭐ Получено звёзд: <b>{total_stars} ⭐</b>\n"
            f"🕓 Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        print("⚠️ /stats ERROR:", e)
        await message.answer(f"⚠️ Ошибка: {e}")

