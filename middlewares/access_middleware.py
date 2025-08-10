import logging
from aiogram.types import Message
from aiogram.dispatcher.middlewares import BaseMiddleware
from database.core import db
from aiogram.dispatcher.flags import CancelHandler
from database.models import User

class AccessMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: Message, data: dict):
        if not message.text or message.text.startswith('/'):
            return
        db_repo = await db.get_repository()
        user = await db_repo.get_user(message.from_user.id)
        if not user:
            user = User(
                id=message.from_user.id,
                goal="",
                stages_plan=None,
                substages_plan = None,
                messages=None,
                access=False,
                is_admin=False
            )
            await db_repo.create_user(user)
        if not user.access and not user.is_admin:
            await message.answer("Похоже, у вас нет доступа к этому боту")
            logging.warning(f"Попытка воспользоваться ботом без доступа\n\nid пользователя: {user.id}")
            raise CancelHandler()