# handlers/payments_handler.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery
from datetime import datetime, timedelta

from database.db import session, UserSettings, Payment  # Payment уже используется в /stats
from config import BOT_USERNAME, ADMIN_CHAT_ID          # ➜ добавь ADMIN_CHAT_ID в config.py

router = Router()

# === Цены в звёздах ===
PREMIUM_PLANS = {
    "7d":      {"label": "Premium — 7 дней",      "days": 7,   "amount": 70},
    "30d":     {"label": "Premium — 30 дней",     "days": 30,  "amount": 200},
    "forever": {"label": "Premium — навсегда",    "days": None,"amount": 600},
}

@router.callback_query(F.data == "buy_premium_open")
async def open_premium_menu(callback: types.CallbackQuery):
    await buy_premium(callback.message)
    await callback.answer()

@router.message(Command("buy_premium"))
async def buy_premium(message: types.Message):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⭐ 7 дней — 70 ⭐", callback_data="premium_7d"),
                types.InlineKeyboardButton(text="💫 30 дней — 200 ⭐", callback_data="premium_30d"),
            ],
            [
                types.InlineKeyboardButton(text="💎 Навсегда — 600 ⭐", callback_data="premium_forever"),
            ]
        ]
    )
    await message.answer(
        "Выберите тариф Premium-доступа 💎\n\n"
        "Преимущества:\n"
        "• GPT-5 ответы без ограничений\n"
        "• Мгновенные напоминания\n"
        "• Приоритетная обработка запросов\n\n"
        "Выберите тариф ниже 👇",
        reply_markup=kb
    )

# === Отправка инвойса (Telegram Stars) ===
@router.callback_query(F.data.startswith("premium_"))
async def send_invoice(callback: types.CallbackQuery):
    plan_id = callback.data.replace("premium_", "")
    plan = PREMIUM_PLANS.get(plan_id)
    if not plan:
        await callback.answer("❌ Ошибка: тариф не найден.", show_alert=True)
        return

    prices = [LabeledPrice(label=plan["label"], amount=plan["amount"])]

    await callback.message.answer_invoice(
        title="AI Assistant Premium",
        description=f"{plan['label']}\n\nПосле оплаты доступ активируется автоматически.",
        provider_token="",              # ← пусто для Telegram Stars
        currency="XTR",                 # ← валюта звёзд
        prices=prices,
        payload=f"premium_{plan_id}",
    )

# === Проверка платежа ===
@router.pre_checkout_query(lambda q: True)
async def pre_checkout_query(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)

# === После успешной оплаты ===
@router.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    print("⚡ successful_payment_handler TRIGGERED!", message)
    payload = message.successful_payment.invoice_payload
    total_stars = message.successful_payment.total_amount  # целое число звёзд
    user = message.from_user
    user_id = user.id

    plan_id = payload.replace("premium_", "")
    plan = PREMIUM_PLANS.get(plan_id)
    if not plan:
        await message.answer("❌ Ошибка при активации Premium.")
        return

    # 1) Активируем премиум
    s = session.query(UserSettings).filter_by(user_id=user_id).first()
    if not s:
        s = UserSettings(user_id=user_id)

    s.is_premium = True
    if plan["days"]:
        s.premium_until = datetime.utcnow() + timedelta(days=plan["days"])
        text_user = f"🎉 Premium активирован на {plan['days']} дней!"
    else:
        s.premium_until = None
        text_user = "💎 Premium активирован навсегда!"

    session.add(s)

    # 2) Сохраняем платёж (для статистики /stats)
    try:
        pay = Payment(
            user_id=user_id,
            stars_amount=total_stars,
            payload=payload,
            created_at=datetime.utcnow()
        )
        session.add(pay)
    except Exception:
        # если у модели другие поля — просто не падаем
        pass

    session.commit()

    # 3) Уведомляем пользователя
    await message.answer(
        f"{text_user}\n\n"
        "Спасибо за поддержку проекта! 💙\n"
        f"Теперь у вас есть полный доступ к возможностям бота @{BOT_USERNAME} 🚀"
    )

    # 4) Уведомляем администратора
    try:
        # Соберём «кто оплатил»
        display_name = (
            (user.full_name or "").strip()
            or (user.username and f"@{user.username}")
            or str(user_id)
        )
        until_str = s.premium_until.strftime("%Y-%m-%d %H:%M UTC") if s.premium_until else "∞ (lifetime)"

        admin_text = (
            "💰 <b>Поступила оплата Premium</b>\n\n"
            f"👤 Пользователь: <b>{display_name}</b>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📦 Тариф: <b>{plan['label']}</b>\n"
            f"⭐ Сумма: <b>{total_stars} ⭐</b>\n"
            f"🧾 Payload: <code>{payload}</code>\n"
            f"⏳ Доступ до: <b>{until_str}</b>"
        )
        await message.bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")
    except Exception:
        # уведомление админу не критично — не ломаем поток
        pass

