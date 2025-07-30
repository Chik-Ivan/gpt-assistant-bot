from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

start_choice_keyboard = InlineKeyboardMarkup(row_width=2)
start_choice_keyboard.add(
    InlineKeyboardButton("🔄 Начать заново", callback_data="start_over"),
    InlineKeyboardButton("➡️ Продолжить", callback_data="continue")
)

support_button = ReplyKeyboardMarkup(resize_keyboard=True)
support_button.add(KeyboardButton("👨‍💻 Техподдержка")) 
