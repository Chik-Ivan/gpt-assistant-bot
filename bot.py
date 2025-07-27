# -*- coding: utf-8 -*-
import sys
import logging
import openai
import os
import random
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError
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
    get_active_users,
    get_users_for_reminder,
    get_progress,
)

# ✅ Настройки Webhook и WebApp
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например: https://gpt-assistant-bot-v.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 5000))

sys.stdout.reconfigure(encoding="utf-8")

# ✅ Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ✅ Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ✅ Команды в меню
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="goal", description="Показать мою цель"),
        BotCommand(command="plan", description="Показать мой план"),
        BotCommand(command="check", description="Проверить выполнение"),
        BotCommand(command="progress", description="Мой прогресс"),
        BotCommand(command="support", description="Техподдержка"),
    ]
    await bot.set_my_commands(commands)

# ✅ Переменные
dialogues = {}
waiting_for_days = {}  # Ждём срок
waiting_for_completion = {}  # Ждём подтверждения выполнения
pool = None

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

# ✅ GPT-ответ
async def chat_with_gpt(user_id: int, user_input: str) -> str:
    if user_id not in dialogues:
        dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    dialogues[user_id].append({"role": "user", "content": user_input})

    try:
        response = openai.ChatCompletion.create(model="gpt-4o", messages=dialogues[user_id], temperature=0.7)
        gpt_reply = response["choices"][0]["message"]["content"]
        dialogues[user_id].append({"role": "assistant", "content": gpt_reply})

        if "Цель:" in gpt_reply and "План действий" in gpt_reply:
            goal = extract_between(gpt_reply, "Цель:", "План действий").strip()
            plan = gpt_reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)

            # Сохраняем этап
            today = datetime.datetime.now()
            deadline = today + datetime.timedelta(days=7)
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline.strftime("%Y-%m-%d %H:%M:%S"))

        return gpt_reply
    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"

# ✅ /start
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    await upsert_user(pool, user_id, message.from_user.username or "", message.from_user.first_name or "")

    if not await check_access(pool, user_id):
        await message.reply("❌ У вас нет доступа. Напишите в поддержку.", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    first_prompt = "Помоги мне определить цель по доходу и составить план."
    first_response = await chat_with_gpt(user_id, first_prompt)
    await message.reply(first_response)

# ✅ Общий обработчик
@dp.message_handler()
async def handle_chat(message: Message):
    user_id, text = message.from_user.id, message.text

    if not await check_access(pool, user_id):
        await message.reply("❌ У вас нет доступа. Напишите в поддержку.", reply_markup=support_button)
        return

    if waiting_for_days.get(user_id):
        days = extract_days(text)
        deadline = datetime.datetime.now() + datetime.timedelta(days=days)
        await create_progress_stage(pool, user_id, stage=1, deadline=deadline.strftime("%Y-%m-%d %H:%M:%S"))
        await message.reply(f"Отлично! План на {days} дней ✅")
        waiting_for_days[user_id] = False
        return

    if user_id in waiting_for_completion:
        if "да" in text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
            await message.reply("🔥 Отлично! Идём дальше!")
        else:
            await message.reply("Ок, но не забывай — цель ждёт тебя! 💪")
        del waiting_for_completion[user_id]
        return

    response = await chat_with_gpt(user_id, text)
    await message.reply(response)

    if any(word in response.lower() for word in ["срок", "график", "за сколько"]):
        waiting_for_days[user_id] = True

# ✅ /goal
@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Твоя цель:\n\n{goal}" if goal else "Цель не найдена.")

# ✅ /plan
@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n\n{plan}" if plan else "План не найден.")

# ✅ /progress
@dp.message_handler(commands=["progress"])
async def progress_handler(message: Message):
    data = await get_progress(pool, message.from_user.id)
    progress_text = (
        f"📊 Прогресс:\n✅ {data['completed']} из {data['total']} этапов\n🔥 Баллы: {data['points']}\n"
    )
    if data["next_deadline"]:
        progress_text += f"📅 Следующий дедлайн: {data['next_deadline'].strftime('%d.%m')}\n"
    await message.reply(progress_text)

# ✅ /support
@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Напишите в поддержку:", reply_markup=support_button)

# ✅ Напоминания
REMINDER_TEXTS = [
    "⏰ Проверь свой план!",
    "🔔 Не забывай про цель!",
    "📅 Как прогресс?",
    "🔥 Ты справишься!"
]

async def send_reminders():
    users = await get_active_users(pool)
    for user in users:
        try:
            await bot.send_message(user["telegram_id"], random.choice(REMINDER_TEXTS))
        except BotBlocked:
            logging.warning(f"Пользователь {user['telegram_id']} заблокировал бота")

# ✅ Webhook lifecycle
async def on_startup_webhook(dp):
    global pool
    pool = await create_pool()
    await bot.set_webhook(WEBHOOK_URL)
    await set_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=18))
    scheduler.start()
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown_webhook(dp):
    logging.warning("Удаление webhook...")
    await bot.delete_webhook()
    await bot.session.close()

# ✅ Запуск
if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup_webhook,
        on_shutdown=on_shutdown_webhook,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )