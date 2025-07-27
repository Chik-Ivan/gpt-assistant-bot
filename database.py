import asyncpg
from typing import List, Dict, Optional
from datetime import datetime

# Подключение к базе данных
async def create_pool():
    return await asyncpg.create_pool(dsn="YOUR_SUPABASE_CONNECTION_STRING")

# ✅ Сохранение пользователя
async def save_user(pool, user_id: str, username: str, first_name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username, first_name, access, points, last_reminder, goal, plan)
            VALUES ($1, $2, $3, FALSE, 0, NULL, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
        """, user_id, username, first_name)

# ✅ Проверка доступа
async def check_access(pool, user_id: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT access FROM users WHERE id = $1", user_id)
        return row["access"] if row else False

# ✅ Получение цели
async def get_goal(pool, user_id: str) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT goal FROM users WHERE id = $1", user_id)
        return row["goal"] if row else None

# ✅ Сохранение цели
async def save_goal(pool, user_id: str, goal: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET goal = $1 WHERE id = $2", goal, user_id)

# ✅ Получение плана
async def get_plan(pool, user_id: str) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT plan FROM users WHERE id = $1", user_id)
        return row["plan"] if row else None

# ✅ Сохранение плана
async def save_plan(pool, user_id: str, plan: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = $1 WHERE id = $2", plan, user_id)

# ✅ Получение пользователей для напоминаний
async def get_users_for_reminder(pool) -> List[Dict]:
    query = """
        SELECT DISTINCT u.id, u.username, u.first_name
        FROM users u
        JOIN progress p ON u.id = p.user_id
        WHERE p.completed = FALSE
        AND (u.last_reminder IS NULL OR u.last_reminder < NOW() - INTERVAL '1 day')
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]

# ✅ Обновление даты последнего напоминания
async def update_last_reminder(pool, user_id: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_reminder = $1 WHERE id = $2", datetime.utcnow(), user_id)

# ✅ Обновление баллов
async def update_points(pool, user_id: str, points: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET points = points + $1 WHERE id = $2", points, user_id)

# ✅ Добавление этапа в progress
async def add_progress_stage(pool, user_id: str, stage: str, deadline: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO progress (user_id, stage, deadline, completed)
            VALUES ($1, $2, $3, FALSE)
        """, user_id, stage, deadline)

# ✅ Получение активных этапов
async def get_active_stages(pool, user_id: str):
    query = """
        SELECT stage, deadline, completed
        FROM progress
        WHERE user_id = $1 AND completed = FALSE
    """
    async with pool.acquire() as conn:
        return await conn.fetch(query)