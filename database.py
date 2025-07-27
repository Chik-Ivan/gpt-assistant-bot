import os
import asyncpg
from typing import List, Dict, Optional
from datetime import datetime

async def create_pool():
    return await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

# ✅ Сохранение пользователя
async def save_user(pool, uuid: str, username: str, first_name: str, telegram_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username, first_name, access, points, goal, plan, telegram_id)
            VALUES ($1, $2, $3, FALSE, 0, NULL, NULL, $4)
            ON CONFLICT (id) DO UPDATE SET telegram_id = $4
        """, uuid, username, first_name, telegram_id)

# ✅ Проверка доступа
async def check_access(pool, uuid: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT access FROM users WHERE id = $1", uuid)
        return row["access"] if row else False

# ✅ Цель
async def get_goal(pool, uuid: str) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT goal FROM users WHERE id = $1", uuid)
        return row["goal"] if row else None

async def save_goal(pool, uuid: str, goal: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET goal = $1 WHERE id = $2", goal, uuid)

# ✅ План
async def get_plan(pool, uuid: str) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT plan FROM users WHERE id = $1", uuid)
        return row["plan"] if row else None

async def save_plan(pool, uuid: str, plan: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = $1 WHERE id = $2", plan, uuid)

# ✅ Прогресс
async def get_progress(pool, telegram_id: int) -> Dict:
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM progress WHERE telegram_id = $1", telegram_id)
        completed = await conn.fetchval("SELECT COUNT(*) FROM progress WHERE telegram_id = $1 AND completed = TRUE", telegram_id)
        points = await conn.fetchval("SELECT points FROM users WHERE telegram_id = $1", telegram_id)
        return {"total": total, "completed": completed, "points": points}

# ✅ Напоминания
async def get_users_for_reminder(pool) -> List[Dict]:
    query = """
        SELECT u.telegram_id
        FROM users u
        JOIN progress p ON u.telegram_id = p.telegram_id
        WHERE p.completed = FALSE AND u.plan IS NOT NULL
        AND (u.last_reminder IS NULL OR u.last_reminder < NOW() - INTERVAL '1 day')
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]

async def update_last_reminder(pool, telegram_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_reminder = $1 WHERE telegram_id = $2", datetime.utcnow(), telegram_id)