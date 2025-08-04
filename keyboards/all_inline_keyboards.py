from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_continue_create_kb():
    kb_list = [
        [InlineKeyboardButton(text="Хочу удалить данные!", callback_data="delete_data")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_list)
    return keyboard
