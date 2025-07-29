import asyncpg
import os
import logging

DATABASE_URL = os.getenv("DATABASE_URL")

async def create_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")

# ✅ Пользователь
async def upsert_user(pool, user_id, username, first_name):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, first_name, access)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
            """, user_id, username, first_name)
    except Exception as e:
        logging.error(f"Ошибка upsert_user: {e}")

async def check_access(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT access FROM users WHERE user_id=$1", user_id)
            return row and row["access"]
    except Exception as e:
        logging.error(f"Ошибка check_access: {e}")
        return False

async def update_goal_and_plan(pool, user_id, goal, plan):
    try:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET goal=$1, plan=$2 WHERE user_id=$3", goal, plan, user_id)
    except Exception as e:
        logging.error(f"Ошибка update_goal_and_plan: {e}")

async def get_goal_and_plan(pool, user_id):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal, plan FROM users WHERE user_id=$1", user_id)
            return row["goal"], row["plan"] if row else (None, None)
    except Exception as e:
        logging.error(f"Ошибка get_goal_and_plan: {e}")
        return None, None

# ✅ Прогресс и баллы
async def create_progress_stage(pool, user_id, stage, deadline):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, $3, FALSE, FALSE)
            """, user_id, stage, deadline)
    except Exception as e:
        logging.error(f"Ошибка create_progress_stage: {e}")

async def check_last_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM progress WHERE user_id=$1 ORDER BY stage DESC LIMIT 1", user_id)
    except Exception as e:
        logging.error(f"Ошибка check_last_progress: {e}")

async def mark_progress_completed(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE progress SET completed=TRUE, checked=TRUE WHERE user_id=$1 AND stage=$2", user_id, stage)
            await conn.execute("UPDATE users SET points = COALESCE(points, 0) + 1 WHERE user_id=$1", user_id)
    except Exception as e:
        logging.error(f"Ошибка mark_progress_completed: {e}")

async def create_next_stage(pool, user_id, stage):
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO progress (user_id, stage, deadline, completed, checked)
                VALUES ($1, $2, NOW() + interval '7 days', FALSE, FALSE)
            """, user_id, stage)
    except Exception as e:
        logging.error(f"Ошибка create_next_stage: {e}")

async def get_progress(pool, user_id):
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT points FROM users WHERE user_id=$1", user_id)
            progress = await conn.fetchrow("""
                SELECT COUNT(*) FILTER (WHERE completed=TRUE) as completed,
                       COUNT(*) as total,
                       MIN(deadline) as next_deadline
                FROM progress WHERE user_id=$1
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

# ✅ Напоминания
async def get_users_for_reminder(pool):
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT user_id FROM progress
                WHERE completed=FALSE AND deadline > NOW()
            """)
            return rows
    except Exception as e:
        logging.error(f"Ошибка get_users_for_reminder: {e}")
        return [] 