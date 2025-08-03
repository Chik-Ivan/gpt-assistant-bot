from decouple import config


BOT_TOKEN = config("BOT_TOKEN")
OPENAI_API_KEY = config("OPENAI_API_KEY")
DATABASE_URL = config("DATABASE_URL")
WEBHOOK_HOST = config("WEBHOOK_HOST")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = 10000
ADMINS = [int(admin_id) for admin_id in config("ADMINS")]
SUPABASE_URL = config("SUPABASE_URL")
SUPABASE_KEY = config("SUPABASE_KEY")
DATABASE_URL = config("DATABASE_URL")