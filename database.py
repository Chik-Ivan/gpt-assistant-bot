import asyncpg
import logging

# Подключение к базе данных
async def create_pool():
    try:
        return await asyncpg.create_pool(dsn="YOUR_DATABASE_URL")
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        return None

# ✅ Добавляем или обновляем пользователя
async def upsert_user(pool, user_id, username, first_name):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (id) DO UPDATE
                SET username = $2, first_name = $3
                """,
                user_id, username, first_name
            )
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")

# ✅ Проверяем доступ
async def check_access(pool, user_id):
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchrow("SELECT access FROM users WHERE id=$1", user_id)
            return result and result["access"]
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False

# ✅ Обновляем цель и план
async def update_goal_and_plan(pool, user_id, goal, plan):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET goal=$2, plan=$3 WHERE id=$1
                """,
                user_id, goal, plan
            )
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")

# ✅ Получаем цель и план
async def get_goal_and_plan(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal, plan FROM users WHERE id=$1", user_id)
            return row["goal"], row["plan"] if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return None, None

# ✅ Создаём этап прогресса
async def create_progress_stage(pool, user_id, stage, deadline):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, $3, FALSE, FALSE)
                """,
                user_id, stage, deadline
            )
    except Exception as e:
        logging.error(f"Ошибка create_progress_stage: {e}")

# ✅ Проверка последнего этапа
async def check_last_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT stage, completed, checked FROM progress
                WHERE user_id=$1
                ORDER BY stage DESC LIMIT 1
                """,
                user_id
            )
            return row
    except Exception as e:
        logging.error(f"Ошибка check_last_progress: {e}")
        return None

# ✅ Отметить выполнение этапа
async def mark_progress_completed(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE progress SET completed=TRUE WHERE user_id=$1 AND stage=$2",
                user_id, stage
            )
    except Exception as e:
        logging.error(f"Ошибка mark_progress_completed: {e}")

# ✅ Создать следующий этап
async def create_next_stage(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, NOW() + INTERVAL '7 days', FALSE, FALSE)
                """,
                user_id, stage
            )
    except Exception as e:
        logging.error(f"Ошибка create_next_stage: {e}")

# ✅ Получаем всех пользователей (для напоминаний)
async def get_all_users(pool):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT id AS user_id FROM users WHERE access = TRUE")
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []

# ✅ Пользователи для напоминаний (по прогрессу)
async def get_users_for_reminder(pool):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT user_id FROM progress
                WHERE completed = FALSE AND deadline > NOW() - INTERVAL '2 days'
                """
            )
    except Exception as e:
        logging.error(f"Ошибка get_users_for_reminder: {e}")
        return []