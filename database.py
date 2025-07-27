import asyncpg
import logging

# ✅ Создаём подключение к базе
async def create_pool():
    try:
        pool = await asyncpg.create_pool(dsn="YOUR_DATABASE_URL", ssl="require")
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        raise

# ✅ Добавляем пользователя или обновляем его данные
async def upsert_user(pool, telegram_id: int, username: str, first_name: str):
    """
    Добавляет пользователя по telegram_id или обновляет данные (если уже есть).
    access по умолчанию = FALSE.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (telegram_id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (telegram_id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
            """, telegram_id, username, first_name)
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")

# ✅ Проверяем доступ
async def check_access(pool, telegram_id: int):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT access FROM users WHERE telegram_id = $1", telegram_id)
            return row["access"] if row else False
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False

# ✅ Обновляем цель и план
async def update_goal_and_plan(pool, telegram_id: int, goal: str, plan: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET goal = $2, plan = $3 WHERE telegram_id = $1
            """, telegram_id, goal, plan)
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")

# ✅ Получаем цель и план
async def get_goal_and_plan(pool, telegram_id: int):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal, plan FROM users WHERE telegram_id = $1", telegram_id)
            return (row["goal"], row["plan"]) if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return None, None

# ✅ Создаём этап прогресса
async def create_progress_stage(pool, telegram_id: int, stage: int, deadline: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO progress (telegram_id, stage, completed, checked, deadline)
                VALUES ($1, $2, FALSE, FALSE, $3)
            """, telegram_id, stage, deadline)
    except Exception as e:
        logging.error(f"Ошибка create_progress_stage: {e}")

# ✅ Проверяем последний прогресс
async def check_last_progress(pool, telegram_id: int):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM progress
                WHERE telegram_id = $1
                ORDER BY stage DESC LIMIT 1
            """, telegram_id)
            return row
    except Exception as e:
        logging.error(f"Ошибка check_last_progress: {e}")
        return None

# ✅ Отмечаем прогресс как выполненный
async def mark_progress_completed(pool, telegram_id: int, stage: int):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE progress SET completed = TRUE, checked = TRUE
                WHERE telegram_id = $1 AND stage = $2
            """, telegram_id, stage)

            # ✅ Начисляем балл
            await conn.execute("""
                UPDATE users SET points = COALESCE(points, 0) + 1 WHERE telegram_id = $1
            """, telegram_id)
    except Exception as e:
        logging.error(f"Ошибка mark_progress_completed: {e}")

# ✅ Создаём следующий этап
async def create_next_stage(pool, telegram_id: int, stage: int):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO progress (telegram_id, stage, completed, checked, deadline)
                VALUES ($1, $2, FALSE, FALSE, NOW() + INTERVAL '7 days')
            """, telegram_id, stage)
    except Exception as e:
        logging.error(f"Ошибка create_next_stage: {e}")

# ✅ Получаем всех пользователей для рассылки
async def get_all_users(pool):
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT telegram_id FROM users WHERE access = TRUE")
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []

# ✅ Получаем прогресс пользователя
async def get_progress(pool, telegram_id: int):
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT points FROM users WHERE telegram_id = $1", telegram_id)
            progress = await conn.fetchrow("""
                SELECT COUNT(*) FILTER (WHERE completed = TRUE) as completed,
                       COUNT(*) as total,
                       MIN(deadline) as next_deadline
                FROM progress WHERE telegram_id = $1
            """, telegram_id)
            return {
                "points": user["points"] if user else 0,
                "completed": progress["completed"] or 0,
                "total": progress["total"] or 0,
                "next_deadline": progress["next_deadline"]
            }
    except Exception as e:
        logging.error(f"Ошибка get_progress: {e}")
        return {"points": 0, "completed": 0, "total": 0, "next_deadline": None}