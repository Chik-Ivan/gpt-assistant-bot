from aiogram import Router, F
from aiogram.types import Message


main_kb_router = Router()


@main_kb_router.message(F.text=="📋 Создать новый план")
async def create_new_plan(message: Message):
    await message.answer("Пытаемся создать новый план")
