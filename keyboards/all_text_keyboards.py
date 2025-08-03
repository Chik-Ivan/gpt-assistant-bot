from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from create_bot import ADMINS


def get_main_keyboard(user_id: int):
    kb_list = [
        [KeyboardButton(text="📋 Создать новый план"), KeyboardButton(text="❗Статус текущего плана")],
        [KeyboardButton(text="🎯 Текущая цель"), KeyboardButton(text="🗒️Текущий план")]
        [KeyboardButton(text="🕛 Задать удобное время напоминалкам"), KeyboardButton(text="🤫 Очистить данные")],
        [KeyboardButton(text="🆘 Обратиться в поддержку")]
    ]
    if user_id in ADMINS:
        kb_list[-1].append(KeyboardButton(text="⚙️ Админ панель"))
    
    return ReplyKeyboardMarkup(keyboard=kb_list,
                               resize_keyboard=True,
                               one_time_keyboard=False,
                               is_persistent=True)