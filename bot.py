import os
import random
import openai
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.executor import start_webhook
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import (
    create_pool, save_user, check_access,
    get_goal, get_plan, save_goal, save_plan,
    get_progress, get_users_for_reminder, update_last_reminder
)

# ✅ ENV
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Пример: gpt-assistant-bot-v.onrender.com
WEBHOOK_URL = f"https://{WEBHOOK_HOST}/{TOKEN}"  # ✅ Автоматически добавляем https://

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))

# ✅ Инициализация
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()
openai.api_key = OPENAI_KEY

REMINDER_TEXTS = [
    "Не забывайте о ваших целях! Как продвигаетесь?",
    "Помните, маленькие шаги приводят к большим результатам!",
    "Сегодня отличный день, чтобы выполнить часть плана!"
]

SYSTEM_PROMPT = """
Ты — умный ассистент. Твоя задача:
1. Выяснить цель пользователя.
2. Сформировать понятный план действий с дедлайнами.
3. Разбить на этапы (progress).
Ответ будь кратким и структурированным.
"""

support_btn = InlineKeyboardMarkup().add(
    InlineKeyboardButton("Написать в поддержку", url="https://t.me/Abramova_school_support")
)

# ✅ GPT: Напоминание
async def generate_reminder_message():
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты дружелюбный ассистент."},
                {"role": "user", "content": "Напомни пользователю про выполнение задач."}
            ],
            temperature=0.8
        )
        return response["choices"][0]["message"]["content"].strip()
    except:
        return random.choice(REMINDER_TEXTS)

# ✅ GPT: Генерация цели и плана
async def generate_goal_and_plan(user_text: str):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Моя цель: {user_text}"}
        ],
        temperature=0.7
    )
    return response["choices"][0]["message"]["content"].strip()

# ✅ Напоминания
async def send_reminders():
    pool = await create_pool()
    users = await get_users_for_reminder(pool)
    for user in users:
        if random.random() < 0.4:  # ~3 раза в неделю
            try:
                text = await generate_reminder_message()
                await bot.send_message(user["telegram_id"], text)
                await update_last_reminder(pool, user["telegram_id"])
            except Exception as e:
                print(f"Ошибка при отправке напоминания {user['telegram_id']}: {e}")

# ✅ Планировщик
scheduler.add_job(send_reminders, "cron", hour="10,18")

# ✅ /start
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    pool = await create_pool()
    await save_user(pool, str(message.from_user.id), message.from_user.username, message.from_user.first_name, message.from_user.id)
    access = await check_access(pool, str(message.from_user.id))

    if not access:
        await message.answer("У вас нет доступа. Напишите в поддержку.", reply_markup=support_btn)
        return

    await message.answer("Привет! Напиши свою цель, и я помогу составить план.")

# ✅ Обработка текста цели (фоновая задача для GPT)
@dp.message_handler(lambda m: not m.text.startswith('/'))
async def handle_goal_text(message: types.Message):
    await message.answer("Генерирую план...")
    asyncio.create_task(process_goal(message))

async def process_goal(message: types.Message):
    try:
        pool = await create_pool()
        text = message.text

        goal_and_plan = await generate_goal_and_plan(text)
        await save_goal(pool, str(message.from_user.id), text)
        await save_plan(pool, str(message.from_user.id), goal_and_plan)

        await bot.send_message(message.chat.id, f"✅ Цель сохранена!\n\n{goal_and_plan}")
    except Exception as e:
        await bot.send_message(message.chat.id, f"Ошибка при генерации плана: {e}")

# ✅ /goal
@dp.message_handler(commands=["goal"])
async def goal_cmd(message: types.Message):
    pool = await create_pool()
    goal = await get_goal(pool, str(message.from_user.id))
    await message.answer(f"Ваша цель:\n{goal}" if goal else "Цель пока не задана.")

# ✅ /plan
@dp.message_handler(commands=["plan"])
async def plan_cmd(message: types.Message):
    pool = await create_pool()
    plan = await get_plan(pool, str(message.from_user.id))
    await message.answer(f"Ваш план:\n{plan}" if plan else "План пока не создан.")

# ✅ /progress
@dp.message_handler(commands=["progress"])
async def progress_cmd(message: types.Message):
    pool = await create_pool()
    progress = await get_progress(pool, message.from_user.id)
    total = progress["total"]
    completed = progress["completed"]
    points = progress["points"]
    percent = int((completed / total) * 100) if total > 0 else 0
    bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
    await message.answer(f"📊 Прогресс:\n{bar} {percent}%\n✅ Этапы: {completed}/{total}\n🔥 Баллы: {points}")

# ✅ /test_reminder
@dp.message_handler(commands=["test_reminder"])
async def test_reminder(message: types.Message):
    text = await generate_reminder_message()
    await message.answer(text)

# ✅ Webhook
async def on_startup(dp):
    print(f"✅ Устанавливаем webhook: {WEBHOOK_URL}")
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()
    print("❌ Webhook удален")

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=f"/{TOKEN}",
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT
    )