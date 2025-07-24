# -*- coding: utf-8 -*-
import sys
import logging
import os
import re
import random
import datetime
import openai
from aiohttp import web
from aiogram.dispatcher.webhook import get_new_configured_app
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
from aiogram.utils.executor import start_webhook

from config import BOT_TOKEN, OPENAI_API_KEY
from keyboards import support_button
from database import (
    create_pool,
    upsert_user,
    update_goal_and_plan,
    get_goal_and_plan,
    check_access,
    create_progress_stage,
    check_last_progress,
    mark_progress_completed,
    create_next_stage,
    get_all_users,
)

# ==============================
# 🔗 Настройки Webhook и порта
# ==============================
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например: https://gpt-assistant-bot-v.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

# ==============================
# Логирование
# ==============================
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==============================
# Инициализация бота и GPT
# ==============================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ==============================
# Команды
# ==============================
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу с помощником"),
        BotCommand(command="goal", description="Показать мою цель"),
        BotCommand(command="plan", description="Показать мой план действий"),
        BotCommand(command="check", description="Проверить выполнение плана"),
        BotCommand(command="support", description="Написать в поддержку"),
    ]
    await bot.set_my_commands(commands)

# ==============================
# Системные переменные
# ==============================
dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
pool = None

# ==============================
# GPT-промт
# ==============================
system_prompt = (
    "Ты — личный ассистент-кондитера. Твоя задача — помочь пользователю определить и сформулировать свою цель по доходу, выявить сложности и ресурсы, и составить чёткий пошаговый план.\n\n"
    "Действуй по следующей логике:\n"
    "1. Выясни, кто перед тобой (новичок, профи, ученик и т.д.)\n"
    "2. Узнай, чего он хочет достичь (в деньгах, уровне, статусе)\n"
    "3. Выяви барьеры и страхи, которые мешают двигаться\n"
    "4. Спроси, сколько времени в неделю он может уделять\n"
    "5. Уточни желаемый срок достижения цели (в неделях или месяцах)\n\n"
    "После этого:\n"
    "- Чётко сформулируй его ЦЕЛЬ\n"
    "- Разбей путь на недели\n"
    "- В каждой неделе запланируй 3 действия: Контент, Продукт, Продажи\n\n"
    "Важно:\n"
    "- Задавай по 1 вопросу за раз\n"
    "- Не спеши, сначала собери информацию\n"
    "- После плана скажи: «Я буду присылать тебе каждую неделю план. Не сливайся»\n\n"
    "Первое сообщение должно быть вдохновляющим: поприветствуй, объясни свою роль, предложи начать.\n"
    "**После слов “Начнём?” дождись ответа пользователя, прежде чем задать следующий вопрос.**\n\n"
    "Говори на русском, дружелюбно, уверенно. Не отпускай пользователя. Веди его до конца."
)

# ==============================
# Утилиты
# ==============================
def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""

# ==============================
# GPT логика
# ==============================
async def chat_with_gpt(user_id: int, user_input: str) -> str:
    if user_id not in dialogues:
        dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    dialogues[user_id].append({"role": "user", "content": user_input})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o", messages=dialogues[user_id], temperature=0.7
        )
        gpt_reply = response["choices"][0]["message"]["content"]
        dialogues[user_id].append({"role": "assistant", "content": gpt_reply})

        if "Цель:" in gpt_reply and "План действий" in gpt_reply:
            goal = extract_between(gpt_reply, "Цель:", "План действий").strip()
            plan = gpt_reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)

            today = datetime.datetime.now()
            deadline = today + datetime.timedelta(days=7)
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline.strftime("%Y-%m-%d %H:%M:%S"))

        return gpt_reply
    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"

# ==============================
# Хэндлеры команд
# ==============================
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    await upsert_user(pool, user_id, username, first_name)

    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа. Обратитесь в поддержку.", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    response = await chat_with_gpt(user_id, "Задай мне вопросы, чтобы определить цель.")
    await message.reply(response)

@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Твоя цель:\n\n{goal}" if goal else "Цель ещё не сохранена.")

@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План действий:\n\n{plan}" if plan else "План ещё не составлен.")

@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Нужна помощь? Напиши в поддержку:", reply_markup=support_button)

@dp.message_handler(commands=["check"])
async def check_progress_handler(message: Message):
    user_id = message.from_user.id
    progress = await check_last_progress(pool, user_id)
    if not progress:
        await message.reply("У тебя ещё нет начатого плана.")
        return
    stage, completed, checked = progress["stage"], progress["completed"], progress["checked"]
    if completed:
        await message.reply("✅ Ты уже завершил последний этап. Молодец!")
    elif not checked:
        await message.reply(f"Ты выполнил задания по этапу {stage}? Напиши: да / нет")
        waiting_for_days[user_id] = False
        waiting_for_completion[user_id] = stage

# ==============================
# Напоминания (GPT-3.5 + fallback)
# ==============================
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели!",
    "📅 Настало время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

async def generate_reminder_message():
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Создай короткое мотивирующее напоминание."}],
            max_tokens=50,
            temperature=0.8,
        )
        return response.choices[0].message["content"].strip()
    except:
        return random.choice(REMINDER_TEXTS)

async def send_reminders():
    users = await get_all_users(pool)
    for user in users:
        try:
            await bot.send_message(user["user_id"], await generate_reminder_message())
        except BotBlocked:
            logging.warning(f"Пользователь {user['user_id']} заблокировал бота")

# ==============================
# Webhook и планировщик
# ==============================
async def on_startup_webhook(dp):
    global pool
    pool = await create_pool()
    await bot.set_webhook(WEBHOOK_URL)
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))  # каждый день в 18:00
    scheduler.start()
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown_webhook(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    # Запускаем aiohttp сервер с aiogram
    app = get_new_configured_app(dispatcher=dp, path=WEBHOOK_PATH)

    async def on_startup_webhook(app):
        global pool
        pool = await create_pool()
        await bot.set_webhook(WEBHOOK_URL)
        await set_commands(bot)
        logging.info(f"Webhook установлен: {WEBHOOK_URL}")

    async def on_shutdown_webhook(app):
        logging.warning("Удаление webhook...")
        await bot.delete_webhook()

    app.on_startup.append(on_startup_webhook)
    app.on_shutdown.append(on_shutdown_webhook)

    # Health-check для Render (убираем 404)
    async def health_check(request):
        return web.Response(text="OK", status=200)

    app.router.add_get("/", health_check)

    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)