# -*- coding: utf-8 -*-
import sys
import logging
import openai
import os
import random
import datetime
import re

from database import get_users_for_reminder 
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError

from config import BOT_TOKEN, OPENAI_API_KEY
from database import (
    create_pool,
    upsert_user,
    check_access,
    get_goal_and_plan,
    update_goal_and_plan,
    create_progress_stage,
    check_last_progress,
    mark_progress_completed,
    create_next_stage,
    get_progress,
    get_all_users,  # Функция для получения всех пользователей
)

from keyboards import support_button
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ✅ Настройки Webhook
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 5000))

sys.stdout.reconfigure(encoding="utf-8")  # Для корректного вывода

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ✅ Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ✅ Команды меню
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="goal", description="Моя цель"),
        BotCommand(command="plan", description="Мой план"),
        BotCommand(command="progress", description="Прогресс"),
        BotCommand(command="support", description="Техподдержка"),
        BotCommand(command="test_reminder", description="Тест напоминаний"),
    ]
    await bot.set_my_commands(commands)

# ✅ Диалоги
dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
pool = None

# ✅ Системный промт GPT
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

# ✅ Новая логика напоминаний
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели, ты справишься!",
    "📅 Настало время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

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

async def send_reminders():
    try:
        users = await get_users_for_reminder(pool)  # только те, у кого есть активные этапы
        if not users:
            logging.info("Нет пользователей для напоминаний.")
            return

        for user in users:
            # ✅ Ограничение: только с вероятностью 30% (чтобы не надоедать каждый день)
            if random.random() > 0.3:
                continue

            try:
                # 50% шанс использовать GPT для креатива
                text = await generate_reminder_message() if random.random() > 0.5 else random.choice(REMINDER_TEXTS)
                await bot.send_message(user["user_id"], text)
                logging.info(f"Напоминание отправлено пользователю {user['user_id']}")
            except BotBlocked:
                logging.warning(f"Пользователь {user['user_id']} заблокировал бота")
            except Exception as e:
                logging.error(f"Ошибка при отправке пользователю {user['user_id']}: {e}")
    except Exception as e:
        logging.error(f"Ошибка при получении пользователей: {e}")

# ✅ Генерация напоминания через GPT-3.5
async def generate_reminder_message():
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты дружелюбный мотиватор."},
                {"role": "user", "content": "Создай короткое мотивирующее напоминание. Максимум одно предложение."}
            ],
            max_tokens=50,
            temperature=0.8,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.warning(f"Ошибка GPT: {e}. Использую заготовленный текст.")
        return random.choice(REMINDER_TEXTS)

# ✅ Получаем пользователей с активными задачами
async def get_users_with_active_tasks(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT user_id FROM progress
            WHERE completed = FALSE AND deadline > NOW()
        """)
        return [row["user_id"] for row in rows]

# ✅ Основная функция отправки напоминаний
async def send_reminders():
    try:
        users = await get_users_for_reminder(pool)  # Только с активными задачами
        for user in users:
            try:
                # Рандомизация текста
                if random.random() > 0.5:
                    text = await generate_reminder_message()
                else:
                    text = random.choice(REMINDER_TEXTS)

                await bot.send_message(user["user_id"], text)
            except BotBlocked:
                logging.warning(f"Пользователь {user['user_id']} заблокировал бота")
            except Exception as e:
                logging.error(f"Ошибка при отправке пользователю {user['user_id']}: {e}")
    except Exception as e:
        logging.error(f"Ошибка при получении пользователей: {e}")

# ✅ Команда для теста напоминаний
@dp.message_handler(commands=["test_reminder"])
async def test_reminder(message: Message):
    await send_reminders()
    await message.reply("✅ Напоминания отправлены всем пользователям!")

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
    response = await chat_with_gpt(user_id, "Начни диалог")
    await message.reply(response)

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

# ✅ /support
@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Нужна помощь? Напиши в поддержку 👇", reply_markup=support_button)

# ✅ GPT-обработчик
@dp.message_handler()
async def handle_chat(message: Message):
    user_id = message.from_user.id
    text = message.text
    response = await chat_with_gpt(user_id, text)
    await message.reply(response)

# ✅ GPT-функция
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
        return gpt_reply
    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"

# ✅ ON STARTUP
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour=10))
    scheduler.add_job(send_reminders, CronTrigger(hour=15))
    scheduler.add_job(send_reminders, CronTrigger(hour=19))
    scheduler.start()

    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

# ✅ ON SHUTDOWN
async def on_shutdown(dp):
    await bot.delete_webhook()
    await bot.session.close()
    logging.warning("Webhook удалён и сессия закрыта.")

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