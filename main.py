# main.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import menu_handler, gpt_handler, reminder_handler, syllabus_handler, settings_handler, payments_handler, broadcast_handler, stats_handler
from services.scheduler import start_scheduler, set_bot


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    set_bot(bot)
    start_scheduler()

    dp.include_routers(
        broadcast_handler.router,
        stats_handler.router ,  # <— новый
        menu_handler.router,
        reminder_handler.router,
        syllabus_handler.router,
        payments_handler.router, # <— новый
        gpt_handler.router,
        settings_handler.router   # <— новы     # <— новый
    )

    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
