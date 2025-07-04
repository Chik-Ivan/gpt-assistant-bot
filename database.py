import asyncpg  # type: ignore
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Создаём подключение (один раз при старте)
import ssl
import asyncpg  # type: ignore
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


async def create_pool():
    ssl_context = ssl._create_unverified_context()
    return await asyncpg.create_pool(dsn=DATABASE_URL, ssl=ssl_context)


# Добавление или обновление пользователя
async def upsert_user(pool, telegram_id: int, username: str, first_name: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, access)
            VALUES ($1, $2, $3, false)  -- по умолчанию доступ закрыт
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = $2, first_name = $3
        """,
            telegram_id,
            username,
            first_name,
        )


async def update_goal_and_plan(pool, telegram_id: int, goal: str, plan: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET goal = $1,
                plan = $2
            WHERE telegram_id = $3
        """,
            goal,
            plan,
            telegram_id,
        )


async def get_goal_and_plan(pool, telegram_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT goal, plan FROM users WHERE telegram_id = $1
        """,
            telegram_id,
        )
        return row["goal"], row["plan"] if row else ("", "")


# Обновление цели пользователя
async def update_goal(pool, telegram_id: int, goal: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users SET goal = $1 WHERE telegram_id = $2
        """,
            goal,
            telegram_id,
        )


# Обновление плана
async def update_plan(pool, telegram_id: int, plan: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users SET plan = $1 WHERE telegram_id = $2
        """,
            plan,
            telegram_id,
        )


# Получение данных пользователя
async def get_user(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM users WHERE telegram_id = $1
        """,
            telegram_id,
        )


# Проверка доступа
async def has_access(pool, telegram_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT access FROM users WHERE telegram_id = $1
        """,
            telegram_id,
        )
        return bool(result) if result is not None else False


async def check_access(pool, telegram_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT access FROM users WHERE telegram_id = $1", telegram_id
        )
        return result and result["access"]

    # Сохранение нового этапа прогресса


async def create_progress_stage(pool, telegram_id: int, stage: int, deadline: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO progress (telegram_id, stage, deadline)
            VALUES ($1, $2, $3)
        """,
            telegram_id,
            stage,
            deadline,
        )


# Получить последний прогресс (этап)
async def check_last_progress(pool, telegram_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM progress
            WHERE telegram_id = $1
            ORDER BY stage DESC
            LIMIT 1
        """,
            telegram_id,
        )
        return row  # вернёт словарь: stage, deadline, completed и т.д.


# Отметить текущий этап как завершённый
async def mark_progress_completed(pool, telegram_id: int, stage: int):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE progress
            SET completed = true, checked = true
            WHERE telegram_id = $1 AND stage = $2
        """,
            telegram_id,
            stage,
        )


# Создать следующий этап (следующую неделю)
async def create_next_stage(pool, telegram_id: int, stage: int, days: int = 7):
    import datetime

    deadline = datetime.datetime.now() + datetime.timedelta(days=days)
    deadline_str = deadline.strftime("%Y-%m-%d %H:%M:%S")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO progress (telegram_id, stage, deadline)
            VALUES ($1, $2, $3)
        """,
            telegram_id,
            stage,
            deadline_str,
        )
