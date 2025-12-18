# handlers/gpt_handler.py
from aiogram import Router, types, F
from aiogram.filters import Command
from services.openai_client import ask_gpt
from database.db import session, UserSettings
from services.utils import check_usage_limits, increment_usage, get_or_create_usage
import html

router = Router()

# ---------- Команда /ask ----------
@router.message(Command("ask"))
async def ask_command(message: types.Message):
    await message.answer("🧠 Напиши свой вопрос для GPT-5:")

# ---------- Обработка обычного текста (не-команды) ----------
@router.message(F.text & ~F.text.startswith("/"))
async def process_prompt(message: types.Message):
    user_id = message.from_user.id

    # 1) Проверяем Premium
    settings = session.query(UserSettings).filter_by(user_id=user_id).first()
    is_premium = settings.is_premium if settings else False

    # 2) Проверяем лимиты
    usage = get_or_create_usage(user_id)
    now_limits = check_usage_limits(user_id, is_premium)
    # Проверяем только GPT-лимит, игнорируя remind_limit
    if not now_limits["ok"] and now_limits["reason"] == "gpt_limit":
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium_open")]
        ])
        await message.answer("⚠️ Лимит GPT-запросов (5/час) исчерпан. Купите Premium 💎", reply_markup=kb)
        return

    # 3) «думаю…»
    thinking_msg = await message.answer("🤔 Думаю над ответом...")

    try:
        # 4) Вызываем GPT
        reply = await ask_gpt(message.text)

        # 5) Успешный ответ -> инкремент счётчика GPT
        increment_usage(user_id, "gpt")
        print(f"[DEBUG] increment_usage called for GPT user={user_id}")


        # 6) Безопасный вывод
        safe_text = html.escape(reply)
        safe_text = safe_text.replace("`", "'").replace("*", "").replace("_", "")

        await thinking_msg.edit_text(
            f"<b>💬 Ответ GPT-5:</b>\n\n{safe_text}",
            parse_mode="HTML"
        )

    except Exception as e:
        await thinking_msg.edit_text(
            f"⚠️ Ошибка при обращении к GPT-5:\n<code>{e}</code>",
            parse_mode="HTML"
        )
