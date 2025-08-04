import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from database.core import db
from create_bot import bot
from database.models import User
from typing import Optional
from keyboards.all_inline_keyboards import get_continue_create_kb


current_plan_router = Router()


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
