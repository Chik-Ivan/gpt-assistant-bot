import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.core import db
from create_bot import bot
from database.models import User, UserTask
from typing import Optional
from keyboards.all_inline_keyboards import get_continue_create_kb, week_tasks_keyboard, support_kb, stop_question_kb
from gpt import gpt, end_plan_prompt, end_task_prompt
from utils.all_utils import extract_date_from_string


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
            "Кажется, сейчас мы обсуждаем детали твоего плана, хочешь прекратить это?",
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


@current_plan_router.message(F.text=="🗒️ Текущий план")
async def get_current_plan(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        
        if not user.goal:
            await message.answer("В данный момент у вас нет созданного плана. Воспользуйтесь кнопкой \"📋 Создать новый план\", чтобы создать его!")
            return
            
        db_repo = await db.get_repository()
        user_task = await db_repo.get_user_task(user.id)
        
        if not user_task or not user_task.deadlines:
            await message.answer("Кажется возникли какие-то неполадки или у вас отсутствует план.\n"
                               "Попробуйте создать новый план.")
            return
        
        text = ["<b>Текущий план выглядит так:</b>\n\n"]
        text.append(f"<b>🎯 Конечная цель:</b> {user.goal}\n\n")
        
        deadlines = user_task.deadlines
        current_step = user_task.current_step
        deadline_idx = 0 
        
        total_tasks = 0
        completed_tasks = 0
        
        for stage_num, (stage_key, stage_value) in enumerate(user.stages_plan.items(), start=1):
            stage_desc = stage_value.split(" - ")[0]
            stage_str_num = str(stage_num)
            
            substages = []
            if stage_str_num in user.substages_plan:
                for sub_name, sub_value in user.substages_plan[stage_str_num].items():
                    sub_desc = sub_value.split(" - ")[0]
                    if deadline_idx < len(deadlines):
                        deadline = deadlines[deadline_idx]
                        is_current = deadline_idx == current_step
                        is_completed = deadline_idx < current_step
                        
                        substages.append({
                            'name': sub_name,
                            'desc': sub_desc,
                            'deadline': deadline,
                            'is_current': is_current,
                            'is_completed': is_completed,
                            'index': deadline_idx
                        })
                        
                        total_tasks += 1
                        if is_completed:
                            completed_tasks += 1
                            
                        deadline_idx += 1
            
            stage_deadline = None
            if stage_str_num in user.substages_plan and substages:
                stage_deadline = substages[-1]['deadline']
                stage_is_current = any(sub['is_current'] for sub in substages)
                stage_is_completed = all(sub['is_completed'] for sub in substages)
            elif deadline_idx < len(deadlines):
                stage_deadline = deadlines[deadline_idx]
                stage_is_current = deadline_idx == current_step
                stage_is_completed = deadline_idx < current_step
                
                total_tasks += 1
                if stage_is_completed:
                    completed_tasks += 1
                
                deadline_idx += 1
            
            if stage_is_current:
                status = "🟢"
            elif stage_is_completed:
                status = "✅"
            else:
                status = "⚪"
            
            deadline_str = f" (до {stage_deadline.strftime('%d.%m.%Y')})" if stage_deadline else ""
            text.append(f"{status} <b>{stage_key}</b> - {stage_desc}{deadline_str}\n")
            
            if substages:
                text.append("<i>Шаги этого этапа:</i>\n")
                for sub in substages:
                    sub_status = "🟢" if sub['is_current'] else "✅" if sub['is_completed'] else "⚪"
                    deadline_str = f" (до {sub['deadline'].strftime('%d.%m.%Y')})" if sub['deadline'] else ""
                    text.append(f"  {sub_status} {sub['name']} - {sub['desc']}{deadline_str}\n")
            
            text.append("\n")

        text.append("\nТы на правильном пути! Продолжай в том же духе! 💪")
        
        await message.answer("".join(text))


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
        total_steps = len(user_task.deadlines)
        normalized_step = round((user_task.current_step / total_steps) * 18)
        normalized_step = min(max(normalized_step, 0), 18)
        text = ("<b>Статус плана:</b>\n\n📊 <b>Прогресс:</b>\n" +
                "◼︎" * (normalized_step) +
                "░" * (18 - normalized_step) + 
                f"  <b>{int((user_task.current_step) / total_steps * 100)} %</b>\n"
                f"<b>✅ Этапы {user_task.current_step}/{total_steps}</b>\n"
                f"🔥 <b>Баллы: *не сказали от чего расчитываются*</b>")
        await message.answer(text)
        

async def get_current_stage_info(user_task: UserTask, user: User) -> str:
    current_step = user_task.current_step
    deadlines = user_task.deadlines
    
    if not deadlines:
        return "Нет активных задач или дедлайнов."
    
    all_tasks = []
    deadline_idx = 0
    
    for stage_num, (stage_key, stage_val) in enumerate(user.stages_plan.items(), start=1):
        substage_key = str(stage_num)
        
        if substage_key in user.substages_plan:
            for sub_key, sub_val in user.substages_plan[substage_key].items():
                if deadline_idx >= len(deadlines):
                    break
                desc = sub_val.split(" - ")[0].strip()
                all_tasks.append({
                    'type': 'substage',
                    'stage_num': stage_num,
                    'stage_name': stage_key,
                    'stage_desc': stage_val.split(" - ")[0].strip(),
                    'desc': desc,
                    'deadline': deadlines[deadline_idx]
                })
                deadline_idx += 1
        else:
            if deadline_idx >= len(deadlines):
                break
            desc = stage_val.split(" - ")[0].strip()
            all_tasks.append({
                'type': 'stage',
                'stage_num': stage_num,
                'stage_name': stage_key,
                'stage_desc': desc,
                'desc': desc,
                'deadline': deadlines[deadline_idx]
            })
            deadline_idx += 1
    
    if current_step >= len(all_tasks):
        current_step = len(all_tasks) - 1
    
    current_task = all_tasks[current_step]
    current_stage_num = current_task['stage_num']
    
    text = [
        f"На данный момент вы на {current_stage_num} этапе плана из {len(user.stages_plan)}!\n",
        f"Текущий дедлайн: {current_task['deadline'].strftime('%d.%m.%Y')}\n\n",
        f"🔹 {current_task['stage_name']}: {current_task['stage_desc']}\n\n"
    ]
    
    stage_tasks = [t for t in all_tasks if t['stage_num'] == current_stage_num]
    
    if len(stage_tasks) > 1 or (len(stage_tasks) == 1 and stage_tasks[0]['type'] == 'substage'):
        text.append("<b>Подэтапы:</b>\n")
        for task in stage_tasks:
            text.append(f"• {task['desc']} — до {task['deadline'].strftime('%d.%m.%Y')}\n")
    else:
        text.append(f"• {current_task['desc']} — до {current_task['deadline'].strftime('%d.%m.%Y')}\n")
    
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
        
        text = await get_current_stage_info(user_task, user)
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
    
    text = await get_current_stage_info(user_task, user)
    
    question_dialog, reply, status_code = gpt.ask_question_gpt(question_dialog=user.question_dialog, user_input=None, plan_part=text)
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
        text = gpt.create_reminder(end_plan_prompt)
        await call.message.answer(text)
        return
    
    base_deadline = deadlines[current_step]
    delta = base_deadline - today


    adjusted = deadlines[:current_step + 1] + [
        d - delta + timedelta(days=1) for d in deadlines[current_step + 1:]
    ]
    user_task.deadlines = adjusted
    user_task.current_step += 1
    user_task.current_deadline = user_task.deadlines[user_task.current_step]
    await db_repo.update_user_task(user_task)   
    text = gpt.create_reminder(end_task_prompt)
    await call.message.answer(text) 


@current_plan_router.message(AskQuestion.ask_question)
async def ask_question_in_dialog(message: Message, state: FSMContext):
    db_repo = await db.get_repository()
    user = await db_repo.get_user(message.from_user.id)
    question_dialog, reply, status_code = gpt.ask_question_gpt(question_dialog=user.question_dialog, user_input=message.text, plan_part=None)
    if status_code == 1:
        await state.clear()
        await message.answer(reply)
        user.question_dialog = None
        await db_repo.update_user(user)
    elif status_code == 0:
        await message.answer(reply)
        user.question_dialog = question_dialog
        await db_repo.update_user(user)