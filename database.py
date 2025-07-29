import asyncpg
import os
import logging

DATABASE_URL = os.getenv("DATABASE_URL")

# 🔌 Создаёт пул подключений к базе данных
async def create_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к базе: {e}")

# 👤 Добавляет или обновляет пользователя
async def upsert_user(pool, user_id, username, first_name):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (user_id)
                DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
            """, user_id, username, first_name)
    except Exception as e:
        logging.error(f"❌ upsert_user: {e}")

# 🔐 Проверяет доступ пользователя
async def check_access(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT access FROM users WHERE user_id = $1", user_id)
            return row and row["access"]
    except Exception as e:
        logging.error(f"❌ check_access: {e}")
        return False

# 📝 Сохраняет цель и план
async def update_goal_and_plan(pool, user_id, goal, plan):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET goal = $1, plan = $2 WHERE user_id = $3",
                goal, plan, user_id
            )
    except Exception as e:
        logging.error(f"❌ update_goal_and_plan: {e}")

# 📥 Получает цель и план
async def get_goal_and_plan(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal, plan FROM users WHERE user_id = $1", user_id)
            return row["goal"], row["plan"] if row else (None, None)
    except Exception as e:
        logging.error(f"❌ get_goal_and_plan: {e}")
        return None, None

# ➕ Создаёт этап прогресса
async def create_progress_stage(pool, user_id, stage, deadline):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO progress (user_id, stage, completed, deadline) VALUES ($1, $2, FALSE, $3)",
                user_id, stage, deadline
            )
    except Exception as e:
        logging.error(f"❌ create_progress_stage: {e}")

# ✅ Отмечает этап как завершённый
async def mark_progress_completed(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE progress SET completed = TRUE WHERE user_id = $1 AND stage = $2",
                user_id, stage
            )
    except Exception as e:
        logging.error(f"❌ mark_progress_completed: {e}")

# 🔄 Создаёт следующий этап
async def create_next_stage(pool, user_id, stage, deadline):
    return await create_progress_stage(pool, user_id, stage, deadline)

# 🔍 Проверяет последний незавершённый этап
async def check_last_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT stage, completed, deadline FROM progress WHERE user_id = $1 ORDER BY stage DESC LIMIT 1",
                user_id
            )
            return row
    except Exception as e:
        logging.error(f"❌ check_last_progress: {e}")
        return None

# 📊 Получает все этапы прогресса
async def get_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch(
                "SELECT stage, completed, deadline FROM progress WHERE user_id = $1 ORDER BY stage",
                user_id
            )
    except Exception as e:
        logging.error(f"❌ get_progress: {e}")
        return []

# 🔔 Получает пользователей, которым нужно отправить напоминание
async def get_users_for_reminder(pool):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT DISTINCT user_id FROM progress WHERE completed = FALSE")
    except Exception as e:
        logging.error(f"❌ get_users_for_reminder: {e}")
        return []