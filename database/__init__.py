import asyncpg
import logging
import asyncio
from config import DATABASE_URL

async def create_pool(retries: int = 5, delay: int = 3):
    for attempt in range(1, retries + 1):
        try:
            pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
            logging.info("Подключение к базе данных успешно!")
            return pool
        except Exception as e:
            logging.error(f"Попытка {attempt} — Ошибка подключения к базе: {e}")
            if attempt < retries:
                logging.info(f"🔁 Повторная попытка через {delay} секунд(ы)...")
                await asyncio.sleep(delay)
            else:
                logging.critical("Не удалось подключиться к базе данных после всех попыток.")
                raise e
