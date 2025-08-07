from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from config import ADMINS


def get_main_keyboard(user_id: int):
    kb_list = [
        [KeyboardButton(text="📋 Создать план"), KeyboardButton(text="❗ Задание этапа")],
        [KeyboardButton(text="🗒️ Текущий план"), KeyboardButton(text="⌛ Статус плана")],
        [KeyboardButton(text="🆘 поддержка"), (KeyboardButton(text="👤 Личный кабинет"))],
    ]
    if user_id in ADMINS:
        kb_list[-1].extend([KeyboardButton(text="⚙️ Админ панель")])
    
    return ReplyKeyboardMarkup(keyboard=kb_list,
                               resize_keyboard=True,
                               one_time_keyboard=False,
                               is_persistent=True)