import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")

# Финальный URL, по которому Telegram будет отправлять запросы
WEBHOOK_URL = f"https://{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"