from datetime import datetime, timedelta
from database.db import session, UserUsage

def get_or_create_usage(user_id: int):
    usage = session.query(UserUsage).filter_by(user_id=user_id).first()
    if not usage:
        usage = UserUsage(
            user_id=user_id,
            gpt_requests=0,
            reminders_created=0,
            last_reset_gpt=datetime.utcnow(),
            last_reset_reminders=datetime.utcnow(),
        )
        session.add(usage)
        session.commit()
    return usage


def check_usage_limits(user_id: int, is_premium: bool):
    """Проверка лимитов GPT и напоминаний"""
    if is_premium:
        return {"ok": True}

    usage = get_or_create_usage(user_id)
    now = datetime.utcnow()

    # 🩹 Если что-то не инициализировано — инициализируем прямо здесь
    if usage.gpt_requests is None:
        usage.gpt_requests = 0
    if usage.reminders_created is None:
        usage.reminders_created = 0
    if usage.last_reset_gpt is None:
        usage.last_reset_gpt = now
    if usage.last_reset_reminders is None:
        usage.last_reset_reminders = now

    # ⏳ Авто-сброс GPT лимита (каждый час)
    if (now - usage.last_reset_gpt) > timedelta(hours=1):
        usage.gpt_requests = 0
        usage.last_reset_gpt = now

    # ⏳ Авто-сброс лимита напоминаний (раз в сутки)
    if (now - usage.last_reset_reminders) > timedelta(days=1):
        usage.reminders_created = 0
        usage.last_reset_reminders = now

    session.commit()

    # 🚫 Проверка лимитов
    if usage.gpt_requests >= 5:
        return {"ok": False, "reason": "gpt_limit"}
    if usage.reminders_created >= 3:
        return {"ok": False, "reason": "remind_limit"}

    return {"ok": True}


def increment_usage(user_id: int, action: str):
    """Увеличивает счётчик при использовании GPT или напоминаний"""
    usage = get_or_create_usage(user_id)

    if action == "gpt":
        usage.gpt_requests = (usage.gpt_requests or 0) + 1
    elif action == "remind":
        usage.reminders_created = (usage.reminders_created or 0) + 1

    session.commit()
    print(f"[USAGE] user={user_id} {action} -> gpt={usage.gpt_requests}, remind={usage.reminders_created}")
