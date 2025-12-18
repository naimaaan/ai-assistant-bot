from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DB_PATH
from datetime import datetime, timedelta

Base = declarative_base()
engine = create_engine(DB_PATH, echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# ==============================
# 📅 Таблица напоминаний
# ==============================
class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    text = Column(String)
    date = Column(DateTime)
    job_id = Column(String, nullable=True)
    repeat_type = Column(String, nullable=True)
    repeat_value = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String, default="manual")  # manual / syllabus


# ==============================
# ⚙️ Настройки пользователя
# ==============================
class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id = Column(Integer, primary_key=True)
    tz = Column(String, default="Asia/Almaty")
    morning_time = Column(String, default="09:00")
    midday_time = Column(String, default="12:00")
    evening_time = Column(String, default="19:00")
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)


# ==============================
# 📊 Лимиты пользователя
# ==============================
class UserUsage(Base):
    __tablename__ = "user_usage"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    gpt_requests = Column(Integer, default=0)
    reminders_created = Column(Integer, default=0)
    last_reset_gpt = Column(DateTime, default=datetime.utcnow)
    last_reset_reminders = Column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    stars_amount = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)
