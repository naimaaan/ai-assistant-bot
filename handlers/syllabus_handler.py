# handlers/syllabus_handler.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.openai_client import ask_gpt
from services.scheduler import schedule_reminder
from database.db import session, Reminder
from datetime import datetime
from zoneinfo import ZoneInfo
import fitz  # PyMuPDF
import docx
import os
import tempfile
import json, re

ALMATY_TZ = ZoneInfo("Asia/Almaty")
router = Router()

# --- Временное хранилище результатов парсинга ---
parsed_cache = {}

# ---------- /upload ----------
@router.message(Command("upload"))
async def upload_start(message: types.Message):
    await message.answer(
        "📄 Пришли мне файл (.pdf, .docx или .txt).\n\n"
        "Я найду даты квизов, дедлайнов и экзаменов и предложу добавить их как напоминания."
    )

# ---------- Обработка файла ----------
@router.message(lambda m: m.document)
async def handle_document(message: types.Message):
    file = message.document
    file_name = file.file_name.lower()

    if not file_name.endswith((".pdf", ".docx", ".txt")):
        await message.answer("⚠️ Поддерживаются только .pdf, .docx или .txt файлы.")
        return

    file_path = os.path.join(tempfile.gettempdir(), file.file_name)
    await message.bot.download(file, destination=file_path)

    # Извлекаем текст
    if file_name.endswith(".pdf"):
        text = extract_pdf(file_path)
    elif file_name.endswith(".docx"):
        text = extract_docx(file_path)
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

    os.remove(file_path)

    if not text.strip():
        await message.answer("⚠️ Не удалось извлечь текст из файла.")
        return

    await message.answer("🤖 Анализирую файл... Это займёт несколько секунд ⏳")

    # ---------- GPT-анализ ----------
    gpt_prompt = (
        "Извлеки все события (экзамены, квизы, дедлайны) из этого текста и верни JSON без пояснений:\n\n"
        "[{\"event\": \"Midterm Exam\", \"date\": \"2025-10-25T09:00\", \"note\": \"Midterm\"}]\n\n"
        "Текст:\n" + text[:7000]
    )

    try:
        reply = (await ask_gpt(gpt_prompt)).strip()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка GPT: {e}")
        return

    # ---------- Извлекаем JSON ----------
    try:
        match = re.search(r"(\[.*\])", reply, re.DOTALL)
        if not match:
            raise ValueError("JSON not found in GPT response")
        clean = match.group(1).replace("```json", "").replace("```", "").strip()
        events = json.loads(clean)
    except Exception as e:
        await message.answer(f"⚠️ Не удалось распознать даты: {e}\n\nСырой ответ GPT:\n{reply[:1000]}")
        return

    # ---------- Фильтрация прошедших событий ----------
    future_events = []
    skipped = []
    now = datetime.now(ALMATY_TZ)
    print("RAW GPT EVENTS:", events)

    for ev in events:
        try:
            raw_date = ev["date"]
            if len(raw_date) == 10:  # формат YYYY-MM-DD
                raw_date += "T09:00"
            dt = datetime.fromisoformat(raw_date).astimezone(ALMATY_TZ)

            print("🕓 CHECK:", ev["event"], dt, " < now?", dt < now)

            if dt < now:
                skipped.append(ev["event"])
            else:
                future_events.append((ev["event"], ev.get("note", ""), dt))
        except Exception as e:
            print("❌ Ошибка при парсинге события:", ev, e)
            continue



    if not future_events:
        msg = "😕 Не удалось найти будущих событий."
        if skipped:
            msg += f"\n⚠️ Пропущено {len(skipped)} (прошедшие даты):\n" + "\n".join(f"• {s}" for s in skipped)
        await message.answer(msg)
        return

    # ---------- Показываем пользователю предварительный список ----------
    summary = "📚 *Я нашёл в файле следующие события:*\n\n"
    for ev, note, dt in future_events:
        summary += f"🗓 {dt.strftime('%d.%m %H:%M')} — {ev}\n"
    summary += "\nДобавить все в напоминания?"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Добавить", callback_data=f"add_syllabus"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_syllabus")
            ]
        ]
    )

    # сохраняем события в cache по user_id
    parsed_cache[message.from_user.id] = future_events

    await message.answer(summary, parse_mode="Markdown", reply_markup=kb)


# ---------- Обработка нажатия кнопок ----------
@router.callback_query(F.data == "add_syllabus")
async def confirm_add(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    events = parsed_cache.get(user_id, [])

    if not events:
        await callback.answer("⚠️ Нет сохранённых данных.", show_alert=True)
        return

    created = 0
    for ev, note, dt in events:
        try:
            text = f"{ev}" if not note else f"{ev} — {note}"
            schedule_reminder(user_id, text, dt, source="syllabus")

            created += 1
        except Exception as e:
            print("❌ Ошибка при добавлении напоминания:", e)
            continue

    del parsed_cache[user_id]
    await callback.message.edit_text(f"✅ Добавлено {created} напоминаний из файла!", parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "cancel_syllabus")
async def cancel_add(callback: types.CallbackQuery):
    parsed_cache.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Добавление напоминаний отменено.")
    await callback.answer()

# ---------- Вспомогательные функции ----------
def extract_pdf(path):
    text = ""
    with fitz.open(path) as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text

def extract_docx(path):
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)
