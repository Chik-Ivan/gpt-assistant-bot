import asyncpg
import logging
from config import DATABASE_URL

async def create_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")