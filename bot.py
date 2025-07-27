# -*- coding: utf-8 -*-
import sys
import logging
import openai
import os
import random
import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError

# Импорт настроек и функций
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
    get_progress,
    get_all_users,
)

# Настройки Webhook
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 5000))

# Настройка вывода в консоль
sys.stdout.reconfigure(encoding="utf-8")

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Инициализация бота и GPT
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# Команды бота
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="goal", description="Показать мою цель"),
        BotCommand(command="plan", description="Показать мой план"),
        BotCommand(command="check", description="Проверить выполнение"),
        BotCommand(command="progress", description="Посмотреть прогресс"),
        BotCommand(command="support", description="Написать в поддержку"),
    ]
    await bot.set_my_commands(commands)

# Хранение состояния диалога
dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
pool = None

# ✅ Основной промт для GPT
system_prompt = (
    "Ты — личный ассистент-кондитера. Помогаешь пользователю определить цель, выявить проблемы и составить пошаговый план.\n"
    "Собери данные: опыт, цель, барьеры, время на обучение, срок достижения.\n"
    "После сбора сформулируй ЦЕЛЬ и ПЛАН (разбей на недели: Контент, Продукт, Продажи).\n"
    "Задавай вопросы по одному. Начни с приветствия и фразы «Начнём?»"
)

# ✅ Вспомогательная функция для извлечения числа дней
import re
def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""

# ✅ GPT-ответ и сохранение данных
async def chat_with_gpt(user_id: int, user_input: str) -> str:
    if user_id not in dialogues:
        dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    dialogues[user_id].append({"role": "user", "content": user_input})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=dialogues[user_id],
            temperature=0.7
        )
        gpt_reply = response["choices"][0]["message"]["content"]
        dialogues[user_id].append({"role": "assistant", "content": gpt_reply})

        # Сохраняем цель и план
        if "Цель:" in gpt_reply and "План действий" in gpt_reply:
            goal = extract_between(gpt_reply, "Цель:", "План действий").strip()
            plan = gpt_reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)

            # Создаём первую неделю
            deadline = datetime.datetime.now() + datetime.timedelta(days=7)
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline.strftime("%Y-%m-%d %H:%M:%S"))

        return gpt_reply
    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"

# ✅ Обработчик /start
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
    first_response = await chat_with_gpt(user_id, "Начни диалог")
    await message.reply(first_response)

# ✅ Общий обработчик сообщений
@dp.message_handler()
async def handle_chat(message: Message):
    user_id = message.from_user.id
    text = message.text

    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа. Обратитесь в поддержку.", reply_markup=support_button)
        return

    if waiting_for_days.get(user_id):
        days = extract_days(text)
        deadline = datetime.datetime.now() + datetime.timedelta(days=days)
        await create_progress_stage(pool, user_id, stage=1, deadline=deadline.strftime("%Y-%m-%d %H:%M:%S"))
        await message.reply(f"✅ План зафиксирован на {days} дней.")
        waiting_for_days[user_id] = False
        return

    if user_id in waiting_for_completion:
        if "да" in text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
            await message.reply("🔥 Отлично! Продолжаем!")
        else:
            await message.reply("Понимаю. Продолжаем, но постарайся успеть!")
        del waiting_for_completion[user_id]
        return

    response = await chat_with_gpt(user_id, text)
    await message.reply(response)

    if any(word in response.lower() for word in ["срок", "график", "дедлайн"]):
        waiting_for_days[user_id] = True

# ✅ /goal
@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Цель:\n{goal}" if goal else "Цель пока не сохранена.")

# ✅ /plan
@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n{plan}" if plan else "План ещё не составлен.")

# ✅ /progress
@dp.message_handler(commands=["progress"])
async def progress_handler(message: Message):
    user_id = message.from_user.id
    data = await get_progress(pool, user_id)
    progress_text = (
        f"📊 Прогресс:\n"
        f"✅ Выполнено: {data['completed']} из {data['total']} этапов\n"
        f"🔥 Баллы: {data['points']}\n"
    )
    if data["next_deadline"]:
        progress_text += f"📅 Следующий дедлайн: {data['next_deadline'].strftime('%d %B')}\n"
    await message.reply(progress_text)

# ✅ Напоминания
REMINDER_TEXTS = [
    "⏰ Проверь свой план!",
    "🔥 Не забывай про цели!",
    "📅 Как идёт прогресс?"
]

async def send_reminders():
    try:
        users = await get_all_users(pool)
        for user in users:
            text = random.choice(REMINDER_TEXTS)
            await bot.send_message(user["telegram_id"], text)
    except Exception as e:
        logging.error(f"Ошибка напоминаний: {e}")

# ✅ ON STARTUP
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

# ✅ ON SHUTDOWN
async def on_shutdown(dp):
    await bot.delete_webhook()
    await bot.session.close()
    logging.warning("Webhook удалён.")

# ✅ Запуск
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