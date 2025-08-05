from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from keyboards.all_text_keyboards import get_main_keyboard
from keyboards.all_inline_keyboards import get_continue_create_kb
from create_bot import logger
from database.core import db
from database.models import User
from handlers.current_plan_handler import SetTimeReminder


start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):

    db_repo = await db.get_repository()  

    # Сначала нужно будет проверить доступ

    cur_state = await state.get_state()
    if cur_state is not None and cur_state != SetTimeReminder.set_reminder_time:
        await message.answer("Вы уже начали заполнять свой персональный план, " 
                             "хотите удалить заполненные данные или продолжим с того места, на котором остановились?",
                             reply_markup=get_continue_create_kb())
        return
    
    await message.answer("Привет, я бот-кондитер, который поможет тебе в реализации твоих целей!\n\n"
                         "Давай расскажу тебе о кнопках, с помощью которых мы с тобой можем взаимодействовать:\n\n"
                         "📋 Создать новый план - эта кнопка поможет тебе создать новый план, по которому ты сможешь двигаться к достижению своей цели\n\n"
                         "❗ Статус текущего плана - с помощью этой кнопки ты можешь отлеживать текущий план (задачу, которую тебе сейчас нужно выполнить, дедлайн по ней, а также номер этапа)"
                         "🎯 Текущая цель - эта кнопка напомнит тебе, ради чего ты так стараешься!\n\n"
                         "🗒️ Текущий план - здесь ты сможешь увидеть план целиком.\n\n"
                         "🕛 Задать удобное время напоминалкам - каждый раз в день дедлайна тебе будет приходить напоминалка, с помощью этой кнопки ты сможешь настроить их время.\n\n"
                         "🤫 Очистить данные - нажав сюда ты очистишь данные о текущем плане и твоем прогрессе в нем, используй с осторожностью!\n\n"
                         "🆘 Обратиться в поддержку (в разработке!) - в случае неполадок я могу передать твое обращения в поддержку (будет доступно одно письмо каждый час в целях борьбы со спамом)", 
                         reply_markup=get_main_keyboard(message.from_user.id))  
    
    new_user = User(
        id=message.from_user.id,
        goal="",
        plan=None,
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
            
    except Exception as e:
        logger.error(f"Ошибка при создании пользователя: {e}")
        await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте ещё раз.")
        return

    