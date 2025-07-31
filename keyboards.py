from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

start_choice_keyboard = InlineKeyboardMarkup(row_width=2)
start_choice_keyboard.add(
    InlineKeyboardButton("🔄 Начать заново", callback_data="start_over"),
    InlineKeyboardButton("➡️ Продолжить", callback_data="continue")
)

support_button = ReplyKeyboardMarkup(resize_keyboard=True)
support_button.add(KeyboardButton("👨‍💻 Техподдержка")) 


clear_memory_keyboard = InlineKeyboardMarkup(row_width=1)
clear_memory_keyboard.add(
    InlineKeyboardButton("🧹 Стереть память", callback_data="confirm_clear")
)

confirm_clear_memory_keyboard = InlineKeyboardMarkup(row_width=2)
confirm_clear_memory_keyboard.add(
    InlineKeyboardButton("✅ Да, стереть", callback_data="clear_confirmed"),
    InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel")
)



from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

start_choice_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
start_choice_keyboard.add(KeyboardButton("🔁 Начать сначала"), KeyboardButton("▶️ Продолжить"))

clear_memory_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
clear_memory_keyboard.add(KeyboardButton("🧹 Стереть память"))

confirm_clear_memory_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
confirm_clear_memory_keyboard.add(
    KeyboardButton("✅ Подтвердить"),
    KeyboardButton("❌ Отмена")
)

