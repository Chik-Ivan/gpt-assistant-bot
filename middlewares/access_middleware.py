import logging
from datetime import datetime
from aiogram import BaseMiddleware
from aiogram.types import Message
from database.core import db
from database.models import User
from keyboards.all_inline_keyboards import support_kb

class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, message: Message, data):
        if not message.text or message.text.startswith('/'):
            return await handler(message, data)
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
                is_admin=False,
                last_access=datetime.strptime(datetime.now(), "%d.%m.%Y").date()
            )
            await db_repo.create_user(user)
        if not user.access and not user.is_admin:
            await message.answer("Похоже, у вас нет доступа к этому боту", reply_markup=support_kb())
            logging.warning(f"Попытка воспользоваться ботом без доступа\n\nid пользователя: {user.id}")
            return
        return await handler(message, data)