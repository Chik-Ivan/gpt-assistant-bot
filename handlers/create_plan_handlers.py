import logging
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
from create_bot import bot
from handlers.current_plan_handler import AskQuestion
from utils.all_utils import extract_date_from_string


class Plan(StatesGroup):
    confirmation_of_start = State()
    find_level = State()
    find_goal = State()
    goal_clarification = State()
    find_strengths = State()
    find_favorite_skills = State()
    about_promotion_and_channel = State()
    find_fear = State()
    find_time_in_week = State()
    find_time_for_goal = State()


create_plan_router = Router()


async def gpt_step(message: Message, state: FSMContext, 
                   add_to_prompt: str, next_state: State, 
                   add_to_answer_check: str = "", need_answer_options: bool = False,
                   question_number: int = 0):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        await message.answer("Подожди немного, пока я подготавливаю вопрос:)")
        db_repo = await db.get_repository()
        user = await db_repo.get_user(message.from_user.id)
        prompt = check_answer_prompt + f"{user.messages}\n\n тебе нужно оценить ответ \"{message.text}\"\nна вопрос\n\"{user.messages[-1]}\" \n\n{add_to_answer_check}"
        reply = gpt.chat_for_plan(prompt) 
        reply = json.loads(reply)
        match int(reply["status"]):
            case 0:
                user.messages.append({"role": "user", "content": message.text})
                prompt = create_question_prompt + f"{user.messages}\n\n {add_to_prompt}"
                reply_question = gpt.chat_for_plan(prompt)
                reply_question = json.loads(reply_question)
                if reply_question["question_text"] and (reply_question["answer_options"] or not need_answer_options) and reply["reply"]:
                    question_text = (f"Отмечаю: <b>{message.text}</b>\n\n"
                                    f"📌 <i>Мини-итог</i>: {reply['reply']}\n\n"
                                    f"-----\n\n"
                                    f"<b>Вопрос {question_number}</b>\n"
                                    f"{reply_question['question_text']}")
                    if need_answer_options:
                        question_text += "\n"
                        for key, value in reply_question["answer_options"].items():
                            question_text += f"• {key}) {value}\n"
                    await message.answer(question_text)
                    await state.set_state(next_state)
                    user.messages.append({"role": "assistant", "content": question_text})
                    await db_repo.update_user(user)
                else:
                    await message.answer("Ошибка при обработке запроса, попробуйте еще раз позже")
                    logging.warning(f"Ошибка при создании вопроса\n\nОтвет гпт: {reply}")
            case 1:
                if reply["reply"]:
                    await message.answer(reply["reply"])
                else:
                    await message.answer("Ошибка при обработке запроса, попробуйте еще раз позже")
                    logging.warning(f"Ошибка при создании вопроса\n\nОтвет гпт: {reply}")
            case 2:
                if reply["reply"]:
                    await message.answer(reply["reply"], reply_markup=stop_question_kb())
                else:
                    await message.answer("Ошибка при обработке запроса, попробуйте еще раз позже")
                    logging.warning(f"Ошибка при создании вопроса\n\nОтвет гпт: {reply}")


async def check_state(message: Message, state: FSMContext):
    cur_state = await state.get_state()

    logging.info(f"CUR_STATE: {cur_state}")

    if cur_state is not None and cur_state != AskQuestion.ask_question:
        await message.answer("В данный момент я пытаюсь заполнить вашу анкету для нового плана, " 
                            "вы можете согласиться на потерю данных и начать пользоваться остальными командами без ограничений.",
                             reply_markup=get_continue_create_kb())
        return None
    elif cur_state == AskQuestion.ask_question:
        await message.answer("Кажется, сейчас мы обсуждаем детали твоего плана, хочешь прекратить это?", reply_markup=stop_question_kb())
        return None
    return True


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
            user_task.current_deadline = None
            await db_repo.update_user_task(user_task)
        await call.message.answer("Успешная отчистка данных, теперь можете попробовать заполнить анкету снова!")
    except Exception as e:
        await call.message.answer(f"Произошла ошибка: {e}")
        logging.error(f"Ошибка: {e}, при удалении данных")


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
            await message.answer("У вас уже есть план, при создании нового плана придется очистить данные о старом.", 
                                 reply_markup=get_continue_create_kb())
            return
        
        if user.messages:
            await message.answer("Вы уже начали заполнять свой персональный план, " 
                                "для создания нового, вам нужно очистить данные о старом.",
                                reply_markup=get_continue_create_kb())
            return
    
        
        reply = gpt.chat_for_plan(hello_prompt)
        reply = json.loads(reply)
        main_keyboard = await get_main_keyboard(message.from_user.id)
        if not reply:
            await message.answer("Произошла ошибка при попытке создания плана. Попробуйте еще раз позже, если ошибка сохранится обратитесь в поддержку.",
                                 reply_markup=main_keyboard)
            return
        if reply["hello_message"]:
            await message.answer(reply["hello_message"], reply_markup=main_keyboard)
            await state.set_state(Plan.confirmation_of_start)
            user.messages = [{"role": "assistant", "content": reply["hello_message"]}]
            await db_repo.update_user(user)
            return
        logging.info(f"Кривой ответ при приветственном сообщении:\n\n {reply}")
        await message.answer(f"Кажется произошла ошибка, попробуйте позже!", reply_markup=main_keyboard)


@create_plan_router.message(Plan.confirmation_of_start)
async def confirmation_of_start(message: Message, state: FSMContext):
    logging.info("Start confirmation_of_start")
    try:
        add_text = "тебе нужно придумать вопрос об уровне навыков пользователя (кто он? может быть новичок или любитель)"
        await gpt_step(message, state, add_text, Plan.find_level, need_answer_options=True, question_number=1)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в confirmation_of_start")


@create_plan_router.message(Plan.find_level)
async def find_level(message: Message, state: FSMContext):
    logging.info("Start find_level")
    try:
        add_text_for_check_answer = "в ответе не обязательно должно быть \"Любитель, профи, новичок\", если пользователь решил ответить что-то свое там может быть и что-то другое, например учусь или прохожу курсы для начинающим, или умею делать простые торты"
        add_text = "тебе нужно придумать вопрос о цели пользователя, о том, чего он хочет достичь (это может быть определенный уровень дохода или мастерства, а может быть что-нибудь мелкое. Главное чтобы была цель связанная с кондитерством)\nСами ответы могут быть общими, уточнение будет в следующем вопросе"
        await gpt_step(message, state, add_text, Plan.find_goal, add_text_for_check_answer, True, 2)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_level")


@create_plan_router.message(Plan.find_goal)
async def find_goal(message: Message, state: FSMContext):
    logging.info("Start find_goal")
    try:
        add_text_for_answer_check = "Цель не обязательно должна быть связана с финансами, это может быть и что-то мелкое, главное, чтобы было связано с кондитерством"
        add_text = "тебе нужно придумать вопрос для того, чтобы уточнить изначальную цель пользователя (если он хочет заработать денег, то какую сумму. Если хочет стать знаменитым, то на каком уровне и т.п.)\nВАЖНО, ЧТО ПРЕДЛОЖАННЫЕ ВАРИАНТЫ ДОЛЖНЫ ОТВЕТА ДОЛЖНЫ ПРОДОЛЖАТЬ ИЗНАЧАЛЬНО ВЫБРАННУЮ ПОЛЬЗОВАТЕЛЕМ ЦЕЛЬ!!"
        await gpt_step(message, state, add_text, Plan.goal_clarification, add_text_for_answer_check, True, 3)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_goal")


@create_plan_router.message(Plan.goal_clarification)
async def goal_clarification(message: Message, state: FSMContext):
    logging.info("Start goal_clarification")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать сильные стороны пользователя (речь не о навыках кондитерства, а в целом. Например, целеустремленность или коммуникабельность). Уточни, что пользователь может выбрать несколько вариантов ответа в своем вопросе"
        await gpt_step(message, state, add_text, Plan.find_strengths, need_answer_options=True, question_number=4)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в goal_clarification")


@create_plan_router.message(Plan.find_strengths)
async def find_strengths(message: Message, state: FSMContext):
    logging.info("Start find_strengths")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать сильные стороны пользователя конкретно в кондитерстве (например, пользователь хорошо работает с украшением тортов или может делать красивые узоры их шоколада)"
        await gpt_step(message, state, add_text, Plan.find_favorite_skills, need_answer_options=True, question_number=5)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_strengths")


@create_plan_router.message(Plan.find_favorite_skills)
async def find_favorite_skills(message: Message, state: FSMContext):
    logging.info("Start find_favorite_skills")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать о социально жизни пользователя (есть ли у него свой канал, большой ли он, хочет ли он канал если его нет)"
        await gpt_step(message, state, add_text, Plan.about_promotion_and_channel, need_answer_options=True, question_number=6)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_favorite_skills")


@create_plan_router.message(Plan.about_promotion_and_channel)
async def about_promotion_and_channel(message: Message, state: FSMContext):
    logging.info("Start about_promotion_and_channel")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать о страхах или тревожностях пользователя, которые могут помешать ему в достижении поставленной цели"
        await gpt_step(message, state, add_text, Plan.find_fear, need_answer_options=True, question_number=7)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в about_promotion_and_channel")


@create_plan_router.message(Plan.find_fear)
async def find_fear(message: Message, state: FSMContext):
    logging.info("start find_fear")
    try:
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать у пользователя сколько времени в неделю или в день он готов уделять для достижения своей цели (в часах)"
        await gpt_step(message, state, add_text, Plan.find_time_in_week, question_number=8)
    except Exception as e:
        logging.error(f"Ошибка: {e}, в find_fear")


@create_plan_router.message(Plan.find_time_in_week)
async def find_time_in_week(message: Message, state: FSMContext):
    logging.info("start find_time_in_week")
    try:
        add_text_to_answer_check = "Если пользователь указал количество часов в сутки, то принимай этот ответ"
        add_text = "тебе нужно придумать вопрос для того, чтобы узнать за сколько времени пользователь хочет достичь своей цели (может быть несколько дней, недель или месяцев)"
        await gpt_step(message, state, add_text, Plan.find_time_for_goal, add_text_to_answer_check, question_number=9)
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
                if reply["goal"] and reply["plan"] and reply["warp"] and reply["motivation"]:
                    stages, substages = reply["plan"], reply["substage"]
                    text = ("Хорошо! Спасибо, что ответил на мои вопросы!\n\n"
                            "Вот твой план по достижению цели! \nА с помощью кнопки \"❗ Задания этапа \", "
                            "ты можешь увидеть подэтапы плана при их наличии\n\n-----\n\n"
                            f"<b>1. Твоя конечная цель:</b>\n\n{reply['goal']}\n\n-----\n\n"
                            f"<b>2. Твой персональный план основывается на:</b>\n\n{reply['warp']}\n\n----\n\n"
                            f"<b>3. Пошаговый план и сроки:</b>\n\n")
                    user.stages_plan = stages
                    user.substages_plan = substages
                    user.goal = reply["goal"]
                    await db_repo.update_user(user)
                    
                    deadlines = []
                    for i, (stage_key, stage_value) in enumerate(stages.items(), start=1):
                        stage_num = str(i)
                        if stage_num in substages:
                            for sub in substages[stage_num].values():
                                date = extract_date_from_string(sub)
                                deadlines.append(date)
                        else:
                            date = extract_date_from_string(stage_value)
                            deadlines.append(date)
                    user_task = await db_repo.get_user_task(user.id)
                    if user_task:
                        user_task.deadlines = deadlines
                        user_task.current_deadline = deadlines[0] if deadlines else None
                        user_task.current_step = 0
                        await db_repo.update_user_task(user_task)
                    else:
                        user_task = UserTask(
                            id=user.id,
                            current_step=0,
                            deadlines=deadlines,
                            current_deadline=deadlines[0]
                        )
                        await db_repo.create_user_task(user_task)
                    for i, (stage_key, stage_value) in enumerate(user.stages_plan.items(), start=1):
                        stage_num = str(i)
                        text += (f"<b>{stage_key}</b> - {stage_value}\n\n")
                        if stage_num in user.substages_plan:
                            text += ("<b>Шаги этого этапа:</b>\n\n")
                            for sub_name, sub_value in user.substages_plan[stage_num].items():
                                text += (f"      {sub_name} - {sub_value}\n\n")
                    text += reply["motivation"]
                    await message.answer(text)
                    await state.clear()
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
        await message.answer("Произошла ошибка при написании плана, попробуйте еще раз немного позже.\nЕсли ошибка сохраняется и перезапуск бота не помогает - обратитесь в поддержку")
