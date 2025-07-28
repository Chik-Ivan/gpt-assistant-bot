# -*- coding: utf-8 -*-
import sys
import logging
import openai
import os
import random
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, OPENAI_API_KEY, WEBHOOK_HOST
from database import (
    create_pool, upsert_user, check_access, update_goal_and_plan, get_goal_and_plan,
    create_progress_stage, mark_progress_completed, create_next_stage, check_last_progress,
    get_progress, get_users_for_reminder
)
from keyboards import support_button

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

waiting_for_days = dict()
waiting_for_completion = dict()

async def set_commands(bot):
    commands = [
        BotCommand(command="/start", description="Начать"),
        BotCommand(command="/goal", description="Моя цель"),
        BotCommand(command="/plan", description="План действий"),
        BotCommand(command="/check", description="Отметить прогресс"),
        BotCommand(command="/progress", description="Прогресс и баллы"),
        BotCommand(command="/support", description="Техподдержка"),
        BotCommand(command="/test_reminder", description="Тест напоминаний"),
    ]
    await bot.set_my_commands(commands)

async def chat_with_gpt(user_id, text):
    try:
        openai.api_key = OPENAI_API_KEY
        messages = [{"role": "system", "content": "Ты помогаешь пользователю определить цель и план."}]
        messages.append({"role": "user", "content": text})
        resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, max_tokens=200)
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"GPT ошибка: {e}")
        return "⚠️ Ошибка связи с GPT. Попробуй позже."

@dp.message_handler(commands=["start"])
async def cmd_start(message: Message):
    global pool
    user_id = message.from_user.id
    await upsert_user(pool, user_id, message.from_user.username, message.from_user.first_name)
    access = await check_access(pool, user_id)
    if not access:
        await message.answer("🔒 У тебя нет доступа. Обратись в поддержку.", reply_markup=support_button)
        return
    await message.answer("👋 Привет! Напиши свою цель.")

@dp.message_handler(commands=["goal"])
async def cmd_goal(message: Message):
    global pool
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.answer(f"🎯 Цель: {goal}" if goal else "Цель не найдена.")

@dp.message_handler(commands=["plan"])
async def cmd_plan(message: Message):
    global pool
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.answer(f"📝 План: {plan}" if plan else "План не найден.")

@dp.message_handler(commands=["check"])
async def cmd_check(message: Message):
    global pool
    user_id = message.from_user.id
    last = await check_last_progress(pool, user_id)
    if last and not last["completed"]:
        stage = last["stage"]
        waiting_for_completion[user_id] = stage
        await message.answer(f"Ты выполнил этап {stage}? (да/нет)")
    else:
        await message.answer("Нет активных задач.")

@dp.message_handler(commands=["progress"])
async def cmd_progress(message: Message):
    global pool
    user_id = message.from_user.id
    stats = await get_progress(pool, user_id)
    await message.answer(
        f"📊 Выполнено этапов: {stats['completed']} / {stats['total']}"

        f"⭐ Баллы: {stats['points']}"

        f"⏳ Ближайший дедлайн: {stats['next_deadline'] or 'Нет'}"
    )

@dp.message_handler(commands=["support"])
async def cmd_support(message: Message):
    await message.answer("Если возникли вопросы — напиши нам:", reply_markup=support_button)

@dp.message_handler()
async def handle_user_input(message: Message):
    global pool
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id in waiting_for_days:
        try:
            days = int("".join(filter(str.isdigit, text)))
            deadline = datetime.datetime.now() + datetime.timedelta(days=days)
            await create_progress_stage(pool, user_id, 1, deadline.strftime("%Y-%m-%d %H:%M:%S"))
            await message.reply(f"✅ План установлен на {days} дней.")
        except:
            await message.reply("⚠️ Укажи число дней (например, 14).")
        waiting_for_days.pop(user_id, None)
        return

    if user_id in waiting_for_completion:
        if "да" in text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
            await message.reply("🔥 Отлично! Продолжаем!")
        else:
            await message.reply("Понимаю. Продолжай стараться!")
        waiting_for_completion.pop(user_id, None)
        return

    response = await chat_with_gpt(user_id, text)
    await message.reply(response)
    if any(word in response.lower() for word in ["срок", "дедлайн", "дней"]):
        waiting_for_days[user_id] = True

REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели!",
    "📅 Время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

async def generate_reminder_message():
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                { "role": "system", "content": "Ты дружелюбный мотиватор." },
                { "role": "user", "content": "Создай короткое напоминание (одно предложение)." }
            ],
            max_tokens=50, temperature=0.8
        )
        return resp["choices"][0]["message"]["content"].strip()
    except:
        return random.choice(REMINDER_TEXTS)

async def send_reminders():
    try:
        users = await get_users_for_reminder(pool)
        for user in users:
            if random.random() < 0.4:
                text = await generate_reminder_message() if random.random() > 0.5 else random.choice(REMINDER_TEXTS)
                await bot.send_message(user["user_id"], text)
    except Exception as e:
        logging.error(f"Ошибка при отправке напоминаний: {e}")

@dp.message_handler(commands=["test_reminder"])
async def test_reminder(message: Message):
    await send_reminders()
    await message.reply("✅ Напоминания отправлены!")

async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour="10,18"))
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    await bot.delete_webhook()
    await bot.session.close()
    logging.warning("Webhook удалён.")

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )