# -*- coding: utf-8 -*-
import sys
import logging
import openai
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.utils import executor
from config import BOT_TOKEN, OPENAI_API_KEY
from database import create_progress_stage  # type: ignore
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
)  # type: ignore
from keyboards import support_button
from aiogram.utils.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
from aiogram.utils.executor import start_webhook

WEBHOOK_HOST = os.getenv(
    "WEBHOOK_HOST"
)  # Например: https://gpt-assistant-bot-v.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 5000))

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

bot = Bot(token=BOT_TOKEN)  # type: ignore
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

from aiogram.types import BotCommand


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу с помощником"),
        BotCommand(command="goal", description="Показать мою цель"),
        BotCommand(command="plan", description="Показать мой план действий"),
        BotCommand(command="check", description="Проверить выполнение плана"),
        BotCommand(command="support", description="Написать в поддержку"),
    ]
    await bot.set_my_commands(commands)


# Хранение диалогов
dialogues = {}
waiting_for_days = {}  # user_id: True/False — ждёт ли бот срок
pool = None  # создаётся при запуске
waiting_for_completion = {}  # user_id: номер этапа, если бот ждёт подтверждения

# System prompt
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

# Извлечение числа дней из текста (для гибкого дедлайна)
import re


def extract_days(text: str) -> int:
    """Пытается извлечь число дней из текста"""
    numbers = re.findall(r"\d+", text)
    if numbers:
        return int(numbers[0])
    return 7  # по умолчанию, если число не указано


# Вспомогательная функция
def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""


# GPT-ответ + сохранение цели/плана
async def chat_with_gpt(user_id: int, user_input: str) -> str:
    if user_id not in dialogues:
        dialogues[user_id] = [{"role": "system", "content": system_prompt}]

    dialogues[user_id].append({"role": "user", "content": user_input})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o", messages=dialogues[user_id], temperature=0.7
        )
        gpt_reply = response["choices"][0]["message"]["content"]  # type: ignore
        dialogues[user_id].append({"role": "assistant", "content": gpt_reply})

        if "Цель:" in gpt_reply and "План действий" in gpt_reply:
            goal = extract_between(gpt_reply, "Цель:", "План действий").strip()
            plan = gpt_reply.split("План действий:")[-1].strip()
            await update_goal_and_plan(pool, user_id, goal, plan)

            # Сохраняем первую неделю прогресса (по умолчанию 7 дней)
            import datetime

            today = datetime.datetime.now()
            deadline = today + datetime.timedelta(days=7)
            deadline_str = deadline.strftime("%Y-%m-%d %H:%M:%S")
            await create_progress_stage(pool, user_id, stage=1, deadline=deadline_str)

        return gpt_reply

    except Exception as e:
        return f"Ошибка GPT: {type(e).__name__}"


# /start
@dp.message_handler(commands=["start"])
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    await upsert_user(pool, user_id, username, first_name)

    access = await check_access(pool, user_id)
    if not access:
        await message.reply(
            "❌ У вас нет доступа. Обратитесь в техподдержку.",
            reply_markup=support_button,
        )
        return

    dialogues[user_id] = [{"role": "system", "content": system_prompt}]
    first_prompt = (
        "Задай мне вопросы, чтобы определить мой тип кондитера, цели по доходу и помочь мне их достичь. "
        "Будь моим помощником и доведи меня до результата."
    )
    first_response = await chat_with_gpt(user_id, first_prompt)
    await message.reply(first_response)


# Диалог
@dp.message_handler()
async def handle_chat(message: Message):
    user_id = message.from_user.id
    user_text = message.text

    # Проверка доступа
    access = await check_access(pool, user_id)
    if not access:
        from keyboards import support_button

        await message.reply(
            "❌ У вас нет доступа. Обратитесь в техподдержку.",
            reply_markup=support_button,
        )
        return

    # ⏳ Если бот ждёт количество дней
    if waiting_for_days.get(user_id):
        days = extract_days(user_text)
        import datetime

        deadline = datetime.datetime.now() + datetime.timedelta(days=days)
        deadline_str = deadline.strftime("%Y-%m-%d %H:%M:%S")
        await create_progress_stage(pool, user_id, stage=1, deadline=deadline_str)

        await message.reply(f"Отлично! План зафиксирован на {days} дней ✅")
        waiting_for_days[user_id] = False
        return

    # ✅ Если бот ждёт подтверждение выполнения задания
    if user_id in waiting_for_completion:
        answer = user_text.lower()
        current_stage = waiting_for_completion[user_id]

        if "да" in answer:
            await mark_progress_completed(pool, user_id, current_stage)
            await message.reply("Отлично! 🔥 Ты получаешь балл. Продолжаем!")
            await create_next_stage(pool, user_id, stage=current_stage + 1)
            del waiting_for_completion[user_id]
            return

        elif "нет" in answer:
            await message.reply(
                "Понимаю. Но если ты не будешь делать — ты не достигнешь цели 😔\nПродолжаем или отложим?"
            )
            del waiting_for_completion[user_id]
            return

    # 💬 Обычный диалог с GPT
    response = await chat_with_gpt(user_id, user_text)
    await message.reply(response)

    # если GPT задал вопрос про срок — начинаем ждать ответ
    if any(
        word in response.lower()
        for word in ["тебе подойдёт", "за сколько дней", "график", "срок"]
    ):
        waiting_for_days[user_id] = True


# /цель
@dp.message_handler(commands=["goal"])
async def goal_handler(message: Message):
    goal, _ = await get_goal_and_plan(pool, message.from_user.id)
    if goal:
        await message.reply(f"🎯 Твоя цель:\n\n{goal}")
    else:
        await message.reply("Цель ещё не сохранена. Заверши диалог с GPT.")


# /план
@dp.message_handler(commands=["plan"])
async def plan_handler(message: Message):
    _, plan = await get_goal_and_plan(pool, message.from_user.id)
    if plan:
        await message.reply(f"📅 План действий:\n\n{plan}")
    else:
        await message.reply("План ещё не составлен. Продолжай диалог с GPT.")


# /потдержка
@dp.message_handler(commands=["support"])
async def support_handler(message: Message):
    await message.reply(
        "Нужна помощь? Напиши в поддержку:", reply_markup=support_button
    )


# 🔧 ON STARTUP
async def on_startup(app):  # type: ignore
    global pool
    pool = await create_pool()
    await set_commands(bot)
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("✅ Бот запущен через Webhook")


# 🛑 ON SHUTDOWN
async def on_shutdown(app):
    await bot.delete_webhook()


# 🚀 RUN WEBHOOK
async def on_startup_webhook(dp):
    global pool
    pool = await create_pool()
    await bot.set_webhook(WEBHOOK_URL)
    await set_commands(bot)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")


async def on_shutdown_webhook(dp):
    logging.warning("Удаление webhook...")
    await bot.delete_webhook()


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


# /Прверка
@dp.message_handler(commands=["check"])
async def check_progress_handler(message: Message):
    user_id = message.from_user.id
    progress = await check_last_progress(pool, user_id)

    if not progress:
        await message.reply(
            "У тебя ещё нет начатого плана. Заверши первую неделю с GPT."
        )
        return

    stage = progress["stage"]
    completed = progress["completed"]
    checked = progress["checked"]

    if completed:
        await message.reply("✅ Ты уже завершил последний этап. Молодец!")
        return

    if not checked:
        await message.reply(f"Ты выполнил задания по этапу {stage}? Напиши: да / нет")
        waiting_for_days[user_id] = False  # сбрасываем ожидание дедлайна
        waiting_for_completion[user_id] = stage  # type: ignore # начинаем ждать ответ


@dp.errors_handler()
async def error_handler(update, exception):
    if isinstance(exception, TelegramAPIError):
        return True  # игнорируем стандартные ошибки Telegram

    try:
        await update.message.answer(
            "⚠️ Возникла ошибка. Обратитесь в поддержку.", reply_markup=support_button
        )
    except:
        pass

    return True


# Функция, которая будет выполняться каждый день
async def check_inactive_users():
    from database import get_users_for_reminder  # ты уже это писал

    user_ids = await get_users_for_reminder(pool)
    for user_id in user_ids:
        try:
            await bot.send_message(
                user_id,
                "Привет! Ты ещё не сообщил, как идёт выполнение плана. Всё идёт по плану?",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить напоминание {user_id}: {e}")


# В on_startup — запускаем планировщик
async def on_startup(dp):
    global pool
    pool = await create_pool()
    await set_commands(bot)

    # Планировщик
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_inactive_users, CronTrigger(hour=10))  # каждый день в 10:00
    scheduler.start()

    logging.info("Bot: GPT-Assistant запущен")
