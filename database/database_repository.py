import json
import logging
from database import create_pool
from database.models import User, UserTask
from typing import Optional
from asyncpg import Pool
from typing import List


class DatabaseRepository:
    def __init__(self, pool: Pool):
        self.pool = pool
        
    @classmethod
    async def connect(cls):
        pool = await create_pool()
        return cls(pool)
    
    async def create_user(self, user: User) -> bool:
        """Добавление нового пользователя"""
        query = """
        INSERT INTO users_data (id, goal, stages_plan, substages_plan, messages, access, created_at, question_dialog, is_admin, last_access)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (id) DO NOTHING
        RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                query,
                user.id,
                user.goal,
                json.dumps(user.stages_plan) if user.stages_plan else None,
                json.dumps(user.substages_plan) if user.substages_plan else None,
                json.dumps(user.messages) if user.messages else None,
                user.access,
                user.created_at,
                json.dumps(user.question_dialog) if user.question_dialog else None,
                user.is_admin,
                user.last_access
            )
            return result is not None
        
    async def create_user_task(self, user_task: UserTask) -> bool:
        "Добавление новой задачи для пользователя"
        query = """
        INSERT INTO users_tasks (id, current_step, current_deadline, deadlines)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id) DO NOTHING
        RETURNING id
        """

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                query,
                user_task.id,
                user_task.current_step,
                user_task.current_deadline,
                json.dumps(user_task.deadlines, default=lambda x: x.isoformat()) if user_task.deadlines else None
            )
            return result is not None
        
    async def get_user(self, user_id: int) -> Optional[User]:
        """Получение пользователя"""
        query = "SELECT * FROM users_data WHERE id = $1"
        
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(query, user_id)
            if record:
                stages_plan = json.loads(record['stages_plan']) if record['stages_plan'] else None
                substages_plan = json.loads(record['substages_plan']) if record['substages_plan'] else None
                messages = json.loads(record['messages']) if record['messages'] else None
                question_dialog = json.loads(record['question_dialog']) if record['question_dialog'] else None

                return User(
                    id=record['id'],
                    goal=record['goal'],
                    stages_plan=stages_plan,
                    substages_plan=substages_plan,
                    messages=messages,
                    question_dialog=question_dialog,
                    access=record['access'],
                    created_at=record['created_at'],
                    is_admin=record["is_admin"],
                    last_access=record["last_access"]
                )
            logging.warning(f"Пользователь с id={user_id} не найден в БД")
            return None
        
    async def get_user_task(self, user_id: int) -> Optional[UserTask]:
        """Получение текущей задачи пользователя"""
        query = "SELECT * FROM users_tasks WHERE id=$1"

        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(query, user_id)
            if record:
                deadlines = json.loads(record["deadlines"]) if record["deadlines"] else None

                return UserTask(
                    id=record["id"],
                    current_step=record["current_step"],
                    current_deadline=record["current_deadline"],
                    deadlines=deadlines
                )
        
    async def update_user(self, user: User) -> None:
        """Обновление данных пользователя"""
        query = """
        UPDATE users_data 
        SET 
            goal = $1,
            stages_plan = $2,
            messages = $3,
            question_dialog = $4,
            access = $5,
            substages_plan = $6,
            is_admin = $7,
            last_access = $8
        WHERE id = $8
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                user.goal,
                json.dumps(user.stages_plan) if user.stages_plan else None,
                json.dumps(user.messages) if user.messages else None,
                json.dumps(user.question_dialog) if user.question_dialog else None,
                user.access,
                json.dumps(user.substages_plan) if user.substages_plan else None,
                user.is_admin,
                user.id,
                user.last_access
            )

    async def update_user_task(self, user_task: UserTask) -> None:
        "Обновление данных о задаче пользователя"
        query = """
        UPDATE users_tasks
        SET
            current_step = $1,
            current_deadline = $2,
            deadlines = $3
        WHERE id = $4
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                user_task.current_step,
                user_task.current_deadline,
                json.dumps(user_task.deadlines, default=lambda x: x.isoformat()) if user_task.deadlines else None,
                user_task.id
            )


    async def get_users_for_reminder_create_plan(self, days_threshold: int = 1) -> list[dict]:
        """
            Получаем пользователей, которым нужно напомнить о создании плана
            :param days_threshold: сколько дней прошло с момента регистрации
            :return: список словарей с id пользователей
        """
        query = """
            SELECT id FROM users_data
            WHERE 
                (goal IS NULL OR stages_plan IS NULL) AND
                created_at < NOW() - INTERVAL '1 day' * $1 AND
                access = TRUE
        """
        
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, days_threshold)
            return [dict(record) for record in records]

    async def get_users_to_remind_deadline(self) -> list[dict]:
        """
            Получаем пользователей, у которых сегодня дедлайн по задаче
            :return: список словарей с id пользователей
        """
        query = """
            SELECT ut.id
            FROM users_tasks ut
            JOIN users_data ud ON ut.id = ud.id
            WHERE 
                ut.current_deadline IS NOT NULL AND
                (ut.current_deadline::date = CURRENT_DATE OR ut.current_deadline::date < CURRENT_DATE) AND
                ud.access = TRUE
        """
        
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query)
            return [dict(record) for record in records]
        
    async def get_all_users(self) -> List[User]:
        """Получение всех пользователей из БД"""
        query = "SELECT * FROM users_data"
        
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query)
            users = []
            for record in records:
                stages_plan = json.loads(record['stages_plan']) if record['stages_plan'] else None
                substages_plan = json.loads(record['substages_plan']) if record['substages_plan'] else None
                messages = json.loads(record['messages']) if record['messages'] else None
                question_dialog = json.loads(record['question_dialog']) if record['question_dialog'] else None
                users.append(User(
                    id=record['id'],
                    goal=record['goal'],
                    stages_plan=stages_plan,
                    substages_plan=substages_plan,
                    messages=messages,
                    question_dialog=question_dialog,
                    access=record['access'],
                    created_at=record['created_at'],
                    is_admin=record["is_admin"],
                    last_access=record["last_access"]
                ))
            return users

    async def bulk_update_access(self, user_ids: List[int], access: bool):
        """Массовое обновление статуса доступа"""
        query = "UPDATE users_data SET access = $1 WHERE id = ANY($2::bigint[])"
        async with self.pool.acquire() as conn:
            await conn.execute(query, access, user_ids)


    async def delete_old_users(self):
        """Удаляем пользователей без доступа и с последним доступом > 2 дней назад"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    delete_tasks_query = """
                        DELETE FROM users_tasks 
                        WHERE id IN (
                            SELECT id FROM users_data 
                            WHERE access = FALSE 
                            AND last_access < NOW() - INTERVAL '2 days'
                            AND is_admin = FALSE
                        )
                    """
                    deleted_tasks_count = await conn.execute(delete_tasks_query)
                    
                    delete_users_query = """
                        DELETE FROM users_data 
                        WHERE access = FALSE 
                        AND last_access < NOW() - INTERVAL '2 days'
                        AND is_admin = FALSE
                    """
                    deleted_users_count = await conn.execute(delete_users_query)
                    
                    logging.info(
                        f"Удалено: {deleted_users_count} пользователей, "
                        f"{deleted_tasks_count} связанных задач"
                    )
                    return deleted_users_count
                    
                except Exception as e:
                    logging.error(f"Ошибка при удалении старых пользователей: {str(e)}")
                    raise
