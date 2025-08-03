import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from keyboards.all_inline_keyboards import get_continue_create_kb
from database.core import db
from gpt import gpt


class Plan(StatesGroup):
    questions = State()
    let_goal_and_plan = State()


plan_router = Router()


@plan_router.message(F.text == "📋 Создать новый план")
async def start_create_plan(message: Message, state: FSMContext):
    cur_state = await state.get_state()

    logging.info(f"CUR_STATE: {cur_state}")

    if cur_state is not None:
        await message.answer("Вы уже начали заполнять свой персональный план, " 
                             "хотите удалить заполненные данные или продолжим с того места, на котором остановились?",
                             reply_markup=get_continue_create_kb())
        return
    
    db_repo = await db.get_repository()

    user = await db_repo.get_user(message.from_user.id)

    if user is None:
        logging.error("Не найден пользователь при попытке создания нового плана")
        await message.answer("Ошибка! Обратитесь к администратору.")
        return
    else:
        logging.info(f"Пользователь получен, id: {user.id}")
    
    dialog, reply, status_code = await gpt.chat_for_plan(user.messages, message.text)    
    logging.info(f"Ответ от гпт: dialog - {dialog}; reply - {reply}; status_code - {status_code}")
    await message.answer(reply)

    match status_code:
        case 0:
            await state.set_state(Plan.questions)
            user.messages = dialog
            await db_repo.update_user(user)
        case 1:
            pass
        case 2:
            await state.clear()
            user.messages = None
            await db_repo.update_user(user)


@plan_router.message(Plan.questions)
async def questions_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    current_q = data.get("current_question", 0)

    if current_q == 5:
        await state.set_state(Plan.let_goal_and_plan)

    db_repo = await db.get_repository()

    user = await db_repo.get_user(message.from_user.id)

    if user is None:
        logging.error(f"Не найден пользователь при попытке заполнении анкеты."
                      f"Вопрос номер : {current_q}; id пользователя : {message.from_user.id}")
        await message.answer("Ошибка! Обратитесь к администратору.")
        return

    dialog, reply, status_code = await gpt.chat_for_plan(user.messages, message.text)    

    await message.answer(reply)

    match status_code:
        case 0:
            user.messages = dialog
            await db_repo.update_user(user)
        case 1:
            pass
        case 2:
            await state.clear()
            user.messages = None
            await db_repo.update_user(user)


@plan_router.message(Plan.let_goal_and_plan)
async def let_goal_and_plan(message: Message, state: FSMContext):
    db_repo = await db.get_repository()

    user = await db.get_user(message.from_user.id)

    if user is None:
        logging.error(f"Не найден пользователь при попытке получения плана."
                      f"id пользователя : {message.from_user.id}")
        await message.answer("Ошибка! Обратитесь к администратору.")
        return

    dialog, reply, status_code = await gpt.chat_for_plan(user.messages, message.text)    

    await message.answer(reply)

    match status_code:
        case 0:
            user.messages = dialog
            await db_repo.update_user(user)
            await state.clear()
        case 1:
            pass
        case 2:
            await state.clear()
            user.messages = None
            await db_repo.update_user(user)


@plan_router.callback_query(F.data == "delete_data")
async def delete_dialog(call: CallbackQuery, state: FSMContext):
    state.clear()
    try:
        db_repo = await db.get_repository()
        user = await db_repo.get_user(call.message.from_user.id)
        user.messages = None
        db_repo.update_user(user)
        call.message.answer("Успешная отчистка данных, теперь можете попробовать заполнить анкету снова!")
    except Exception as e:
        call.message.answer(f"Произошла ошибка: {e}")
