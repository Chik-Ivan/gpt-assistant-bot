import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from database.core import db
from create_bot import bot
from database.models import User
from typing import Optional
from keyboards.all_inline_keyboards import get_continue_create_kb
from utils.all_utils import extract_number


current_plan_router = Router()


class SetTimeReminder(StatesGroup):
    set_reminder_time = State()


async def check_plan(user_id: int, message: Message, state: FSMContext) -> Optional[User]:
    cur_state = await state.get_state()

    logging.info(f"CUR_STATE: {cur_state}")

    if cur_state is not None:
        await message.answer("В данный момент я пытаюсь заполнить вашу анкету для нового плана, " 
                            "вы можете согласиться на потерю данных и начать пользоваться остальными командами без ограничений.",
                             reply_markup=get_continue_create_kb())
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

@current_plan_router.message(F.text, StateFilter(SetTimeReminder.set_reminder_time))
async def reminder_time_to_db(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):

        new_time = extract_number(message.text)
        if not new_time or not (0 <= new_time <= 23):
            await message.answer("Некорректный ответ!\nПожалуйста, введите одно число от 0 до 23 (0, 12, 23)!")
        db_repo = await db.get_repository()
        cur_task = await db_repo.get_user_task(message.from_user.id)
        if not cur_task:
            await message.answer("Упс.. Кажется произошла ошибка!\n"
                                 "Возможно вы еще не создавали свой персональный план,"
                                 " если это не так, то обратитесь к администратору по кнопке ниже.")
        cur_task.reminder_time = new_time
        await db_repo.update_user_task(cur_task)
        await message.answer(f"Теперь напоминания будут приходить в {new_time}:00 МСК в день дедлайна!")

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

        text = ["Текущий план выглядит так:\n"]
        for week, tasks in plan.items():
            text.append(f"{week}:\n")
            for task_name, task_value in tasks.items():
                text.append(f"{task_name}: {task_value}\n")
            text.append("\n")
        text.append("Продолжать работать и точно достигнешь всех своих целей!")
        text = "".join(text[:-2])
        await message.answer(text)

@current_plan_router.message(F.text=="🕛 Задать удобное время напоминалкам")
async def set_reminder_time(message: Message, state: FSMContext):
    async with ChatActionSender(bot=bot, chat_id=message.chat.id, action="typing"):
        user = await check_plan(message.from_user.id, message, state)
        if not user:
            return
        if not user.goal:
            await message.answer("Кажется у вас еще нет созданного плана, для начала создайте план:)")
            return
        state.set_state(SetTimeReminder.set_reminder_time)
        db_repo = await db.get_repository()
        cur_user_task = await db_repo.get_user_task(message.from_user.id)
        await message.answer("Напишите число от 0 до 23 - удобный час для получения напоминания по Московскому времени\n\n"
                             f"Текущее время -- {cur_user_task.reminder_time}:00 в день дедлайна по текущей задаче")