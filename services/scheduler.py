# services/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from database.db import Reminder, UserSettings, session

ALMATY_TZ = ZoneInfo("Asia/Almaty")
scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()}, timezone=ALMATY_TZ)

_bot: Bot | None = None
def set_bot(bot: Bot):
    global _bot
    _bot = bot

async def _notify(user_id: int, text: str):
    if _bot is None:
        return
    try:
        await _bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ Failed to notify user {user_id}: {e}")

async def check_premium_expiry():
    """
    Раз в сутки:
    - если user.is_premium == 1 и premium_until < now -> выключаем и уведомляем
    """
    now = datetime.utcnow()
    try:
        users = session.query(UserSettings).filter(UserSettings.is_premium == 1).all()
        expired = [u for u in users if u.premium_until and u.premium_until < now]
        for u in expired:
            u.is_premium = 0
            session.commit()
            print(f"💔 Premium expired for user {u.user_id}")
            await _notify(
                u.user_id,
                "💔 <b>Ваш Premium закончился.</b>\n"
                "Активируйте снова, чтобы продолжить без ограничений: /buy_premium"
            )
    except Exception as e:
        session.rollback()
        print("❌ Premium watcher error:", e)

# ---------- UI: отправка уведомления ----------
async def _send_reminder_message(user_id: int, text: str, reminder_id: int):
    if _bot is None:
        print("⚠️ Bot not set for scheduler")
        return

    now = datetime.now(ALMATY_TZ).strftime("%H:%M")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="😴 +10м", callback_data=f"snooze_10m_{reminder_id}"),
            InlineKeyboardButton(text="😴 +1ч",  callback_data=f"snooze_1h_{reminder_id}")
        ],
        [
            InlineKeyboardButton(text="📅 Завтра", callback_data=f"snooze_tomorrow_{reminder_id}"),
            InlineKeyboardButton(text="✅ Готово",  callback_data=f"done_{reminder_id}")
        ]
    ])

    msg = f"🔔 **Напоминание**\n\n🕓 *{now}* — время пришло!\n💬 {text}"
    await _bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=kb)
    print(f"📩 Reminder sent to {user_id}: {text}")

# ---------- внутренние утилиты ----------
def _remove_job_by_reminder(reminder_id: int):
    for j in scheduler.get_jobs():
        try:
            if len(j.args) >= 3 and j.args[2] == reminder_id:
                scheduler.remove_job(j.id)
                print(f"🗑 Removed job {j.id} for reminder {reminder_id}")
        except Exception:
            pass

def _plan_job_for(rem: Reminder):
    when = rem.date
    if when.tzinfo is None:
        when = when.replace(tzinfo=ALMATY_TZ)
    job = scheduler.add_job(
        remind_user,
        trigger="date",
        run_date=when,
        args=[rem.user_id, rem.text, rem.id],  # передаём реальный id
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )
    rem.job_id = job.id
    session.commit()
    print(f"⏰ Scheduled reminder #{rem.id} at {when}")

def _compute_next_occurrence(dt: datetime, repeat_type: str, repeat_value: str | None):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ALMATY_TZ)
    if repeat_type == "daily":
        return dt + timedelta(days=1)
    if repeat_type == "weekly":
        return dt + timedelta(days=7)
    if repeat_type == "monthly":
        return dt + timedelta(days=30)
    return dt

# ---------- основной раннер задачи ----------
async def remind_user(user_id: int, text: str, reminder_id: int | None = None):
    # 1) отправили пуш с кнопками (id обязателен для колбэков)
    await _send_reminder_message(user_id, text, reminder_id)

    if not reminder_id:
        return

    # 2) НЕ удаляем одноразовые записи сразу — оставляем для кнопок snooze/done
    rem = session.query(Reminder).filter_by(id=reminder_id).first()
    if not rem:
        return

    if rem.repeat_type:
        next_dt = _compute_next_occurrence(rem.date, rem.repeat_type, rem.repeat_value)
        rem.date = next_dt
        session.commit()
        _remove_job_by_reminder(reminder_id)
        _plan_job_for(rem)
    else:
        rem.job_id = None
        session.commit()
        print(f"🔔 Reminder {reminder_id} triggered (kept for actions)")

# ---------- публичные API ----------
def schedule_reminder(
    user_id: int,
    text: str,
    when: datetime,
    repeat_type: str | None = None,
    repeat_value: str | None = None,
    *,
    source: str = "manual",  # ✅ НОВОЕ: принимаем источник
) -> int:
    """
    Планирует напоминание и сохраняет в БД.
    source: "manual" | "syllabus"
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=ALMATY_TZ)
    now = datetime.now(ALMATY_TZ)
    if when < now:
        when = now + timedelta(seconds=10)

    rem = Reminder(
        user_id=user_id,
        text=text,
        date=when,
        repeat_type=repeat_type,
        repeat_value=repeat_value,
        source=source,  # ✅ НОВОЕ: сохраняем источник
    )
    session.add(rem)
    session.commit()
    _plan_job_for(rem)
    return rem.id

def snooze_reminder(reminder_id: int, delta: timedelta | None = None, to_tomorrow_same_time: bool = False):
    rem = session.query(Reminder).filter_by(id=reminder_id).first()
    if not rem:
        print("⚠️ Snooze failed — reminder not found")
        return False

    if to_tomorrow_same_time:
        if rem.date.tzinfo is None:
            rem.date = rem.date.replace(tzinfo=ALMATY_TZ)
        new_dt = rem.date + timedelta(days=1)
    else:
        new_dt = datetime.now(ALMATY_TZ) + (delta or timedelta(minutes=10))

    rem.date = new_dt
    session.commit()

    _remove_job_by_reminder(reminder_id)
    _plan_job_for(rem)
    print(f"😴 Reminder {reminder_id} snoozed to {new_dt}")
    return True

def cancel_reminder(reminder_id: int):
    rem = session.query(Reminder).filter_by(id=reminder_id).first()
    if not rem:
        print("⚠️ Cancel failed — reminder not found")
        return False

    _remove_job_by_reminder(reminder_id)
    session.delete(rem)
    session.commit()
    print(f"✅ Reminder {reminder_id} canceled")
    return True


def _restore_jobs_from_db():
    """Полезно при рестарте — поднимем все будущие напоминания."""
    from datetime import timezone
    now = datetime.now(ALMATY_TZ)
    rems = session.query(Reminder).all()
    restored = 0
    for r in rems:
        when = r.date
        if when.tzinfo is None:
            when = when.replace(tzinfo=ALMATY_TZ)
        if when > now:
            _plan_job_for(r)
            restored += 1
    if restored:
        print(f"🔁 Restored {restored} jobs from DB.")
def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("✅ APScheduler started (Asia/Almaty).")
        # восстановим отложенные задачи
        _restore_jobs_from_db()
        # план: ежедневная проверка Premium (в 03:00 по Алматы)
        scheduler.add_job(
            check_premium_expiry,
            trigger="cron",
            hour=3, minute=0, second=0,
            id="premium_expiry_daily",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        # и сразу разово проверим при старте, чтобы сработало мгновенно:
        scheduler.add_job(
            check_premium_expiry,
            trigger="date",
            run_date=datetime.now(ALMATY_TZ) + timedelta(seconds=5),
            id="premium_expiry_boot_check",
            replace_existing=True
        )