from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 💬 Кнопка для связи с техподдержкой
support_button = InlineKeyboardMarkup().add(
    InlineKeyboardButton(
        text="💬 Написать в поддержку",
        url="https://t.me/Abramova_school_support"
    )
)