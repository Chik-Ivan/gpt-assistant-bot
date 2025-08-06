import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from database.core import db
from create_bot import bot
from database.models import User
from typing import Optional
from keyboards.all_inline_keyboards import get_continue_create_kb, week_tasks_keyboard, support_kb, stop_question_kb
from utils.all_utils import extract_number
from gpt import gpt 


current_plan_router = Router()


class AskQuestion(StatesGroup):
    ask_question = State()


async def check_plan(user_id: int, message: Message|CallbackQuery, state: FSMContext) -> Optional[User]:
    cur_state = await state.get_state()

    logging.info(f"CUR_STATE: {cur_state}")

    if cur_state is not None and cur_state != AskQuestion.ask_question:
        await message.answer("В данный момент я пытаюсь заполнить вашу анкету для нового плана, " 
                            "вы можете согласиться на потерю данных и начать пользоваться остальными командами без ограничений.",
                             reply_markup=get_continue_create_kb())
        return None
    elif cur_state == AskQuestion.ask_question:
        await message.answer("Кажется, сейчас мы обсуждаем детали твоего плана на неделю, хочешь прекратить это?", reply_markup=stop_question_kb())
        return
    
    db_repo = await db.get_repository()
    user = await db_repo.get_user(user_id)

    if user is None:
        logging.error("Не найден пользователь при попытке создания нового плана")
        await message.answer("Ошибка! Обратитесь к администратору.")
        return None
    else:
        logging.info(f"Пользователь получен, id: {user.id}")
    
    return user


@current_plan_router.callback_query(F.data=="stop_question")
async def stop_question(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Хорошо! Помни, можешь обращаться ко мне в любое время:)")
    db_repo = await db.get_repository()
    user = await db_repo.get_user(call.from_user.id)
    user.question_dialog = None
    await db_repo.update_user(user)

@current_plan_router.message(F.text=="🎯 Текущая цель")
async def get_current_goal(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        await message.answer(f"Ваша текущая цель: {user.goal}" if user.goal else "В данный момент цель не задана. Попробуйте создать новый план")


@current_plan_router.message(F.text=="🗒️ Текущий план")
async def get_cuurent_plan(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        plan = user.plan
        if not plan:
            await message.answer("В данный момент у вас нет созданного плана. Воспользуйтесь кнопкой \"📋 Создать новый план\", чтобы создать его!")
            return
        db_repo = await db.get_repository()
        user_task = await db_repo.get_user_task(user.id)
        if not user_task.deadlines:
            await message.answer("Кажется возникли какие-то неполадки или у вас отсутсвует план.\n"
                                 "Попробуйте создать новый план.")
            return
        
        text = ["Текущий план выглядит так:\n"]
        for index_week, (week, tasks) in enumerate(plan.items()):
            text.append(f"{week}:\n")
            for index_task, (task_name, task_value) in enumerate(tasks.items()):
                text.append(f"{task_name}: {task_value} до {user_task.deadlines[index_week//3 + index_task].strftime('%d.%m.%Y')}\n")
            text.append("\n")
        text.append("Продолжай работать и точно достигнешь всех своих целей!")
        text = "".join(text[:-2])
        await message.answer(text)


@current_plan_router.message(F.text=="⌛ Статус плана")
async def plan_status(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        plan = user.plan
        if not plan:
            await message.answer("В данный момент у вас нет созданного плана. Воспользуйтесь кнопкой \"📋 Создать новый план\", чтобы создать его!")
            return
        db_repo = await db.get_repository()
        user_task = await db_repo.get_user_task(user.id)
        if not user_task.deadlines:
            await message.answer("Кажется возникли какие-то неполадки или у вас отсутсвует план.\n"
                                 "Попробуйте создать новый план.")
            return
        text = ("<b>Статус плана:</b>\n\n📊 <b>Прогресс:</b>\n" +
                "⏹︎" * (user_task.current_step) +
                "░" * (len(user_task.deadlines) - user_task.current_step) + 
                f"<b>{int((user_task.current_step) / len(user_task.deadlines) * 100)} %</b>\n"
                f"<b>✅ Этапы {user_task.current_step}/{len(user_task.deadlines)}</b>\n"
                f"🔥 <b>Баллы: *не сказали от чего расчитываются*</b>")
        await message.answer(text)
        

@current_plan_router.message(F.text=="❗ Задание на неделю")
async def current_status(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        if not user.goal:
            await message.answer("Кажется у вас еще нет созданного плана, для начала создайте план:)")
            return
        db_repo = await db.get_repository()
        user_task = await db_repo.get_user_task(user.id)
        if not user_task.deadlines:
            await message.answer("Кажется возникли какие-то неполадки или у вас отсутсвует план.\n"
                                 "Попробуйте создать новый план.")
            return
        tasks = []
        for week in user.plan.keys():
            for type, task in user.plan[week].items():
                tasks.append(f"{type}: {task}")
        text = (f"На данный момент вы на {user_task.current_step//3 + 1} неделе плана плана из {len(user_task.deadlines) // 3}!\n"
                f"Ваши задачи на эту неделю и их дедлайны:\n\n"
                f"{tasks[user_task.current_step//3]} до {user_task.deadlines[user_task.current_step//3].strftime('%d.%m.%Y')}\n\n"
                f"{tasks[user_task.current_step//3 + 1]} до {user_task.deadlines[user_task.current_step//3 + 1].strftime('%d.%m.%Y')}\n\n"
                f"{tasks[user_task.current_step//3 + 2]} до {user_task.deadlines[user_task.current_step//3 + 2].strftime('%d.%m.%Y')}\n\n"
                )
        await message.answer(text, reply_markup=week_tasks_keyboard())


@current_plan_router.callback_query(F.data=="ask_question")
async def ask_question(call: CallbackQuery, state: FSMContext):
    user = await check_plan(call.from_user.id, call, state)
    if not user:
        return
    await state.set_state(AskQuestion.ask_question)
    db_repo = await db.get_repository()
    user_task = await db_repo.get_user_task(call.from_user.id)
    tasks = []
    for week in user.plan.keys():
        for type, task in user.plan[week].items():
            tasks.append(f"{type}: {task}")
    text = (f"Задачи на эту неделю и их дедлайны:\n\n"
            f"{tasks[user_task.current_step//3]} до {user_task.deadlines[user_task.current_step//3].strftime('%d.%m.%Y')}\n\n"
            f"Ваши задачи на эту неделю и их дедлайны:\n\n"
            f"{tasks[user_task.current_step//3 + 1]} до {user_task.deadlines[user_task.current_step//3 + 1].strftime('%d.%m.%Y')}\n\n"
            f"Ваши задачи на эту неделю и их дедлайны:\n\n"
            f"{tasks[user_task.current_step//3 + 2]} до {user_task.deadlines[user_task.current_step//3 + 2].strftime('%d.%m.%Y')}\n\n"
            )
    
    question_dialog, reply, status_code = await gpt.ask_question_gpt(question_dialog=user.question_dialog, plan_part=text)
    await call.message.answer(reply)
    user.question_dialog = question_dialog
    await db_repo.update_user(user)


@current_plan_router.callback_query(F.data=="mark_completed")
async def mark_completed(call: CallbackQuery, state: FSMContext):
    user = await check_plan(call.from_user.id, call, state)
    if not user:
        return
    db_repo = await db.get_repository()
    user_task = await db_repo.get_user_task(call.from_user.id)
    if not user_task:
        await call.message.answer("Кажется у тебя еще нет активного плана:(")
        return
    deadlines = user_task.deadlines
    current_step = user_task.current_step

    today = datetime.now()
    block_index = current_step // 3
    adjust_index = block_index + 2

    if adjust_index >= len(deadlines):
        return deadlines

    base_deadline = deadlines[adjust_index]
    delta = base_deadline - today

    if delta.total_seconds() <= 0:
        return deadlines

    adjusted = deadlines[:adjust_index] + [
        d - delta + timedelta(days=1) for d in deadlines[adjust_index:]
    ]
    user_task.deadlines = adjusted
    user_task.current_step = adjust_index
    await db_repo.update_user_task(user_task)    

# Этот хендлер должен находиться в отдельном .py файле, но я вношу быстрые правки, 
# поэтому если это видит другой программист, то перенеси пж
@current_plan_router.message(F.text=="🆘 поддержка")
async def support(message: Message, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
            return
    text = ("Не стоит злоупотреблять этой возможностью, спамить или оскорблять операторов.\n"
            "Пишите четко и по существу, не разделяя свое сообщение на множество более мелких.\n"
            "Спасибо за понимание!")
    await message.answer(text, reply_markup=support_kb()) 


@current_plan_router.message(AskQuestion.ask_question)
async def ask_question_in_dialog(message: Message, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    db_repo = await db.get_repository()
    question_dialog, reply, status_code = await gpt.ask_question_gpt(question_dialog=user.question_dialog, user_input=message.text)
    if status_code == 1:
        await state.clear()
        await message.answer(reply)
        user.question_dialog = None
        await db_repo.update_user(user)
    elif status_code == 0:
        await message.answer(reply)
        user.question_dialog = question_dialog
        await db_repo.update_user(user)