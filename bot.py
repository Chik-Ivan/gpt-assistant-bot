# -*- coding: utf-8 -*-
import sys
import logging
import asyncio
import aiohttp
from keep_alive import keep_alive
import openai
import os
import random
from datetime import datetime

from aiogram.types import CallbackQuery
from aiogram.dispatcher import FSMContext
from states import GoalStates
from config import WEBHOOK_URL
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import  Message, BotCommand
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import BOT_TOKEN, OPENAI_API_KEY
from database import (
    create_pool,
    upsert_user,
    check_access,
    update_goal_and_plan,
    get_goal_and_plan,
    create_progress_stage,
    mark_progress_completed,
    create_next_stage,
    check_last_progress,
    get_progress,
    get_users_for_reminder
)
from keyboards import support_button

# Webhook config
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# ✅ Команды
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="goal", description="Моя цель"),
        BotCommand(command="plan", description="Мой план"),
        BotCommand(command="progress", description="Мой прогресс"),
        BotCommand(command="support", description="Поддержка"),
        BotCommand(command="test_reminder", description="Тест напоминания"),
    ]
    await bot.set_my_commands(commands)

# ==========================
# Глобальные переменные
dialogues = {}
waiting_for_days = {}
waiting_for_completion = {}
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

# ==========================
# Функции GPT
def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""

def extract_days(text: str) -> int:
    import re
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 7

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

        if "Цель:" in reply and "План действий" in reply:
            goal = extract_between(reply, "Цель:", "План действий").strip()
            plan = reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)
            deadline = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            await create_progress_stage(pool, user_id, 1, deadline)

        return reply
    except Exception as e:
        return f"Ошибка GPT: {e}"

# ==========================
# ✅ Хэндлеры команд
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    await upsert_user(pool, user_id, message.from_user.username or "", message.from_user.first_name or "", False, 0, datetime.utcnow())

    if not await check_access(pool, user_id):
        await message.reply("❌ Нет доступа. Обратитесь в поддержку.", reply_markup=support_button)
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    await message.reply(await chat_with_gpt(user_id, "Начни диалог"))

@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"🎯 Цель:\n{goal}" if goal else "Цель не сохранена.")

@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    await message.reply(f"📅 План:\n{plan}" if plan else "План не сохранён.")

@dp.message_handler(commands=["progress"])
async def progress_handler(message: Message):
    user_id = message.from_user.id
    data = await get_progress(pool, user_id)

    completed = data["completed"]
    total = data["total"]
    points = data["points"]

    total = max(total, 1)  # чтобы не делить на 0
    percent = int((completed / total) * 100)

    bar_length = 10
    filled_length = int(percent / 10)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)

    text = (
        f"📊 Прогресс:\n"
        f"{bar} {percent}%\n"
        f"✅ Этапы: {completed}/{total}\n"
        f"🔥 Баллы: {points}"
    )

    if data["next_deadline"]:
        text += f"\n📅 Следующий дедлайн: {data['next_deadline'].strftime('%d %B')}"

    await message.reply(text)
@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply("Нужна помощь? Напиши в поддержку 👇", reply_markup=support_button)

# ✅ Общий обработчик
@dp.message_handler()
async def handle_chat(message: Message):
    user_id = message.from_user.id
    if not await check_access(pool, user_id):
        await message.reply("❌ Нет доступа. Обратитесь в поддержку.", reply_markup=support_button)
        return
    text = message.text
    if waiting_for_days.get(user_id):
        days = extract_days(text)
        deadline = datetime.datetime.now() + datetime.timedelta(days=days)
        await create_progress_stage(pool, user_id, 1, deadline.strftime("%Y-%m-%d %H:%M:%S"))
        await message.reply(f"✅ План установлен на {days} дней.")
        waiting_for_days[user_id] = False
        return
    if user_id in waiting_for_completion:
        if "да" in text.lower():
            await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
            await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
            await message.reply("🔥 Отлично! Продолжаем!")
        else:
            await message.reply("Понимаю. Продолжай стараться!")
        del waiting_for_completion[user_id]
        return
    response = await chat_with_gpt(user_id, text)
    await message.reply(response)
    if any(word in response.lower() for word in ["срок", "дедлайн"]):
        waiting_for_days[user_id] = True

# ==========================
# ✅ Напоминания
REMINDER_TEXTS = [
    "⏰ Проверь свой план! Делаешь успехи?",
    "🔔 Не забывай про свои цели!",
    "📅 Время проверить прогресс.",
    "🔥 Ты молодец! Но цели сами не выполнятся!"
]

async def generate_reminder_message():
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты дружелюбный мотиватор."},
                {"role": "user", "content": "Создай короткое напоминание (одно предложение)."}
            ],
            max_tokens=50, temperature=0.8
        )
        return resp["choices"][0]["message"]["content"].strip()
    except:
        return random.choice(REMINDER_TEXTS)



async def send_reminders():
    if pool is None:
        logging.warning("⏳ Пропущено напоминание: нет подключения к базе данных")
        return

    try:
        users = await get_users_for_reminder()
        for user in users:
            user_id = user["user_id"]

            # Получаем текущий активный этап пользователя
            current_stage = await check_last_progress(pool, user_id)
            if not current_stage or current_stage["completed"]:
                continue  # Нет активной задачи

            # Получаем цель и план (если нет — пропускаем)
            goal, plan = await get_goal_and_plan(pool, user_id)
            if not goal or not plan:
                continue

            stage_number = current_stage["stage"]
            deadline = current_stage["deadline"]
            delta_days = (deadline - datetime.datetime.now()).days

            # 40% шанс отправки, 50% из них — GPT
            if random.random() < 0.4:
                if random.random() > 0.5:
                    prompt = (
                        f"Ты ассистент. Пользователь сейчас на этапе {stage_number} из плана: {plan}. "
                        f"Создай дружелюбное напоминание о текущем этапе, используя мотивационный тон. "
                        f"Срок выполнения — {deadline.strftime('%Y-%m-%d')}. Укажи действия или вдохнови продолжить."
                    )
                    try:
                        resp = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "Ты дружелюбный мотиватор, помогаешь пользователю дойти до цели."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=100,
                            temperature=0.8
                        )
                        text = resp["choices"][0]["message"]["content"].strip()
                    except Exception as e:
                        logging.error(f"GPT не сработал, fallback: {e}")
                        text = random.choice(REMINDER_TEXTS)
                else:
                    text = random.choice(REMINDER_TEXTS)

                await bot.send_message(user_id, text)

    except Exception as e:
        logging.error(f"Ошибка при отправке напоминаний: {e}")

@dp.message_handler(commands=["test_reminder"])
async def test_reminder(message: Message):
    await message.reply("🧪 Запускаю умные напоминания...")
    await send_reminders()
    await message.reply("✅ Тестовое напоминание: запускаю рассылку...")
    await send_reminders()

async def test_reminder(message: Message):
    await send_reminders()
    await message.reply("✅ Напоминания отправлены!")

# ==========================
# ✅ ON STARTUP
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, CronTrigger(hour="10,18"))
    scheduler.start()

    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

    # 👇 Автоматически "пингуем" Render, чтобы webhook не сбрасывался
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                data={"url": f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"}
            ) as resp:
                if resp.status == 200:
                    logging.info("Webhook успешно установлен вручную через код")
                else:
                    logging.error(f"Не удалось установить webhook: {resp.status}")
    except Exception as e:
        logging.error(f"Ошибка при установке webhook через код: {e}")

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )

async def handle_root(request):
    return web.Response(text="✅ Бот работает", status=200)

app = web.Application()
app.router.add_get("/", handle_root)

# Запуск aiohttp-сервера
if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=10000)
@dp.callback_query_handler(lambda c: c.data in ["fsm_restart", "fsm_continue"], state="*")
async def fsm_choice_callback(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.data == "fsm_restart":
        await state.finish()
        await callback_query.message.edit_text("🔁 Опрос начат заново. Какая у тебя цель?")
        await GoalStates.waiting_for_goal.set()
    elif callback_query.data == "fsm_continue":
        await callback_query.message.edit_text("▶️ Продолжаем с того места, где остановились.")

