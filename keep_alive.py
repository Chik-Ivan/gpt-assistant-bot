
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
        
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

start_choice_keyboard = InlineKeyboardMarkup(row_width=2)
start_choice_keyboard.add(
    InlineKeyboardButton(text="🔁 Начать сначала", callback_data="fsm_restart"),
    InlineKeyboardButton(text="▶️ Продолжить", callback_data="fsm_continue")
)