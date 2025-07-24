# -*- coding: utf-8 -*-
import sys
import logging
import os
import re
import random
import datetime
import openai
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
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
    get_users_for_reminder
)

# 🔗 Webhook config for Render
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # https://your-service.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 5000))

sys.stdout.reconfigure(encoding="utf-8")

# 🔍 Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ✅ Init bot & dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ✅ Register commands in Telegram
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу с помощником"),
        BotCommand(command="goal", description="Показать мою цель"),
        BotCommand(command="plan", description="Показать мой план действий"),
        BotCommand(command="check", description="Проверить выполнение плана"),
        BotCommand(command="support", description="Написать в поддержку"),
    ]
    await bot.set_my_commands(commands)

# 📌 Хранилища
dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
pool = None

# ✅ Основной промт GPT (НЕ трогаем)
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

# ✅ Извлечение числа дней
def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

# ✅ GPT-ответ
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

        # Если есть цель и план — сохраняем
        if "Цель:" in gpt_reply and "План действий" in gpt_reply:
            goal = gpt_reply.split("Цель:")[1].split("План действий")[0].strip()
            plan = gpt_reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)

            # Дедлайн + прогресс
            today = datetime.datetime.now()
            deadline = today + datetime.timedelta(days=7)
            await create_progress_stage(pool, user_id, 1, deadline.strftime("%Y-%m-%d %H:%M:%S"))

        return gpt_reply

    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"

# ✅ Команда /start
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    await upsert_user(pool, user_id, username, first_name)

    # Проверка доступа
    access = await check_access(pool, user_id)
    if not access:
        await message.reply("❌ У вас нет доступа.", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    intro_text = "Задай мне вопросы, чтобы определить мой тип кондитера и помочь достичь цели."
    response = await chat_with_gpt(user_id, intro_text)
    await message.reply(response)

# ✅ Обработка текста
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
            await message.reply("🔥 Отлично! Переходим к следующему этапу.")
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
        else:
            await message.reply("😔 Понимаю. Продолжим, когда будешь готов.")
        del waiting_for_completion[user_id]
        return

    response = await chat_with_gpt(user_id, text)
    await message.reply(response)
    if any(w in response.lower() for w in ["за сколько дней", "срок", "график"]):
        waiting_for_days[user_id] = True

# ✅ Команды goal/plan/check/support
@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Твоя цель:\n{goal}" if goal else "Цель не сохранена.")

@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n{plan}" if plan else "План ещё не составлен.")

@dp.message_handler(commands=["check"])
async def check_progress_handler(message: Message):
    progress = await check_last_progress(pool, message.from_user.id)
    if not progress:
        await message.reply("Нет начатого плана. Заверши диалог с GPT.")
        return
    if progress["completed"]:
        await message.reply("✅ Последний этап завершён!")
        return
    await message.reply(f"Ты выполнил этап {progress['stage']}? Напиши: да / нет")
    waiting_for_completion[message.from_user.id] = progress["stage"]

@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Напиши в поддержку:", reply_markup=support_button)

# ✅ Напоминания
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про цели, ты справишься!",
    "📅 Проверь прогресс прямо сейчас.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

async def generate_reminder():
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Создай короткое мотивирующее напоминание."}],
            max_tokens=50,
            temperature=0.8
        )
        return response["choices"][0]["message"]["content"].strip()
    except:
        return random.choice(REMINDER_TEXTS)

async def send_reminders():
    users = await get_all_users(pool)
    for user in users:
        try:
            text = await generate_reminder()
            await bot.send_message(user["user_id"], text)
        except BotBlocked:
            logging.warning(f"Пользователь {user['user_id']} заблокировал бота")

# ✅ Обработка ошибок
@dp.errors_handler()
async def error_handler(update, exception):
    if isinstance(exception, TelegramAPIError):
        return True
    try:
        await update.message.answer("⚠️ Ошибка! Обратитесь в поддержку.", reply_markup=support_button)
    except:
        pass
    return True

# ✅ Webhook старт и планировщик
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))  # Напоминания в 18:00
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    from aiogram.utils.executor import start_webhook
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )