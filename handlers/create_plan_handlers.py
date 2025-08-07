import logging
import re
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.chat_action import ChatActionSender
from keyboards.all_inline_keyboards import get_continue_create_kb, stop_question_kb
from keyboards.all_text_keyboards import get_main_keyboard
from database.core import db
from database.models import UserTask
from gpt import gpt, hello_prompt, create_question_prompt, check_answer_prompt, create_plan_prompt
from utils.all_utils import extract_between, extract_days, parse_plan
from create_bot import bot
from handlers.current_plan_handler import AskQuestion


class Plan(StatesGroup):
    confirmation_of_start = State()
    find_level = State()
    find_goal = State()
    find_fear = State()
    find_time_in_week = State()
    find_time_for_target = State()
    let_goal_and_plan = State()


create_plan_router = Router()


async def gpt_step(message: Message, state: FSMContext, add_to_prompt: str, next_state: State):
    db_repo = await db.get_repository()
    user = await db_repo.get_user(message.from_user.id)
    prompt = check_answer_prompt + f"{user.messages}\n\n тебе нужно оценить ответ \"{message.text}\"\nна вопрос\n\"{user.messages[-1]}\""
    reply = gpt.chat_for_plan(prompt) 
    reply = json.loads(reply)
    match int(reply["status"]):
        case 0:
            user.messages.append({"role": "user", "content": message.text})
            prompt = create_question_prompt + f"{user.messages}\n\n {add_to_prompt}"
            reply = gpt.chat_for_plan(prompt)
            reply = json.loads(reply)
            if reply["question_text"]:
                await message.answer(reply["question_text"])
                await state.set_state(next_state)
                user.messages.append({"role": "assistant", "content": reply["question_text"]})
                await db_repo.update_user(user)
            else:
                await message.answer("Ошибка при обработке запроса, попробуйте еще раз позже")
                logging.warning(f"Ошибка при создании вопроса об уровне пользователя\n\nОтвет гпт: {reply}")
        case 1:
            if reply["reply"]:
                await message.answer(reply["reply"])
            else:
                await message.answer("Ошибка при обработке запроса, попробуйте еще раз позже")
                logging.warning(f"Ошибка при создании вопроса об уровне пользователя\n\nОтвет гпт: {reply}")
        case 2:
            if reply["reply"]:
                await message.answer(reply["reply"], reply_markup=stop_question_kb())
            else:
                await message.answer("Ошибка при обработке запроса, попробуйте еще раз позже")
                logging.warning(f"Ошибка при создании вопроса об уровне пользователя\n\nОтвет гпт: {reply}")


async def check_state(message: Message, state: FSMContext):
    cur_state = await state.get_state()

    logging.info(f"CUR_STATE: {cur_state}")

    if cur_state is not None and cur_state != AskQuestion.ask_question:
        await message.answer("В данный момент я пытаюсь заполнить вашу анкету для нового плана, " 
                            "вы можете согласиться на потерю данных и начать пользоваться остальными командами без ограничений.",
                             reply_markup=get_continue_create_kb())
        return None
    elif cur_state == AskQuestion.ask_question:
        await message.answer("Кажется, сейчас мы обсуждаем детали твоего плана на неделю, хочешь прекратить это?", reply_markup=stop_question_kb())
        return None
    return True


@create_plan_router.message(F.text == "📋 Создать план")
async def start_create_plan(message: Message, state: FSMContext):
    check = await check_state(message, state)
    if not check:
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
    
        
        reply = gpt.chat_for_plan(hello_prompt)
        reply = json.loads(reply)
        if reply["hello_message"]:
            await message.answer(reply["hello_message"], reply_markup=get_main_keyboard(message.from_user.id))
            await state.set_state(Plan.confirmation_of_start)
            user.messages = [{"role": "assistant", "content": reply["hello_message"]}]
            await db_repo.update_user(user)
            return
        logging.info(f"Ответ при приветственном сообщении:\n\n {reply}")
        await message.answer(f"Кажется произошла ошибка, попробуйте позже!", reply_markup=get_main_keyboard())



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
            await db_repo.update_user_task(user_task)
        await call.message.answer("Успешная отчистка данных, теперь можете попробовать заполнить анкету снова!")
    except Exception as e:
        await call.message.answer(f"Произошла ошибка: {e}")
        logging.error(f"Ошибка: {e}, при удалении данных")


@create_plan_router.message(Plan.confirmation_of_start)
async def confirmation_of_start(message: Message, state: FSMContext):
    logging.info("Start confirmation_of_start")
    try:
        add_text = "тебе нужно придумать вопрос об уровне навыков пользователя (кто он? может быть новичок или любитель)"
        await gpt_step(message, state, add_text, Plan.find_level)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в confirmation_of_start")


@create_plan_router.message(Plan.find_level)
async def find_level(message: Message, state: FSMContext):
    logging.info("Start find_level")
    try:
        add_text = "тебе нужно придумать вопрос о цели пользователя, о том, чего он хочет достичь (это может быть определенный уровень дохода или мастерства)"
        await gpt_step(message, state, add_text, Plan.find_goal)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_level")


@create_plan_router.message(Plan.find_goal)
async def find_goal(message: Message, state: FSMContext):
    logging.info("Start find_goal")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать у пользователя о его страхах или возможных препятствиях при достижении его цели"
        await gpt_step(message, state, add_text, Plan.find_fear)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_goal")


# @create_plan_router.message(Plan.questions)
# async def questions_handler(message: Message, state: FSMContext):
#     data = await state.get_data()
#     current_q = data.get("current_question", 0)
#     logging.info(f"CURRENT_Q: {current_q}")

#     db_repo = await db.get_repository()
#     async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
#         user = await db_repo.get_user(message.from_user.id)

#         if user is None:
#             logging.error(f"Не найден пользователь при попытке заполнении анкеты."
#                         f"Вопрос номер : {current_q}; id пользователя : {message.from_user.id}")
#             await message.answer("Ошибка! Обратитесь к администратору.")
#             return

#         dialog, reply, status_code = await gpt.chat_for_plan(user.messages, 
#                                                              message.text)    

#         await message.answer(reply)

#     match status_code:
#         case 0:
#             user.messages = dialog
#             await db_repo.update_user(user)
#             if current_q == 4: # до этого вопроса было задано еще 4
#                 await state.set_state(Plan.let_goal_and_plan)
#             data["current_question"] = current_q + 1
#             await state.set_data(data)
#             logging.info("Статус код 0 при заполнении анкеты")
#         case 1:
#             logging.info("Статус код 1 при заполнении анкеты")
#             pass
#         case 2:
#             await state.clear()
#             user.messages = None
#             logging.info("Статус код 2 при заполнении анкеты")
#             await message.answer("Приношу извинения за неудачу в создании плана.\n"
#                                  "Давай попробуем еще раз, нажми на кнопку для создания плана.")
#             await db_repo.update_user(user)


# @create_plan_router.message(Plan.let_goal_and_plan)
# async def let_goal_and_plan(message: Message, state: FSMContext):
#     db_repo = await db.get_repository()
#     async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
#         user = await db_repo.get_user(message.from_user.id)

#         if user is None:
#             logging.error(f"Не найден пользователь при попытке получения плана."
#                         f"id пользователя : {message.from_user.id}")
#             await message.answer("Ошибка! Обратитесь к администратору.")
#             return

#         dialog, reply, status_code = await gpt.chat_for_plan(user.messages, 
#                                                              message.text)    
#         json_text = extract_between(reply, "<json>", "</json>")
#         if json_text:
#             reply = re.sub(r"<json>.*?</json>", "", reply, flags=re.DOTALL).strip()
#             json_text = json.loads(json_text)
#         await message.answer(reply)
#     match status_code:
#         case 0:
#             if json_text:
#                 user.goal = json_text.get("goal")
#                 user.plan = json_text.get("plan")
#             else:
#                 user.goal = re.sub(r'^[\s:\-–—]+', '', extract_between(reply, "Итак, твоя цель", "Вот твой план"))
#                 user.plan = parse_plan(extract_between(reply, "Вот твой план:", "Я буду присылать тебе каждую неделю план. Не сливайся!"))
#             user.messages = dialog
#             await db_repo.update_user(user)
#             user_task = await db_repo.get_user_task(message.from_user.id)
#             if user_task:
#                 user_task.current_step = 0
#                 user_task.deadlines = get_deadlines(user.plan)
#                 await db_repo.update_user_task(user_task)
#             else:
                
#                 result = await db_repo.create_user_task(UserTask(id=message.from_user.id))
#                 if result:
#                     logging.info(f"Успешно добавлена задача для пользователя: {message.from_user.id}")
#                 else:
#                     logging.error(f"Проблема создания новой задачи для пользователя: {message.from_user.id}."
#                                   "Скорее всего задача уже существует и была попытка создания новой, вместо обновления старой")

#             await state.clear()
#             logging.info("Бот вернул план пользователю")

#             logging.info("Статус код 0 при завершении заполнения анкеты")
#         case 1:
#             logging.info("Статус код 1 при завершении заполнения анкеты")
#             pass
#         case 2:
#             await state.clear()
#             user.messages = None
#             logging.info("Статус код 2 при завершении заполнения анкеты")
#             await db_repo.update_user(user)


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
