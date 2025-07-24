# -*- coding: utf-8 -*-
"""
Модуль для работы с PostgreSQL через asyncpg.
Хранит функции для управления пользователями, целями, планами и прогрессом.
"""

import asyncpg
import logging

# ✅ Настройки подключения берём из ENV (Render или .env)
import os
DATABASE_URL = os.getenv("DATABASE_URL")


# -----------------------------
# ✅ 1. Подключение к базе
# -----------------------------
async def create_pool():
    """Создаёт пул соединений с PostgreSQL."""
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        logging.info("✅ Подключение к базе данных успешно!")
        return pool
    except Exception as e:
        logging.error(f"Ошибка подключения к базе: {e}")
        raise


# -----------------------------
# ✅ 2. Работа с пользователями
# -----------------------------
async def upsert_user(pool, user_id, username, first_name):
    """
    Добавляет пользователя в базу, если его нет.
    Если есть — обновляет username и first_name.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
        """, user_id, username, first_name)


async def check_access(pool, user_id):
    """Проверяет, есть ли у пользователя доступ к боту."""
    async with pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT access FROM users WHERE user_id = $1
        """, user_id)
        return result or False


# -----------------------------
# ✅ 3. Цели и планы
# -----------------------------
async def update_goal_and_plan(pool, user_id, goal, plan):
    """Сохраняет цель и план пользователя."""
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET goal = $2, plan = $3 WHERE user_id = $1
        """, user_id, goal, plan)


async def get_goal_and_plan(pool, user_id):
    """Возвращает (goal, plan) пользователя."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT goal, plan FROM users WHERE user_id = $1
        """, user_id)
        return (row["goal"], row["plan"]) if row else (None, None)


# -----------------------------
# ✅ 4. Прогресс
# -----------------------------
async def create_progress_stage(pool, user_id, stage, deadline):
    """Создаёт новый этап прогресса с дедлайном."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO progress (user_id, stage, deadline, completed, checked)
            VALUES ($1, $2, $3, FALSE, FALSE)
        """, user_id, stage, deadline)


async def check_last_progress(pool, user_id):
    """Проверяет последний этап прогресса."""
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT stage, completed, checked
            FROM progress
            WHERE user_id = $1
            ORDER BY stage DESC
            LIMIT 1
        """, user_id)


async def mark_progress_completed(pool, user_id, stage):
    """Помечает этап как выполненный."""
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE progress SET completed = TRUE, checked = TRUE
            WHERE user_id = $1 AND stage = $2
        """, user_id, stage)


async def create_next_stage(pool, user_id, stage):
    """Создаёт следующий этап после успешного завершения предыдущего."""
    import datetime
    new_deadline = datetime.datetime.now() + datetime.timedelta(days=7)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO progress (user_id, stage, deadline, completed, checked)
            VALUES ($1, $2, $3, FALSE, FALSE)
        """, user_id, stage, new_deadline)


# -----------------------------
# ✅ 5. Все пользователи (для напоминаний)
# -----------------------------
async def get_all_users(pool):
    """Возвращает список всех user_id для рассылки напоминаний."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id FROM users WHERE access = TRUE
        """)
        return rows