from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# Главное меню
main_menu = (
    ReplyKeyboardMarkup(resize_keyboard=True)  # type: ignore
    .add(  # type: ignore
        KeyboardButton("🎯 Цель"),  # type: ignore
        KeyboardButton("📅 План"),  # type: ignore
        KeyboardButton("✅ Проверка"),  # type: ignore
    )
    .add(KeyboardButton("💬 Поддержка"))  # type: ignore
)

# Кнопка поддержки (inline)
support_button = InlineKeyboardMarkup().add(
    InlineKeyboardButton("💬 Написать в поддержку", url="https://t.me/Abramova_school_support")  # type: ignore
)
