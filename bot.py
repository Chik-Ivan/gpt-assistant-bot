# -*- coding: utf-8 -*-
import sys
import logging
import os
import re
import random
import datetime
import openai

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError
from aiogram.dispatcher.webhook import get_new_configured_app
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, OPENAI_API_KEY
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
from keyboards import support_button

# ✅ Webhook + WebApp config
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://gpt-assistant-bot-v.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

# ✅ Настройка логов
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ✅ Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ✅ Глобальные переменные
dialogues = {}
waiting_for_days = {}  # user_id → True (ожидает срок)
waiting_for_completion = {}  # user_id → номер этапа
pool = None

# ✅ Команды
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="goal", description="Показать цель"),
        BotCommand(command="plan", description="Показать план"),
        BotCommand(command="check", description="Проверить прогресс"),
        BotCommand(command="support", description="Написать в поддержку"),
    ]
    await bot.set_my_commands(commands)

# ✅ System Prompt
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

# ✅ Вспомогательные функции
def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""

# ✅ GPT функция
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
        reply = response["choices"][0]["message"]["content"]
        dialogues[user_id].append({"role": "assistant", "content": reply})

        # ✅ Сохраняем цель и план
        if "Цель:" in reply and "План действий" in reply:
            goal = extract_between(reply, "Цель:", "План действий").strip()
            plan = reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)

            # Создаём прогресс на неделю
            deadline = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline)

        return reply
    except Exception as e:
        return f"Ошибка GPT: {e}"

# ✅ /start
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    await upsert_user(pool, user_id, message.from_user.username or "", message.from_user.first_name or "")

    if not await check_access(pool, user_id):
        await message.reply("❌ У вас нет доступа. Обратитесь в поддержку:", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    response = await chat_with_gpt(user_id, "Начнем?")
    await message.reply(response)

# ✅ Обработчик диалога
@dp.message_handler()
async def handle_message(message: Message):
    user_id, text = message.from_user.id, message.text

    if not await check_access(pool, user_id):
        await message.reply("❌ Нет доступа. Обратитесь в поддержку:", reply_markup=support_button)
        return

    # ✅ Ждём срок
    if waiting_for_days.get(user_id):
        days = extract_days(text)
        deadline = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        await create_progress_stage(pool, user_id, stage=1, deadline=deadline)
        waiting_for_days[user_id] = False
        await message.reply(f"✅ План зафиксирован на {days} дней.")
        return

    # ✅ Ждём ответ по выполнению
    if user_id in waiting_for_completion:
        if "да" in text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
            await message.reply("🔥 Отлично! Идём дальше!")
        else:
            await message.reply("⚠️ Не сдавайся! Попробуем продолжить?")
        del waiting_for_completion[user_id]
        return

    # ✅ Диалог с GPT
    response = await chat_with_gpt(user_id, text)
    await message.reply(response)

    if any(w in response.lower() for w in ["срок", "дедлайн", "за сколько"]):
        waiting_for_days[user_id] = True

# ✅ /goal
@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Твоя цель:\n{goal}" if goal else "Цель не найдена.")

# ✅ /plan
@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n{plan}" if plan else "План не найден.")

# ✅ /check
@dp.message_handler(commands=["check"])
async def check_handler(message: Message):
    progress = await check_last_progress(pool, message.from_user.id)
    if not progress:
        await message.reply("Нет активного этапа.")
        return
    await message.reply(f"Этап {progress['stage']} готов? Напиши: да / нет")
    waiting_for_completion[message.from_user.id] = progress["stage"]

# ✅ /support
@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Нужна помощь? Напиши сюда:", reply_markup=support_button)

# ✅ Напоминания
REMINDER_TEXTS = [
    "⏰ Проверь свой план!",
    "🔥 Время проверить прогресс!",
    "📅 Двигаемся к цели, как дела?",
    "💪 Ты молодец! Но цели сами не выполнятся!"
]

async def send_reminders():
    users = await get_all_users(pool)
    for user in users:
        try:
            await bot.send_message(user["user_id"], random.choice(REMINDER_TEXTS))
        except BotBlocked:
            logging.warning(f"User {user['user_id']} заблокировал бота")

# ✅ Ошибки
@dp.errors_handler()
async def error_handler(update, exception):
    try:
        await update.message.answer("⚠️ Ошибка. Обратитесь в поддержку.", reply_markup=support_button)
    except:
        pass
    return True

# ✅ ON STARTUP
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))
    scheduler.start()
    logging.info("✅ Бот запущен.")

# ✅ Webhook app
app = get_new_configured_app(dispatcher=dp, path=WEBHOOK_PATH)

async def on_startup_webhook(app):
    await bot.set_webhook(WEBHOOK_URL)
    await on_startup(dp)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown_webhook(app):
    await bot.delete_webhook()
    logging.warning("Webhook удален.")

app.on_startup.append(on_startup_webhook)
app.on_shutdown.append(on_shutdown_webhook)

# ✅ RUN
if __name__ == "__main__":
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)