# -*- coding: utf-8 -*-
import sys
import os
import logging
import openai
import re
import datetime
from random import choice

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.utils.executor import start_webhook
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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

sys.stdout.reconfigure(encoding="utf-8")

# ============ ЛОГИ ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ============ БАЗОВАЯ НАСТРОЙКА ============
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY
pool = None  # Создается при старте

# Настройка Webhook
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Домен Render, например: https://gpt-assistant-bot-v2.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 5000))

# ============ СИСТЕМНЫЙ ПРОМТ ============
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

# Хранение диалогов
dialogues = {}
waiting_for_days = {}  # user_id → True/False
waiting_for_completion = {}  # user_id → этап


# ============ ПОЛЕЗНЫЕ ФУНКЦИИ ============
def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7


def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="goal", description="Моя цель"),
        BotCommand(command="plan", description="Мой план"),
        BotCommand(command="check", description="Проверка прогресса"),
    ]
    await bot.set_my_commands(commands)


# ============ GPT-ОТВЕТ ============
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

            deadline = datetime.datetime.now() + datetime.timedelta(days=7)
            await create_progress_stage(pool, user_id, 1, deadline.strftime("%Y-%m-%d %H:%M:%S"))

        return gpt_reply
    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"


# ============ КОМАНДЫ ============
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    await upsert_user(pool, user_id, username, first_name)

    access = await check_access(pool, user_id)
    if not access:
        await message.reply(
            "❌ У вас нет доступа. Обратитесь к администратору.",
            reply_markup=support_button,
        )
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    first_prompt = (
        "Задай мне вопросы, чтобы определить мой тип кондитера и помочь достичь цели."
    )
    first_response = await chat_with_gpt(user_id, first_prompt)
    await message.reply(first_response)


@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Твоя цель:\n\n{goal}" if goal else "Цель ещё не сохранена.")


@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План действий:\n\n{plan}" if plan else "План ещё не составлен.")


@dp.message_handler(commands=["check"])
async def check_progress_handler(message: Message):
    user_id = message.from_user.id
    progress = await check_last_progress(pool, user_id)

    if not progress:
        await message.reply("План ещё не начат.")
        return

    stage = progress["stage"]
    completed = progress["completed"]
    if completed:
        await message.reply("✅ Ты уже завершил последний этап.")
    else:
        await message.reply(f"Ты выполнил задания по этапу {stage}? Напиши: да / нет")
        waiting_for_completion[user_id] = stage


# ============ ДИАЛОГ ============
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
        deadline = datetime.datetime.now() + datetime.timedelta(days=days)
        await create_progress_stage(pool, user_id, 1, deadline.strftime("%Y-%m-%d %H:%M:%S"))
        await message.reply(f"План зафиксирован на {days} дней ✅")
        waiting_for_days[user_id] = False
        return

    if user_id in waiting_for_completion:
        if "да" in text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await message.reply("🔥 Отлично! Продолжаем!")
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
        else:
            await message.reply("Хорошо, попробуем позже.")
        waiting_for_completion.pop(user_id)
        return

    response = await chat_with_gpt(user_id, text)
    await message.reply(response)
    if any(word in response.lower() for word in ["дней", "срок", "график"]):
        waiting_for_days[user_id] = True


# ============ НАПОМИНАНИЯ ============
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели, ты справишься!",
    "📅 Настало время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]


async def send_reminders():
    users = await get_all_users(pool)
    for user in users:
        try:
            text = choice(REMINDER_TEXTS)
            await bot.send_message(user["user_id"], text)
        except Exception as e:
            logging.warning(f"Ошибка отправки напоминания: {e}")


# ============ ОБРАБОТКА ОШИБОК ============
@dp.errors_handler()
async def error_handler(update, exception):
    try:
        await update.message.answer("⚠️ Возникла ошибка. Обратитесь в поддержку.", reply_markup=support_button)
    except:
        pass
    return True


# ============ HEALTHCHECK ============
@dp.message_handler(commands=["ping"])
async def ping_handler(message: Message):
    await message.reply("✅ Бот работает!")


# ============ ON_STARTUP ============
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("Webhook установлен.")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))  # Напоминание каждый день
    scheduler.start()


# ============ ЗАПУСК ============
if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )