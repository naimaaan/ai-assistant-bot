# handlers/broadcast_handler.py
import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import session, UserSettings
from config import ADMIN_CHAT_ID

router = Router()


async def send_broadcast(bot, user_id: int, content: dict):
    """Универсальная отправка контента (текст, фото, видео и т.д.)"""
    try:
        if content["type"] == "text":
            await bot.send_message(user_id, content["text"], parse_mode="HTML")
        elif content["type"] == "photo":
            await bot.send_photo(user_id, content["file_id"], caption=content.get("caption"), parse_mode="HTML")
        elif content["type"] == "video":
            await bot.send_video(user_id, content["file_id"], caption=content.get("caption"), parse_mode="HTML")
        elif content["type"] == "document":
            await bot.send_document(user_id, content["file_id"], caption=content.get("caption"), parse_mode="HTML")
        elif content["type"] == "animation":
            await bot.send_animation(user_id, content["file_id"], caption=content.get("caption"), parse_mode="HTML")
        elif content["type"] == "voice":
            await bot.send_voice(user_id, content["file_id"], caption=content.get("caption"), parse_mode="HTML")
        else:
            await bot.send_message(user_id, content.get("caption", "📢 Новое сообщение!"))
        return True
    except Exception:
        return False


@router.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    """Рассылка обычного текста (без вложений)"""
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("📝 Укажи текст для рассылки.\n\nПример:\n<code>/broadcast Всем привет!</code>", parse_mode="HTML")
        return

    users = session.query(UserSettings.user_id).all()
    total = len(users)
    sent = 0
    failed = 0

    await message.answer(f"🚀 Начинаю рассылку {total} пользователям...")

    content = {"type": "text", "text": text}

    for (user_id,) in users:
        if await send_broadcast(message.bot, user_id, content):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # антиперегрузка Telegram API

    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Успешно: {sent}\n"
        f"❌ Ошибок: {failed}\n"
        f"👥 Всего пользователей: {total}"
    )


@router.message(Command("broadcast_media"))
async def broadcast_media_cmd(message: types.Message):
    """Начало процесса рассылки с вложением"""
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    await message.answer(
        "📎 Отправь мне медиа (фото / видео / документ / гиф / голос) и добавь подпись — я разошлю всем пользователям.\n\n"
        "Пример: прикрепи фото и напиши внизу подпись ✍️"
    )


@router.message(F.content_type.in_({"photo", "video", "document", "animation", "voice"}))
async def handle_media_broadcast(message: types.Message):
    """Фактическая рассылка медиа (если отправил админ)"""
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    # определяем тип
    ctype = message.content_type
    caption = message.caption or "📢 Новое объявление!"

    if ctype == "photo":
        file_id = message.photo[-1].file_id
    elif ctype == "video":
        file_id = message.video.file_id
    elif ctype == "document":
        file_id = message.document.file_id
    elif ctype == "animation":
        file_id = message.animation.file_id
    elif ctype == "voice":
        file_id = message.voice.file_id
    else:
        await message.answer("⚠️ Неподдерживаемый тип медиа.")
        return

    users = session.query(UserSettings.user_id).all()
    total = len(users)
    sent = 0
    failed = 0

    await message.answer(f"🚀 Начинаю медиа-рассылку ({ctype}) {total} пользователям...")

    content = {"type": ctype, "file_id": file_id, "caption": caption}

    for (user_id,) in users:
        if await send_broadcast(message.bot, user_id, content):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.07)  # чуть дольше — медиа тяжелее

    await message.answer(
        f"✅ Медиа-рассылка завершена!\n\n"
        f"📤 Успешно: {sent}\n"
        f"❌ Ошибок: {failed}\n"
        f"👥 Всего пользователей: {total}"
    )
