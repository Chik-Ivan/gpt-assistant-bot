from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_continue_create_kb():
    kb_list = [
        [InlineKeyboardButton(text="Хочу удалить данные!", callback_data="delete_data")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_list)
    return keyboard


def week_tasks_keyboard():
    kb_list = [
        [InlineKeyboardButton(text="Задать вопрос", callback_data="ask_question")],
        [InlineKeyboardButton(text="Отметить неделю выполненной", callback_data="mark_completed")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)


def support_kb():
    kb_list = [
        [InlineKeyboardButton(text="Поддержка", url="https://t.me/Abramova_school_support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)

def stop_question_kb():
    kb_list = [
        [InlineKeyboardButton("Прекратить обусждение!", callback_data="stop_question")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)
