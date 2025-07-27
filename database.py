import asyncpg
import logging
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ Создание пула соединений
async def create_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        raise

# ✅ Добавляем или обновляем пользователя
async def upsert_user(pool, user_id, username, first_name):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
            """, user_id, username, first_name)
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")

# ✅ Проверка доступа пользователя
async def check_access(pool, user_id):
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT access FROM users WHERE id = $1", user_id)
            return result
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False

# ✅ Обновляем цель и план
async def update_goal_and_plan(pool, user_id, goal, plan):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET goal = $2, plan = $3 WHERE id = $1
            """, user_id, goal, plan)
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")

# ✅ Получаем цель и план
async def get_goal_and_plan(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal, plan FROM users WHERE id = $1", user_id)
            return row["goal"], row["plan"] if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return None, None

# ✅ Создаём этап прогресса
async def create_progress_stage(pool, user_id, stage, deadline):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, $3, FALSE, FALSE)
            """, user_id, stage, deadline)
    except Exception as e:
        logging.error(f"Ошибка create_progress_stage: {e}")

# ✅ Получаем прогресс пользователя
async def get_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT points FROM users WHERE id = $1", user_id)
            progress = await conn.fetchrow("""
                SELECT COUNT(*) FILTER (WHERE completed = TRUE) as completed,
                       COUNT(*) as total,
                       MIN(deadline) as next_deadline
                FROM progress WHERE user_id = $1
            """, user_id)
            return {
                "points": user["points"] if user else 0,
                "completed": progress["completed"] or 0,
                "total": progress["total"] or 0,
                "next_deadline": progress["next_deadline"]
            }
    except Exception as e:
        logging.error(f"Ошибка get_progress: {e}")
        return {"points": 0, "completed": 0, "total": 0, "next_deadline": None}

# ✅ Получаем всех пользователей для напоминаний
async def get_users_for_reminder(pool):
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT user_id FROM progress
                WHERE completed = FALSE AND deadline > NOW()
            """)
            return [row["user_id"] for row in rows]
    except Exception as e:
        logging.error(f"Ошибка get_users_for_reminder: {e}")
        return []