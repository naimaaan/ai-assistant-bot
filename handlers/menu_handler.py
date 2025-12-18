from aiogram import Router, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

router = Router()

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/ask")],
        [KeyboardButton(text="/remind")],
        [KeyboardButton(text="/upload")],
        [KeyboardButton(text="/buy_premium 💎 Premium доступ")],
    ],
    resize_keyboard=True
)

@router.message(Command(commands=["start", "menu"]))
async def send_menu(message: types.Message):
    await message.answer(
        "👋 Привет! Я твой ИИ-ассистент. Вот, что я умею:\n\n"
        "🤖 `/ask` — спросить совет у GPT-5\n"
        "⏰ `/remind` — создать напоминание\n"
        "📄 `/upload` — загрузить силлабус и получить даты квизов\n\n"
        "💎 `/buy_premium` — купить премиум доступ\n\n"
        
        "Выбери команду ниже 👇",
        reply_markup=main_menu
    )
