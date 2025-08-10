import logging
from datetime import datetime, timedelta
from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery
from database.core import db
from database.models import UserTask
from keyboards.all_inline_keyboards import remind_about_deadline_kb
from gpt import gpt, end_plan_prompt, end_task_prompt, comfort_prompt

logger = logging.getLogger(__name__)
reminder_router = Router()


async def send_reminders(bot: Bot):
    try:
        db_repo = await db.get_repository()
        users_to_remind_create_plan = await db_repo.get_users_for_reminder_create_plan()
        users_to_remind_deadline = await db_repo.get_users_to_remind_deadline()
        logger.info(f"users_to_remind_create_plan: {users_to_remind_create_plan}")
        logger.info(f"users_to_remind_deadline: {users_to_remind_deadline}")
        for user in users_to_remind_create_plan:
            try:
                await bot.send_message(
                    chat_id=user['id'],
                    text="⏰ Хэй! Я вижу, что ты так и не создал себе персональный план, так может пора это сделать прямо сейчас?:)"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить напоминание пользователю {user['id']}: {e}")

        for user in users_to_remind_deadline:
            try:
                await bot.send_message(
                    chat_id=user['id'],
                    text="⏰ Приветик! Вижу у тебя сегодня дедлайн по задаче, ты справился и мы можем переходить к следующей или мне немного сдвинуть дедлайны?",
                    reply_markup=remind_about_deadline_kb()
                )
            except Exception as e:
                logger.error(f"Не удалось отправить напоминание пользователю {user['id']}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка в задаче отправки напоминаний: {e}")

async def check_deadlines_send_reminders(bot: Bot):
    db_repo = await db.get_repository()
    users_to_remind_deadline = await db_repo.get_users_to_remind_deadline()
    for user in users_to_remind_deadline:
            try:
                await bot.send_message(
                    chat_id=user['id'],
                    text=("⏰ Кажется, что ты так и не определился с тем, выполнена ли твоя цель, тогда я передвину дедлайны.\n\n"
                          "Если захочешь закончить этап досрочно, то сможешь сделать это по кнопке в меню с информацией об этапе.")
                )
                user_task = await db_repo.get_user_task(user['id'])
                await postponement_deadlines(user_task)
            except Exception as e:
                logger.error(f"Не удалось отправить напоминание пользователю {user['id']}: {e}")


@reminder_router.callback_query(F.data=="task_completed_on_time")
async def task_complited_on_time(call: CallbackQuery):
    await call.answer()
    db_repo = await db.get_repository()
    user_task = await db_repo.get_user_task(call.from_user.id)
    current_deadline = user_task.current_deadline.date()
    today = datetime.now().date()
    if current_deadline <= today:
        user_task.current_step += 1
        if user_task.current_step == len(user_task.deadlines):
            text = gpt.create_reminder(end_plan_prompt)
            await call.message.answer(text)
            return
        text = gpt.create_reminder(end_task_prompt)
        await call.message.answer(text=text)
        user_task.current_deadline = user_task.deadlines[user_task.current_step]
        await db_repo.update_user_task(user_task)
    else:
        await call.message.answer(text="Кажется, что ты уже отметил задачу выполненной:)\n\n")


@reminder_router.callback_query(F.data=="postponement_deadlines")
async def postponement_deadlines_handler(call: CallbackQuery):
    await call.answer()
    db_repo = await db.get_repository()
    user_task = await db_repo.get_user_task(call.from_user.id)
    current_deadline = user_task.current_deadline.date()
    today = datetime.now().date()
    if current_deadline <= today:
        text = gpt.create_reminder(comfort_prompt)
        await call.message.answer(text=text)
        await postponement_deadlines(user_task)
    else:
        await call.message.answer(text="Кажется, что твой дедлайн и так не сегодня.")

async def postponement_deadlines(user_task: UserTask):
    db_repo = await db.get_repository()
    adjusted = user_task.deadlines[:user_task.current_step] + [
        d + timedelta(days=2) for d in user_task.deadlines[user_task.current_step:]
    ]
    
    user_task.deadlines = adjusted
    user_task.current_deadline = user_task.deadlines[user_task.current_step]
    await db_repo.update_user_task(user_task)
