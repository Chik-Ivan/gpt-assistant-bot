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
from database.models import User, UserTask
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

    async def send_text(text: str, reply_markup=None):
        if isinstance(message, CallbackQuery):
            await message.message.answer(text, reply_markup=reply_markup)
        else:
            await message.answer(text, reply_markup=reply_markup)

    if cur_state is not None and cur_state != AskQuestion.ask_question:
        await send_text(
            "В данный момент я пытаюсь заполнить вашу анкету для нового плана, "
            "вы можете согласиться на потерю данных и начать пользоваться остальными командами без ограничений.",
            reply_markup=get_continue_create_kb()
        )
        return None
    elif cur_state == AskQuestion.ask_question:
        await send_text(
            "Кажется, сейчас мы обсуждаем детали твоего плана на неделю, хочешь прекратить это?",
            reply_markup=stop_question_kb()
        )
        return None
    
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
    await call.answer()
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
        goal = user.goal
        if not goal:
            await message.answer("В данный момент у вас нет созданного плана. Воспользуйтесь кнопкой \"📋 Создать новый план\", чтобы создать его!")
            return
        db_repo = await db.get_repository()
        user_task = await db_repo.get_user_task(user.id)
        if not user_task.deadlines:
            await message.answer("Кажется возникли какие-то неполадки или у вас отсутсвует план.\n"
                                 "Попробуйте создать новый план.")
            return
        
        text = ["Текущий план выглядит так:\n"]
        for i, (stage_key, stage_value) in enumerate(user.stages_plan.items(), start=1):
                        stage_num = str(i)
                        text.append(f"<b>{stage_key}</b> - {stage_value}\n\n")
                        if stage_num in user.substages_plan:
                            text.append("<b>Подэтапы этого эпата:</b>\n\n")
                            for sub_name, sub_value in user.substages_plan[stage_num].items():
                                text.append(f"      {sub_name} - {sub_value}\n\n")
        text.append("Продолжай работать и точно достигнешь всех своих целей!")
        text = "".join(text)
        await message.answer(text)


@current_plan_router.message(F.text=="⌛ Статус плана")
async def plan_status(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        goal = user.goal
        if not goal:
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
                f"  <b>{int((user_task.current_step) / len(user_task.deadlines) * 100)} %</b>\n"
                f"<b>✅ Этапы {user_task.current_step}/{len(user_task.deadlines)}</b>\n"
                f"🔥 <b>Баллы: *не сказали от чего расчитываются*</b>")
        await message.answer(text)
        

def get_current_stage_info(user_task: UserTask, user: User) -> str:
    current_step = user_task.current_step

    deadline_map = []
    for i, (stage_key, stage_val) in enumerate(user.stages_plan.items(), start=1):
        stage_tasks = []
        substage_key = str(i)
        if substage_key in user.substages_plan:
            for sub_desc in user.substages_plan[substage_key].values():
                desc, date_str = sub_desc.rsplit(" - ", 1)
                deadline = datetime.strptime(date_str.strip(), "%d.%m.%Y")
                stage_tasks.append((desc, deadline))
        else:
            desc, date_str = stage_val.rsplit(" - ", 1)
            deadline = datetime.strptime(date_str.strip(), "%d.%m.%Y")
            stage_tasks.append((desc, deadline))
        deadline_map.append((i, stage_key, stage_val, stage_tasks))

    flat_deadlines = []
    for stage in deadline_map:
        stage_num, stage_name, stage_val, tasks = stage
        for task in tasks:
            flat_deadlines.append((stage_num, stage_name, stage_val, task))

    current_stage_num = flat_deadlines[current_step][0]
    total_stage = len(user.stages_plan)

    text = [
        f"На данный момент вы на {current_stage_num} этапе плана из {total_stage}!\n",
        f"Ваши задачи на этом этапе и их дедлайны:\n\n"
    ]

    for stage_num, stage_name, stage_val, stage_tasks in deadline_map:
        if stage_num == current_stage_num:
            text.append(f"🔹 {stage_name}: {stage_val}\n\n<b>Подэтапы:</b>\n")
            substage_key = str(stage_num)

            if substage_key in user.substages_plan:
                for desc, dl in stage_tasks:
                    text.append(f"• {desc} — до {dl.strftime('%d.%m.%Y')}\n")
            else:
                desc, date_str = stage_val.rsplit(" - ", 1)
                dl = datetime.strptime(date_str.strip(), "%d.%m.%Y")
                text.append(f"• Подэтапов нет – только основной этап:\n")
                text.append(f"  {desc} — до {dl.strftime('%d.%m.%Y')}\n")
            break

    return "".join(text)


@current_plan_router.message(F.text=="❗ Задание этапа")
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
        
        text = get_current_stage_info(user_task, user)
        await message.answer(text, reply_markup=week_tasks_keyboard())


@current_plan_router.callback_query(F.data=="ask_question")
async def ask_question(call: CallbackQuery, state: FSMContext):
    user = await check_plan(call.from_user.id, call, state)
    await call.answer()
    if not user:
        return
    await call.answer()
    await state.set_state(AskQuestion.ask_question)
    db_repo = await db.get_repository()
    user_task = await db_repo.get_user_task(call.from_user.id)
    tasks = []
    for week in user.plan.keys():
        for type, task in user.plan[week].items():
            tasks.append(f"{type}: {task}")
    text = get_current_stage_info(user_task, user)
    
    question_dialog, reply, status_code = await gpt.ask_question_gpt(question_dialog=user.question_dialog, user_input=None, plan_part=text)
    await call.message.answer(reply)
    user.question_dialog = question_dialog
    await db_repo.update_user(user)


@current_plan_router.callback_query(F.data=="mark_completed")
async def mark_completed(call: CallbackQuery, state: FSMContext):
    user = await check_plan(call.from_user.id, call, state)
    await call.answer()
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

    if current_step == len(deadlines) - 1:
        await call.message.answer("Это был последний этап и ты справился ос своим планом! Поздравляю!")
        return
    
    base_deadline = deadlines[current_step]
    delta = base_deadline - today


    adjusted = deadlines[:current_step + 1] + [
        d - delta + timedelta(days=1) for d in deadlines[current_step + 1:]
    ]
    user_task.deadlines = adjusted
    user_task.current_step += 1
    await db_repo.update_user_task(user_task)   
    await call.message.answer("Дедлайны передвинуты") 


@current_plan_router.message(AskQuestion.ask_question)
async def ask_question_in_dialog(message: Message, state: FSMContext):
    db_repo = await db.get_repository()
    user = await db_repo.get_user(message.from_user.id)
    question_dialog, reply, status_code = await gpt.ask_question_gpt(question_dialog=user.question_dialog, user_input=message.text, plan_part=None)
    if status_code == 1:
        await state.clear()
        await message.answer(reply)
        user.question_dialog = None
        await db_repo.update_user(user)
    elif status_code == 0:
        await message.answer(reply)
        user.question_dialog = question_dialog
        await db_repo.update_user(user)