import os
from datetime import datetime, timedelta, timezone

import streamlit as st
from sqlalchemy import func
from dotenv import load_dotenv  # NEW

load_dotenv()  # NEW
from database.db import session, UserSettings, Reminder, UserUsage, Payment


# -----------------------------
# Auth
# -----------------------------
def ensure_auth() -> bool:
    if "authed" not in st.session_state:
        st.session_state.authed = False

    required_token = (
        os.getenv("ADMIN_PANEL_TOKEN")
        or os.getenv("admin_panel_token")
        or "admin"
    )

    if st.session_state.authed:
        cols = st.columns([1, 1, 6])
        with cols[0]:
            if st.button("🔄 Обновить"):
                st.cache_data.clear()
                st.rerun()
        with cols[1]:
            if st.button("🚪 Выйти"):
                st.session_state.authed = False
                st.rerun()
        return True

    st.title("🔐 Admin Login")
    token = st.text_input("Введите токен администратора", type="password")
    if st.button("Войти"):
        if token.strip() == required_token:
            st.session_state.authed = True
            st.query_params["authed"] = "1"  # REPLACED experimental_set_query_params
            st.rerun()
        else:
            st.error("Неверный токен.")
    st.info("Подсказка: установите ADMIN_PANEL_TOKEN в .env. По умолчанию — 'admin'.")
    return False


# -----------------------------
# Data access (cached)
# -----------------------------
@st.cache_data(ttl=10)
def get_stats():
    users = session.query(UserSettings).count()
    premium = session.query(UserSettings).filter(UserSettings.is_premium == True).count()
    reminders = session.query(Reminder).count()
    total_gpt = session.query(func.coalesce(func.sum(UserUsage.gpt_requests), 0)).scalar() or 0
    total_stars = session.query(func.coalesce(func.sum(Payment.stars_amount), 0)).scalar() or 0
    return {
        "users": users,
        "premium": premium,
        "reminders": reminders,
        "total_gpt": int(total_gpt),
        "total_stars": int(total_stars),
    }

@st.cache_data(ttl=10)
def get_users_list():
    rows = session.query(UserSettings).all()
    data = []
    for r in rows:
        until = None
        if r.premium_until:
            # показываем в UTC человеко-читаемо
            dt = r.premium_until
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            until = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        data.append({
            "user_id": r.user_id,
            "is_premium": bool(r.is_premium),
            "premium_until": "∞" if (r.is_premium and r.premium_until is None) else (until or ""),
            "tz": r.tz,
            "morning_time": r.morning_time,
            "midday_time": r.midday_time,
            "evening_time": r.evening_time,
        })
    # сортировка по user_id
    data.sort(key=lambda x: x["user_id"])
    return data

@st.cache_data(ttl=10)
def get_payments_list(limit: int = 50):
    q = session.query(Payment).order_by(Payment.timestamp.desc()).limit(limit).all()
    out = []
    for p in q:
        ts = p.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out.append({
            "id": p.id,
            "user_id": p.user_id,
            "stars_amount": p.stars_amount,
            "timestamp_utc": ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "",
        })
    return out


# -----------------------------
# Mutations
# -----------------------------
def grant_premium(user_id: int, days: int | None):
    s = session.query(UserSettings).filter_by(user_id=user_id).first()
    if not s:
        s = UserSettings(user_id=user_id)
        session.add(s)

    s.is_premium = True
    if days is None:
        s.premium_until = None
    else:
        s.premium_until = datetime.utcnow() + timedelta(days=days)

    session.commit()
    st.cache_data.clear()

def revoke_premium(user_id: int):
    s = session.query(UserSettings).filter_by(user_id=user_id).first()
    if not s:
        st.warning("Пользователь не найден в настройках.")
        return
    s.is_premium = False
    s.premium_until = None
    session.commit()
    st.cache_data.clear()

def set_premium_until(user_id: int, dt_utc: datetime | None):
    s = session.query(UserSettings).filter_by(user_id=user_id).first()
    if not s:
        s = UserSettings(user_id=user_id)
        session.add(s)

    s.is_premium = True if dt_utc is not None else False
    s.premium_until = dt_utc
    session.commit()
    st.cache_data.clear()


# -----------------------------
# UI
# -----------------------------
def main():
    st.set_page_config(page_title="AI Assistant Admin", page_icon="🛠️", layout="wide")

    if not ensure_auth():
        return

    st.title("🛠️ AI Assistant — Admin Panel")

    # Stats
    st.subheader("📈 Статистика")
    s = get_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Пользователей", s["users"])
    c2.metric("Premium", s["premium"])
    c3.metric("Напоминаний", s["reminders"])
    c4.metric("GPT-запросов (сумма)", s["total_gpt"])
    c5.metric("Получено звёзд (сумма)", s["total_stars"])

    st.divider()

    # Users table
    st.subheader("👥 Пользователи")
    users = get_users_list()
    st.dataframe(users, use_container_width=True, hide_index=True)

    # Premium management
    st.subheader("💎 Управление Premium")
    with st.form("premium_form", clear_on_submit=False):
        user_ids = [u["user_id"] for u in users]
        user_id = st.selectbox("Выберите пользователя", options=user_ids, placeholder="user_id")
        action = st.radio(
            "Действие",
            options=[
                "Выдать на 7 дней",
                "Выдать на 30 дней",
                "Выдать навсегда (lifetime)",
                "Установить вручную дату окончания (UTC)",
                "Отключить Premium",
            ],
            horizontal=False,
        )

        manual_date = None
        manual_time = None
        if action == "Установить вручную дату окончания (UTC)":
            manual_date = st.date_input("Дата (UTC)")
            manual_time = st.time_input("Время (UTC)")

        submitted = st.form_submit_button("Применить")
        if submitted:
            try:
                if action == "Выдать на 7 дней":
                    grant_premium(user_id, 7)
                    st.success(f"Выдан Premium на 7 дней: {user_id}")
                elif action == "Выдать на 30 дней":
                    grant_premium(user_id, 30)
                    st.success(f"Выдан Premium на 30 дней: {user_id}")
                elif action == "Выдать навсегда (lifetime)":
                    grant_premium(user_id, None)
                    st.success(f"Выдан Premium навсегда: {user_id}")
                elif action == "Отключить Premium":
                    revoke_premium(user_id)
                    st.success(f"Отключён Premium: {user_id}")
                else:
                    if manual_date is None or manual_time is None:
                        st.error("Укажите дату и время.")
                    else:
                        dt_utc = datetime(
                            year=manual_date.year,
                            month=manual_date.month,
                            day=manual_date.day,
                            hour=manual_time.hour,
                            minute=manual_time.minute,
                            second=0,
                            tzinfo=timezone.utc
                        )
                        # сохраняем как наивный UTC в БД (совместимо с текущей моделью)
                        set_premium_until(user_id, dt_utc.replace(tzinfo=None))
                        st.success(f"Установлен Premium до {dt_utc.strftime('%Y-%m-%d %H:%M UTC')} для {user_id}")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.divider()

    # Payments
    st.subheader("💰 Последние платежи")
    pays = get_payments_list()
    if pays:
        st.dataframe(pays, use_container_width=True, hide_index=True)
    else:
        st.info("Платежей пока нет.")

    st.caption("Подключение к БД идёт напрямую через database.db.session")


if __name__ == "__main__":
    main()