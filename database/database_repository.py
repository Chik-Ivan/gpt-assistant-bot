from database import create_pool
from database.models import User
from typing import Optional


class DatabaseRepository:
    def __init__(self, pool):
        self.pool = pool
        
    @classmethod
    async def connect(cls):
        pool = await create_pool()
        return cls(pool)
    
    async def create_user(self, user: User) -> User:
        """Добавление нового пользователя"""
        query = """
        INSERT INTO users_data (id, goal, plan, messages, access, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (telegram_id) DO NOTHING
        RETURNING telegram_id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                query,
                user.id,
                user.goal,
                user.plan,
                user.messages,
                user.access,
                user.created_at
            )
            return result is not None
        
    async def get_user(self, user_id: int) -> Optional[User]:
        """Получение пользователя по ID"""
        query = "SELECT * FROM users_data WHERE id = $1"
        
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(query, user_id)
            if record:
                return User(
                    id=record['id'],
                    goal=record['goal'],
                    plan=record['plan'],
                    messages=record['messages'],
                    access=record['access'],
                    created_at=record['created_at']
                )
            return None
        
    async def update_user(self, user: User) -> None:
        """Обновление данных пользователя"""
        query = """
        UPDATE users_data 
        SET 
            goal = $1,
            plan = $2,
            messages = $3,
            access = $4
        WHERE id = $5
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                user.goal,
                user.plan,
                user.messages,
                user.access,
                user.id
            )