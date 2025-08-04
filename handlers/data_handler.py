from aiogram import Router, F
from aiogram.types import Message
from keyboards.all_inline_keyboards import get_continue_create_kb


data_router = Router()


@data_router.message(F.text=="🤫 Очистить данные")
async def clear_data(message: Message):
    await message.answer("Ты действительно хочешь очистить данные с сервера?", reply_markup=get_continue_create_kb())
