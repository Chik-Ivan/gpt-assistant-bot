from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from keyboards.all_text_keyboards import get_main_keyboard
from create_bot import logger
from database.database_repository import get_db
from database.models import User


start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    db = await get_db
    if state.get_state():
        await message.answer("Вы уже начали заполнять свой персональный план, " 
                            "хотите удалить заполненные данные или продолжим с того места, на котором остановились?")
        return
    
    new_user = User(
        id=message.from_user.id,
        goal="",
        plan=None,
        messages=None,
        access=False
    )

    try:
        created = await db.create_user(new_user)
        
        if created:
            logger.info(f"Новый пользователь добавлен: {message.from_user.id}")
        else:
            logger.info(f"Пользователь уже существует: {message.from_user.id}")
            
    except Exception as e:
        logger.error(f"Ошибка при создании пользователя: {e}")
        await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте ещё раз.")
        return

    await message.answer("Тут должно быть сообщение с информацией о кнопках*", 
                         reply_markup=get_main_keyboard(message.from_user.id))