import asyncpg
from supabase import create_client
from config import DATABASE_URL
from create_bot import logger

async def create_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        logger.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logger.error(f"Ошибка подключения к базе: {e}")