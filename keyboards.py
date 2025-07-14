from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Кнопка поддержки (inline)
support_button = InlineKeyboardMarkup().add(
    InlineKeyboardButton("🆘 Написать в поддержку", url="https://t.me/Abramova_school_support")  # type: ignore
)
