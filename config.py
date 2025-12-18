import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
DB_PATH = "sqlite:///bot.db"
BOT_USERNAME = os.getenv("BOT_USERNAME")  # замени на свой username без @
ADMIN_CHAT_ID = 1082863162

