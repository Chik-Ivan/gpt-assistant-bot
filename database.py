import asyncpg
import logging
import os

DATABASE_URL = os.getenv("DATABASE_URL")


# ✅ Подключение к базе
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
            await conn.execute(
                """
                INSERT INTO users (id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (id) DO UPDATE SET username = $2, first_name = $3
                """,
                user_id,
                username,
                first_name,
            )
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")


# ✅ Проверка доступа
async def check_access(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT access FROM users WHERE id = $1", user_id)
            return row["access"] if row else False
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False


# ✅ Обновление цели и плана
async def update_goal_and_plan(pool, user_id, goal, plan):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET goal = $2, plan = $3
                WHERE id = $1
                """,
                user_id,
                goal,
                plan,
            )
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")


# ✅ Получение цели и плана
async def get_goal_and_plan(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT goal, plan FROM users WHERE id = $1", user_id
            )
            return (row["goal"], row["plan"]) if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return None, None


# ✅ Прогресс: создание этапа
async def create_progress_stage(pool, user_id, stage, deadline):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, $3, FALSE, FALSE)
                """,
                user_id,
                stage,
                deadline,
            )
    except Exception as e:
        logging.error(f"Ошибка create_progress_stage: {e}")


# ✅ Проверка последнего прогресса
async def check_last_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM progress
                WHERE user_id = $1
                ORDER BY stage DESC
                LIMIT 1
                """,
                user_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logging.error(f"Ошибка check_last_progress: {e}")
        return None


# ✅ Отметка выполнения
async def mark_progress_completed(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE progress
                SET completed = TRUE, checked = TRUE
                WHERE user_id = $1 AND stage = $2
                """,
                user_id,
                stage,
            )
    except Exception as e:
        logging.error(f"Ошибка mark_progress_completed: {e}")


# ✅ Создаём следующий этап
async def create_next_stage(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, NOW() + INTERVAL '7 days', FALSE, FALSE)
                """,
                user_id,
                stage,
            )
    except Exception as e:
        logging.error(f"Ошибка create_next_stage: {e}")


# ✅ Получить всех пользователей (для напоминаний)
async def get_all_users(pool):
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM users WHERE access = TRUE")
            return rows
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []


# ✅ Получить пользователей, у кого незавершённые этапы
async def get_users_for_reminder(pool):
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT user_id FROM progress
                WHERE completed = FALSE AND deadline < NOW() + INTERVAL '1 day'
                """
            )
            return rows
    except Exception as e:
        logging.error(f"Ошибка get_users_for_reminder: {e}")
        return []