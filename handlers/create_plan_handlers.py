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
    find_time_for_goal = State()


create_plan_router = Router()


async def gpt_step(message: Message, state: FSMContext, add_to_prompt: str, next_state: State, add_to_answer_check: str = ""):
    db_repo = await db.get_repository()
    user = await db_repo.get_user(message.from_user.id)
    prompt = check_answer_prompt + f"{user.messages}\n\n тебе нужно оценить ответ \"{message.text}\"\nна вопрос\n\"{user.messages[-1]}\" \n\n{add_to_answer_check}"
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
        user.stages_plan = None
        user.substages_plan = None
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
        add_text_for_check_answer = "в ответе не обязательно должно быть \"Любитель, профи, новичок\" там может быть и что-то другое, например учусь или прохожу курсы для начинающим, или умею делать простые торты"
        add_text = "тебе нужно придумать вопрос о цели пользователя, о том, чего он хочет достичь (это может быть определенный уровень дохода или мастерства, а может быть что-нибудь мелкое. Главное чтобы была цель связанная с кондитерством)"
        await gpt_step(message, state, add_text, Plan.find_goal)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_level")


@create_plan_router.message(Plan.find_goal)
async def find_goal(message: Message, state: FSMContext):
    logging.info("Start find_goal")
    try:
        add_text_to_answer_check = "Цель не обязательно должна быть связана с финансами, это может быть и что-то мелкое, главное, чтобы было связано с кондитерством"
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать у пользователя о его страхах или возможных препятствиях при достижении его цели"
        await gpt_step(message, state, add_text, Plan.find_fear, add_text_to_answer_check)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_goal")


@create_plan_router.message(Plan.find_fear)
async def find_fear(message: Message, state: FSMContext):
    logging.info("start find_fear")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать у пользователя сколько времени в неделю или в день он готов уделять для достижения своей цели (в часах)"
        await gpt_step(message, state, add_text, Plan.find_time_in_week)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_fear")


@create_plan_router.message(Plan.find_time_in_week)
async def find_time_in_week(message: Message, state: FSMContext):
    logging.info("start find_time_in_week")
    try:
        add_text_to_answer_check = "Если пользователь указал количество часов в сутки, то принимай этот ответ"
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать за сколько времени пользователь хочет достичь своей цели (может быть несколько дней, недель или месяцев)"
        await gpt_step(message, state, add_text, Plan.find_time_for_goal, add_text_to_answer_check)
    except Exception as e:
        logging.error(f"Ошибка {e}, в find_time_in_week")

    
@create_plan_router.message(Plan.find_time_for_goal)
async def find_time_for_goal(message: Message, state: FSMContext):
    logging.info("start find_time_for_goal")
    try:
        
        db_repo = await db.get_repository()
        user = await db_repo.get_user(message.from_user.id)
        prompt = check_answer_prompt + f"{user.messages}\n\n тебе нужно оценить ответ \"{message.text}\"\nна вопрос\n\"{user.messages[-1]}\""
        reply = gpt.chat_for_plan(prompt) 
        reply = json.loads(reply)
        match int(reply["status"]):
            case 0:
                await message.answer("Подожди немного, я составляю для тебя персональный план..")
                user.messages.append({"role": "user", "content": message.text})
                prompt = create_plan_prompt + f"{user.messages}\n\n Сегодняшняя дата {datetime.now().strftime('%d.%m.%Y')}"
                reply = gpt.chat_for_plan(prompt)
                reply = json.loads(reply)
                if reply["goal"] and reply["plan"]:
                    stages, substages = reply["plan"], reply["substage"]
                    text = ["Хорошо! Спасибо, что ответил на мои вопросы!", "Вот твой план по достижению цели! \nА с помощью кнопки \"❗ Задания этапа \", ты можешь увидеть подэтапы плана при их наличии\n"]
                    await state.clear()
                    user.stages_plan = stages
                    user.substages_plan = substages
                    user.goal = reply["goal"]
                    await db_repo.update_user(user)
                    
                    deadlines = []
                    for i, (stage_key, stage_value) in enumerate(stages.items(), start=1):
                        stage_num = str(i)
                        if stage_num in substages:
                            for sub in substages[stage_num].values():
                                date_str = sub.split(" - ")[-1].strip()
                                deadlines.append(datetime.strptime(date_str, "%d.%m.%Y"))
                        else:
                            date_str = stage_value.split(" - ")[-1].strip()
                            deadlines.append(datetime.strptime(date_str, "%d.%m.%Y"))
                    user_task = await db_repo.get_user_task(user.id)
                    if user_task:
                        user_task.deadlines = deadlines
                        user_task.current_deadline = deadlines[0] if deadlines else None
                        await db_repo.update_user_task(user_task)
                    else:
                        user_task = UserTask(
                            id=user.id,
                            current_step=0,
                            deadlines=deadlines,
                            current_deadline=deadlines[0]
                        )
                        await db_repo.create_user_task(user_task)
                    for stage_name, stage_value in stages.items():
                        text.append(f"{stage_name} - {stage_value}\n")
                    await message.answer('\n'.join(text))
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
    except Exception as e:
        logging.error(f"Ошибка {e}, в find_time_for_goal")



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
