from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from database.core import db

async def get_main_keyboard(user_id: int):
    kb_list = [
        [KeyboardButton(text="📋 Создать план"), KeyboardButton(text="❗ Задание этапа")],
        [KeyboardButton(text="🗒️ Текущий план"), KeyboardButton(text="⌛ Статус плана")],
        [KeyboardButton(text="🆘 поддержка"), (KeyboardButton(text="👤 Личный кабинет"))],
    ]
    db_repo = await db.get_repository()
    user = await db_repo.get_user(user_id)
    if user.is_admin:
        kb_list[-1].extend([KeyboardButton(text="⚙️ Админ панель")])
    
    return ReplyKeyboardMarkup(keyboard=kb_list,
                               resize_keyboard=True,
                               one_time_keyboard=False,
                               is_persistent=True)