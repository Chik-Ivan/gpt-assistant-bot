import asyncio
import aiohttp
import os

URL = f"https://{os.getenv('WEBHOOK_HOST')}"

async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(URL) as response:
                    print(f"Pinged {URL}: {response.status}")
        except Exception as e:
            print(f"Keep-alive error: {e}")
        await asyncio.sleep(30)
        
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

start_choice_keyboard = InlineKeyboardMarkup(row_width=2)
start_choice_keyboard.add(
    InlineKeyboardButton("🔄 Начать заново", callback_data="start_over"),
    InlineKeyboardButton("➡️ Продолжить", callback_data="continue")
)

support_button = ReplyKeyboardMarkup(resize_keyboard=True)
support_button.add(KeyboardButton("👨‍💻 Техподдержка"))