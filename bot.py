import os
import random
import openai
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
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например: gpt-assistant-bot-v.onrender.com
WEBHOOK_PATH = f"/bot{TOKEN}"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"

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

# ✅ Напоминания (только для тех, у кого есть план)
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

# ✅ Обработка текста цели
@dp.message_handler(lambda m: not m.text.startswith('/'))
async def handle_goal_text(message: types.Message):
    pool = await create_pool()
    text = message.text
    await message.answer("Генерирую план...")

    goal_and_plan = await generate_goal_and_plan(text)
    await save_goal(pool, str(message.from_user.id), text)
    await save_plan(pool, str(message.from_user.id), goal_and_plan)

    await message.answer(f"✅ Цель сохранена!\n\n{goal_and_plan}")

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

# ✅ Webhook запуск
async def on_startup(dp):
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    await bot.delete_webhook()
    print("❌ Webhook удален")

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT
    )