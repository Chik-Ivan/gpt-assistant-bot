# -*- coding: utf-8 -*-
"""
Главный файл Telegram-бота с поддержкой GPT и личного планирования.
Функции:
✅ Старт и диалог с GPT
✅ Сохранение целей и планов в БД
✅ Проверка доступа
✅ Напоминания с разными сообщениями
✅ Обработка ошибок с кнопкой поддержки
✅ Webhook для Render
"""

import os
import sys
import logging
import random
import datetime
import re
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.dispatcher.webhook import get_new_configured_app
from aiogram.utils.exceptions import TelegramAPIError, BotBlocked
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import openai

# =====================
# ✅ Настройка окружения
# =====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например: https://gpt-assistant-bot.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_PORT = int(os.environ.get("PORT", 5000))

openai.api_key = OPENAI_API_KEY

# =====================
# ✅ Настройка логов
# =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# =====================
# ✅ Инициализация бота
# =====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# =====================
# ✅ Импорты функций из базы
# =====================
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

# =====================
# ✅ Меню и кнопки
# =====================
main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True).add(
    types.KeyboardButton("🎯 Цель"),
    types.KeyboardButton("📅 План"),
    types.KeyboardButton("✅ Проверка")
)

support_button = types.InlineKeyboardMarkup().add(
    types.InlineKeyboardButton("🆘 Написать в поддержку", url="https://t.me/Abramova_school_support")
)

# =====================
# ✅ Системный prompt для GPT
# =====================
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

dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
pool = None

# =====================
# ✅ Напоминания — разные тексты
# =====================
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели, ты справишься!",
    "📅 Настало время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

# =====================
# ✅ GPT-ответ
# =====================
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

            # Добавляем первую неделю в прогресс
            deadline = datetime.datetime.now() + datetime.timedelta(days=7)
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline)

        return gpt_reply
    except Exception as e:
        return f"Ошибка GPT: {e}"

# =====================
# ✅ Вспомогательные функции
# =====================
def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""

def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

# =====================
# ✅ Обработчики команд
# =====================
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    await upsert_user(pool, user_id, username, first_name)

    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа к ассистенту.", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    first_response = await chat_with_gpt(user_id, "Начнем?")
    await message.reply(first_response, reply_markup=main_menu)

@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Твоя цель:\n\n{goal}" if goal else "Цель еще не сохранена.")

@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n\n{plan}" if plan else "План еще не составлен.")

@dp.message_handler(commands=["check"])
async def check_progress_handler(message: Message):
    progress = await check_last_progress(pool, message.from_user.id)
    if not progress:
        await message.reply("Пока нет прогресса. Заверши первую неделю.")
        return

    stage, completed, checked = progress["stage"], progress["completed"], progress["checked"]
    if completed:
        await message.reply("✅ Ты уже завершил последний этап.")
    elif not checked:
        await message.reply(f"Ты выполнил задания по этапу {stage}? Напиши: да / нет")
        waiting_for_completion[message.from_user.id] = stage

# =====================
# ✅ Напоминания
# =====================
async def send_reminders():
    users = await get_all_users(pool)
    for user in users:
        text = random.choice(REMINDER_TEXTS)
        try:
            await bot.send_message(user["user_id"], text)
        except BotBlocked:
            logging.warning(f"Пользователь {user['user_id']} заблокировал бота.")

# =====================
# ✅ Обработчик диалога
# =====================
@dp.message_handler()
async def handle_chat(message: Message):
    user_id, user_text = message.from_user.id, message.text

    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа.", reply_markup=support_button)
        return

    # Ждем сроков
    if waiting_for_days.get(user_id):
        days = extract_days(user_text)
        deadline = datetime.datetime.now() + datetime.timedelta(days=days)
        await create_progress_stage(pool, user_id, stage=1, deadline=deadline)
        await message.reply(f"План установлен на {days} дней ✅")
        waiting_for_days[user_id] = False
        return

    # Ждем подтверждения выполнения
    if user_id in waiting_for_completion:
        if "да" in user_text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await message.reply("🔥 Отлично! Продолжаем.")
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
        else:
            await message.reply("Не переживай, продолжим работать!")
        del waiting_for_completion[user_id]
        return

    # GPT-диалог
    response = await chat_with_gpt(user_id, user_text)
    await message.reply(response)

# =====================
# ✅ Обработка ошибок
# =====================
@dp.errors_handler()
async def error_handler(update, exception):
    if isinstance(exception, TelegramAPIError):
        return True
    try:
        await update.message.answer("⚠️ Ошибка! Обратитесь в поддержку.", reply_markup=support_button)
    except:
        pass
    return True

# =====================
# ✅ Webhook и запуск
# =====================
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await bot.set_webhook(WEBHOOK_URL)

    # Планировщик напоминаний
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))  # Каждый день 18:00
    scheduler.start()
    logging.info("✅ Бот запущен с Webhook!")

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    app = get_new_configured_app(dispatcher=dp, path=WEBHOOK_PATH)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, port=WEBAPP_PORT)