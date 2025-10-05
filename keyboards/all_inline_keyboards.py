from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_continue_create_kb():
    kb_list = [
        [InlineKeyboardButton(text="Продолжить", callback_data="continue_fill_data")],
        [InlineKeyboardButton(text="Хочу новый план", callback_data="delete_data")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_list)
    return keyboard


def get_plan_exists_kb():
    kb_list = [
        [InlineKeyboardButton(text="Продолжить", callback_data="continue_with_exists_plan")],
        [InlineKeyboardButton(text="Удалить старый план", callback_data="delete_data")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_list)
    return keyboard

def week_tasks_keyboard():
    kb_list = [
        [InlineKeyboardButton(text="Задать вопрос", callback_data="ask_question")],
        [InlineKeyboardButton(text="Отметить шаг выполненным", callback_data="mark_completed")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)


def support_kb():
    kb_list = [
        [InlineKeyboardButton(text="Поддержка", url="https://t.me/Abramova_school_support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)

def stop_question_kb():
    kb_list = [
        [InlineKeyboardButton(text="Прекратить обусждение!", callback_data="stop_question")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)


def remind_about_deadline_kb():
    kb_list = [
        [InlineKeyboardButton(text="Задача выполнена!", callback_data="task_completed_on_time")],
        [InlineKeyboardButton(text="Не успеваю, сдвинь дедлайны!", callback_data="postponement_deadlines")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_list)
