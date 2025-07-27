# -*- coding: utf-8 -*-
import sys
import logging
import openai
import os
import random
import datetime
import re
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.utils.executor import start_webhook
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web

from config import BOT_TOKEN, OPENAI_API_KEY
from database import (
    create_pool,
    upsert_user,
    update_goal_and_plan,
    get_goal_and_plan,
    check_access,
    create_progress_stage,
    mark_progress_completed,
    create_next_stage,
    get_all_users,
    get_progress,
)
from keyboards import support_button
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError

# ✅ Webhook Config
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://gpt-assistant-bot-v.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

# ✅ Logging
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ✅ Aiogram Bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ✅ Commands
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="goal", description="Показать цель"),
        BotCommand(command="plan", description="Показать план"),
        BotCommand(command="progress", description="Прогресс"),
        BotCommand(command="support", description="Техподдержка"),
    ]
    await bot.set_my_commands(commands)

# ✅ Variables
dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
pool = None

# ✅ System Prompt для GPT
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

# ✅ Извлечение дней из текста
def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

# ✅ GPT Диалог
async def chat_with_gpt(user_id: int, user_input: str) -> str:
    if user_id not in dialogues:
        dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    dialogues[user_id].append({"role": "user", "content": user_input})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o", messages=dialogues[user_id], temperature=0.7
        )
        reply = response["choices"][0]["message"]["content"]
        dialogues[user_id].append({"role": "assistant", "content": reply})

        if "Цель:" in reply and "План действий" in reply:
            goal = reply.split("Цель:")[1].split("План действий")[0].strip()
            plan = reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)
            deadline = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline)

        return reply
    except Exception as e:
        return f"Ошибка GPT: {e}"

# ✅ Обработчики команд
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    await upsert_user(pool, user_id, message.from_user.username or "", message.from_user.first_name or "")
    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа.", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    await message.reply(await chat_with_gpt(user_id, "Начни диалог"))

@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Цель:\n{goal}" if goal else "Цель еще не создана.")

@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n{plan}" if plan else "План не найден.")

@dp.message_handler(commands=["progress"])
async def progress_handler(message: Message):
    user_id = message.from_user.id
    data = await get_progress(pool, user_id)

    completed = data['completed']
    total = data['total']
    points = data['points']
    next_deadline = data['next_deadline']

    # Рассчитываем прогресс
    if total > 0:
        progress_percent = int((completed / total) * 100)
        bars = int((completed / total) * 10)  # 10 сегментов
        progress_bar = "█" * bars + "░" * (10 - bars)
    else:
        progress_percent = 0
        progress_bar = "░" * 10

    text = (
        f"📊 Прогресс:\n"
        f"{progress_bar} {progress_percent}%\n"
        f"✅ Этапы: {completed}/{total}\n"
        f"🔥 Баллы: {points}\n"
    )

    if next_deadline:
        text += f"📅 Следующий дедлайн: {next_deadline.strftime('%d %B')}\n"

    await message.reply(text)

@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Нужна помощь? 👇", reply_markup=support_button)

# ✅ Общий обработчик
@dp.message_handler()
async def handle_chat(message: Message):
    user_id = message.from_user.id
    text = message.text
    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа.", reply_markup=support_button)
        return

    if waiting_for_days.get(user_id):
        days = extract_days(text)
        deadline = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        await create_progress_stage(pool, user_id, stage=1, deadline=deadline)
        await message.reply(f"✅ План зафиксирован на {days} дней.")
        waiting_for_days[user_id] = False
        return

    if user_id in waiting_for_completion:
        if "да" in text.lower():
            stage = waiting_for_completion[user_id]
            await mark_progress_completed(pool, user_id, stage)
            await create_next_stage(pool, user_id, stage + 1)
            await message.reply("🔥 Отлично! Продолжаем!")
        else:
            await message.reply("Понимаю. Продолжаем!")
        del waiting_for_completion[user_id]
        return

    response = await chat_with_gpt(user_id, text)
    await message.reply(response)
    if any(word in response.lower() for word in ["срок", "график", "дедлайн"]):
        waiting_for_days[user_id] = True

# ✅ Запасные тексты напоминаний
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели, ты справишься!",
    "📅 Настало время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

# ✅ Генерация напоминания через GPT-3.5
async def generate_reminder_message():
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты дружелюбный мотиватор."},
                {"role": "user", "content": "Создай короткое мотивирующее напоминание для проверки плана. Максимум одно предложение."}
            ],
            max_tokens=50,
            temperature=0.8,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.warning(f"Ошибка GPT: {e}. Использую заготовленный текст.")
        return random.choice(REMINDER_TEXTS)

# ✅ Основная функция отправки напоминаний
async def send_reminders():
    try:
        users = await get_all_users(pool)  # список пользователей
        for user in users:
            try:
                # 50% шанс использовать GPT
                if random.random() > 0.5:
                    text = await generate_reminder_message()
                else:
                    text = random.choice(REMINDER_TEXTS)

                await bot.send_message(user["id"], text)
            except BotBlocked:
                logging.warning(f"Пользователь {user['id']} заблокировал бота")
            except Exception as e:
                logging.error(f"Ошибка при отправке пользователю {user['id']}: {e}")
    except Exception as e:
        logging.error(f"Ошибка при получении пользователей: {e}")

# ✅ ON STARTUP
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, "interval", minutes=1)
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

# ✅ ON SHUTDOWN
async def on_shutdown(dp):
    try:
        await bot.delete_webhook()
        session = await bot.get_session()
        await session.close()
        logging.warning("Webhook удалён и сессия закрыта.")
    except Exception as e:
        logging.error(f"Ошибка при закрытии: {e}")

# ✅ Health Check
async def health_check(request):
    return web.Response(text="OK")

# ✅ /test_reminder
@dp.message_handler(commands=["test_reminder"])
async def test_reminder(message: Message):
    await send_reminders()
    await message.reply("✅ Напоминания отправлены всем пользователям!")

# ✅ RUN SERVER
if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", health_check)
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )