import asyncpg
import logging
import os

DATABASE_URL = os.getenv("DATABASE_URL")


async def create_pool():
    try:
        return await asyncpg.create_pool(DATABASE_URL)
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        raise


# ✅ Добавляем или обновляем пользователя
async def upsert_user(pool, telegram_id: int, username: str, first_name: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (telegram_id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
                """,
                telegram_id,
                username,
                first_name,
            )
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")


# ✅ Проверка доступа
async def check_access(pool, telegram_id: int) -> bool:
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT access FROM users WHERE telegram_id = $1", telegram_id
            )
            return bool(result)
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False


# ✅ Обновляем цель и план
async def update_goal_and_plan(pool, telegram_id: int, goal: str, plan: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE progress
                SET goal = $1, plan = $2
                WHERE telegram_id = $3
                """,
                goal,
                plan,
                telegram_id,
            )
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")


# ✅ Получаем цель и план
async def get_goal_and_plan(pool, telegram_id: int):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT goal, plan FROM progress WHERE telegram_id = $1", telegram_id
            )
            return (row["goal"], row["plan"]) if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return (None, None)


# ✅ Получаем прогресс
async def get_progress(pool, telegram_id: int):
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT points FROM users WHERE telegram_id = $1", telegram_id
            )
            progress = await conn.fetchrow(
                """
                SELECT COUNT(*) FILTER (WHERE completed = TRUE) as completed,
                       COUNT(*) as total,
                       MIN(deadline) as next_deadline
                FROM progress WHERE telegram_id = $1
                """,
                telegram_id,
            )
            return {
                "points": user["points"] if user else 0,
                "completed": progress["completed"] or 0,
                "total": progress["total"] or 0,
                "next_deadline": progress["next_deadline"],
            }
    except Exception as e:
        logging.error(f"Ошибка get_progress: {e}")
        return {"points": 0, "completed": 0, "total": 0, "next_deadline": None}


# ✅ Получаем всех пользователей (для напоминаний)
async def get_all_users(pool):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT telegram_id FROM users WHERE access = TRUE")
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []