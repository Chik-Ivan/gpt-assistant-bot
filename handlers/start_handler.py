from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from keyboards.all_inline_keyboards import get_continue_create_kb, stop_question_kb
from create_bot import logger
from database.core import db
from database.models import User
from handlers.current_plan_handler import AskQuestion
from handlers.create_plan_handlers import start_create_plan


start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):

    db_repo = await db.get_repository()  

    cur_state = await state.get_state()
    if cur_state is not None and cur_state != AskQuestion.ask_question:
        await message.answer("Вы уже начали заполнять свой персональный план, " 
                             "хотите удалить заполненные данные или продолжим с того места, на котором остановились?",
                             reply_markup=get_continue_create_kb())
        return
    elif cur_state == AskQuestion.ask_question:
        await message.answer("Кажется, сейчас мы обсуждаем детали твоего плана, хочешь прекратить это?", reply_markup=stop_question_kb())
        return
    
    new_user = User(
        id=message.from_user.id,
        goal="",
        stages_plan=None,
        substages_plan = None,
        messages=None,
        access=False
    )

    try:
        created = await db_repo.create_user(new_user)
        logger.info(f"Попытка добавить пользователя с id: {new_user.id}")
        if created:
            logger.info(f"Новый пользователь добавлен: {message.from_user.id}")
        else:
            logger.info(f"Пользователь уже существует: {message.from_user.id}")
            
        await start_create_plan(message, state)
    except Exception as e:
        logger.error(f"Ошибка при создании пользователя: {e}")
        await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте ещё раз.\n\n При повторении ошибки обратитесь в поддержку.")
        return

    