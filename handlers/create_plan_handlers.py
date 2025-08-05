import logging
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.chat_action import ChatActionSender
from keyboards.all_inline_keyboards import get_continue_create_kb
from database.core import db
from database.models import UserTask
from gpt import gpt
from utils.all_utils import extract_between, extract_days, parse_plan
from create_bot import bot
from handlers.current_plan_handler import SetTimeReminder


class Plan(StatesGroup):
    questions = State()
    let_goal_and_plan = State()


create_plan_router = Router()


@create_plan_router.message(F.text == "📋 Создать новый план")
async def start_create_plan(message: Message, state: FSMContext):
    cur_state = await state.get_state()

    logging.info(f"CUR_STATE: {cur_state}")

    if cur_state is not None and cur_state != SetTimeReminder.set_reminder_time:
        await message.answer("Вы уже начали заполнять свой персональный план, " 
                            "для создания нового, вам нужно очистить данные о старом.",
                             reply_markup=get_continue_create_kb())
        return
    
    db_repo = await db.get_repository()
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await db_repo.get_user(message.from_user.id)

        if user is None:
            logging.error("Не найден пользователь при попытке создания нового плана")
            await message.answer("Ошибка! Обратитесь к администратору.")
            return
        else:
            logging.info(f"Пользователь получен, id: {user.id}")


        if user.goal:
            await message.answer("У вас уже есть план, при создании нового плана придется очистить данные о старом старый.", 
                                 reply_markup=get_continue_create_kb())
            return
        
        if user.messages:
            await message.answer("Вы уже начали заполнять свой персональный план, " 
                                "для создания нового, вам нужно очистить данные о старом.",
                                reply_markup=get_continue_create_kb())
            return
    
        
        dialog, reply, status_code = await gpt.chat_for_plan(user.messages, 
                                                             message.text)    
        await message.answer(reply)

    match status_code:
        case 0:
            await state.set_state(Plan.questions)
            user.messages = dialog
            await db_repo.update_user(user)
            logging.info("Успешный старт опроса для заполнения анкеты")
        case 1:
            logging.info("Статус код 1 при старте заполнения анкеты")
            pass
        case 2:
            await state.clear()
            user.messages = None
            logging.info("Статус код 2 при старте заполнения анкеты")
            await message.answer("Приношу извинения за неудачу в создании плана.\n"
                                 "Давай попробуем еще раз, нажми на кнопку для создания плана.")
            await db_repo.update_user(user)


@create_plan_router.callback_query(F.data == "delete_data")
async def delete_dialog(call: CallbackQuery, state: FSMContext):
    logging.info("Хендлер удаления запущен")
    await state.clear()
    await call.answer()
    
    try:
        db_repo = await db.get_repository()
        user = await db_repo.get_user(call.from_user.id)
        user.messages = None
        user.plan = None
        user.goal = None
        await db_repo.update_user(user)
        user_task = await db_repo.get_user_task(call.from_user.id)
        if user_task:
            user_task.current_step = 0
            user_task.deadlines = None
            db_repo.update_user_task(user_task)
        await call.message.answer("Успешная отчистка данных, теперь можете попробовать заполнить анкету снова!")
    except Exception as e:
        await call.message.answer(f"Произошла ошибка: {e}")


@create_plan_router.message(Plan.questions)
async def questions_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    current_q = data.get("current_question", 0)
    logging.info(f"CURRENT_Q: {current_q}")
    if current_q == 4: # до этого вопроса было задано еще 4
        await state.set_state(Plan.let_goal_and_plan)

    db_repo = await db.get_repository()
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await db_repo.get_user(message.from_user.id)

        if user is None:
            logging.error(f"Не найден пользователь при попытке заполнении анкеты."
                        f"Вопрос номер : {current_q}; id пользователя : {message.from_user.id}")
            await message.answer("Ошибка! Обратитесь к администратору.")
            return

        dialog, reply, status_code = await gpt.chat_for_plan(user.messages, 
                                                             message.text)    

        await message.answer(reply)

    match status_code:
        case 0:
            user.messages = dialog
            await db_repo.update_user(user)
            data["current_question"] = current_q + 1
            await state.set_data(data)
            logging.info("Статус код 0 при заполнении анкеты")
        case 1:
            logging.info("Статус код 1 при заполнении анкеты")
            pass
        case 2:
            await state.clear()
            user.messages = None
            logging.info("Статус код 2 при заполнении анкеты")
            await message.answer("Приношу извинения за неудачу в создании плана.\n"
                                 "Давай попробуем еще раз, нажми на кнопку для создания плана.")
            await db_repo.update_user(user)


@create_plan_router.message(Plan.let_goal_and_plan)
async def let_goal_and_plan(message: Message, state: FSMContext):
    db_repo = await db.get_repository()
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await db_repo.get_user(message.from_user.id)

        if user is None:
            logging.error(f"Не найден пользователь при попытке получения плана."
                        f"id пользователя : {message.from_user.id}")
            await message.answer("Ошибка! Обратитесь к администратору.")
            return

        dialog, reply, status_code = await gpt.chat_for_plan(user.messages, 
                                                             message.text)    

        await message.answer(reply)
        logging.info("Бот вернул план пользователю")
    match status_code:
        case 0:
            user.messages = dialog
            user.goal = re.sub(r'^[\s:\-–—]+', '', extract_between(reply, "Итак, твоя цель", "Вот твой план"))
            user.plan = parse_plan(extract_between(reply, "Вот твой план:", "Я буду присылать тебе каждую неделю план. Не сливайся!"))
            await db_repo.update_user(user)
            user_task = await db_repo.get_user_task(message.from_user.id)
            if user_task:
                user_task.current_step = 0
                user_task.deadlines = get_deadlines(user.plan)
                await db_repo.update_user_task(user_task)
            else:
                
                result = await db_repo.create_user_task(UserTask(id=message.from_user.id))
                if result:
                    logging.info(f"Успешно добавлена задача для пользователя: {message.from_user.id}")
                else:
                    logging.error(f"Проблема создания новой задачи для пользователя: {message.from_user.id}."
                                  "Скорее всего задача уже существует и была попытка создания новой, вместо обновления старой")

            await state.clear()
            logging.info("Статус код 0 при завершении заполнения анкеты")
        case 1:
            logging.info("Статус код 1 при завершении заполнения анкеты")
            pass
        case 2:
            await state.clear()
            user.messages = None
            logging.info("Статус код 2 при завершении заполнения анкеты")
            await db_repo.update_user(user)


def get_deadlines(plan: Optional[Dict[str, Dict]]) -> List[datetime]:
    if not plan:
        return []

    deadlines = []
    today = datetime.now()
    today = datetime(
        year=today.year,
        month=today.month,
        day=today.day,
        hour=12,
        minute=0,
        second=0,
    )


    for week in plan.keys():        
        for index, task in enumerate(plan[week].keys()):
            if index == 2:
                today += timedelta(days=3)
                deadlines.append(today)
                continue
            today += timedelta(days=2)
            deadlines.append(today)

    return deadlines
