import asyncpg
import logging
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ Подключение к базе данных
async def create_pool():
    """Создаёт подключение к базе данных PostgreSQL."""
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        raise


# ✅ 1. Добавление или обновление пользователя
async def upsert_user(pool, user_id, username, first_name):
    """Добавляет пользователя или обновляет его данные (если уже есть)."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
            """,
                user_id,
                username,
                first_name,
            )
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")


# ✅ 2. Проверка доступа
async def check_access(pool, user_id):
    """Проверяет, есть ли у пользователя доступ (True/False)."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT access FROM users WHERE id = $1", user_id
            )
            return row["access"] if row else False
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False


# ✅ 3. Сохранение цели и плана
async def update_goal_and_plan(pool, user_id, goal, plan):
    """Обновляет цель и план для пользователя."""
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


# ✅ 4. Получение цели и плана
async def get_goal_and_plan(pool, user_id):
    """Возвращает цель и план пользователя."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT goal, plan FROM users WHERE id = $1", user_id
            )
            return (row["goal"], row["plan"]) if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return (None, None)


# ✅ 5. Создание прогресса (этапа)
async def create_progress_stage(pool, user_id, stage, deadline):
    """Создаёт новый этап выполнения плана."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO progress (id_user, stage, deadline, completed, checked)
                VALUES ($1, $2, $3, FALSE, FALSE)
            """,
                user_id,
                stage,
                deadline,
            )
    except Exception as e:
        logging.error(f"Ошибка create_progress_stage: {e}")


# ✅ 6. Получение последнего этапа прогресса
async def check_last_progress(pool, user_id):
    """Возвращает последний этап прогресса пользователя."""
    try:
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT stage, completed, checked
                FROM progress
                WHERE id_user = $1
                ORDER BY stage DESC
                LIMIT 1
            """,
                user_id,
            )
    except Exception as e:
        logging.error(f"Ошибка check_last_progress: {e}")
        return None


# ✅ 7. Отметить этап завершённым
async def mark_progress_completed(pool, user_id, stage):
    """Отмечает этап как завершённый."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE progress
                SET completed = TRUE, checked = TRUE
                WHERE id_user = $1 AND stage = $2
            """,
                user_id,
                stage,
            )
    except Exception as e:
        logging.error(f"Ошибка mark_progress_completed: {e}")


# ✅ 8. Создать следующий этап
async def create_next_stage(pool, user_id, stage):
    """Создаёт новый этап (stage+1) с дедлайном через 7 дней."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO progress (id_user, stage, deadline, completed, checked)
                VALUES ($1, $2, NOW() + INTERVAL '7 days', FALSE, FALSE)
            """,
                user_id,
                stage,
            )
    except Exception as e:
        logging.error(f"Ошибка create_next_stage: {e}")


# ✅ 9. Получение пользователей для напоминаний
async def get_users_for_reminder(pool):
    """Возвращает пользователей с незавершённым прогрессом (для напоминаний)."""
    try:
        async with pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id_user FROM progress
                WHERE completed = FALSE AND deadline > NOW() - INTERVAL '2 days'
            """
            )
    except Exception as e:
        logging.error(f"Ошибка get_users_for_reminder: {e}")
        return []


# ✅ 10. Получение всех пользователей
async def get_all_users(pool):
    """Возвращает всех пользователей (список id)."""
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT id FROM users WHERE access = TRUE")
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []