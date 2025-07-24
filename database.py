import asyncpg
import os
import logging

# ✅ Подключение к базе данных через пул соединений
async def create_pool():
    try:
        pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        return None


# ✅ 1. Сохраняем пользователя или обновляем данные
async def upsert_user(pool, user_id, username, first_name):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, username, first_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE SET username = $2, first_name = $3
                """,
                user_id, username, first_name
            )
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")


# ✅ 2. Проверка доступа
async def check_access(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT access FROM users WHERE user_id = $1", user_id)
            return row and row["access"]
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False


# ✅ 3. Сохраняем цель и план
async def update_goal_and_plan(pool, user_id, goal, plan):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET goal = $2, plan = $3
                WHERE user_id = $1
                """,
                user_id, goal, plan
            )
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")


# ✅ 4. Получаем цель и план
async def get_goal_and_plan(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal, plan FROM users WHERE user_id = $1", user_id)
            return row["goal"], row["plan"] if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return None, None


# ✅ 5. Создаём этап прогресса
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


# ✅ 6. Проверяем последний этап прогресса
async def check_last_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT * FROM progress
                WHERE user_id = $1
                ORDER BY stage DESC
                LIMIT 1
                """,
                user_id
            )
    except Exception as e:
        logging.error(f"Ошибка check_last_progress: {e}")
        return None


# ✅ 7. Отмечаем этап как выполненный
async def mark_progress_completed(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE progress
                SET completed = TRUE, checked = TRUE
                WHERE user_id = $1 AND stage = $2
                """,
                user_id, stage
            )
    except Exception as e:
        logging.error(f"Ошибка mark_progress_completed: {e}")


# ✅ 8. Создаём следующий этап
async def create_next_stage(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            import datetime
            deadline = datetime.datetime.now() + datetime.timedelta(days=7)
            deadline_str = deadline.strftime("%Y-%m-%d %H:%M:%S")

            await conn.execute(
                """
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, $3, FALSE, FALSE)
                """,
                user_id, stage, deadline_str
            )
    except Exception as e:
        logging.error(f"Ошибка create_next_stage: {e}")


# ✅ 9. Получаем всех пользователей (для рассылки напоминаний)
async def get_all_users(pool):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT user_id FROM users WHERE access = TRUE")
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []


# ✅ 10. Получаем пользователей для напоминаний (только с активными задачами)
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