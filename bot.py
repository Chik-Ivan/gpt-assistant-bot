import asyncio
from create_bot import bot, dp, logger
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from handlers.start_handler import start_router
from handlers.main_kb_handler import main_kb_router
from aiohttp import web
from config import WEBHOOK_PATH, WEBHOOK_URL, PORT


async def on_startup():
    await set_commands()
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)


async def main():
    await set_commands()

    dp.include_router(start_router)
    dp.include_router(main_kb_router)
    dp.startup.register(on_startup)

    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )

    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(PORT)
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    
    try:
        await site.start()
        logger.info(f"Бот успешно запущен на порту {port}. URL: {WEBHOOK_URL}")
        await asyncio.Event().wait()
    finally:
        await bot.session.close()


async def set_commands():
    commands = [
        BotCommand(command="start", description="start bot")
    ]
    await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")







# # Глобальные переменные
# dialogues = {}
# waiting_for_days = {}
# waiting_for_completion = {}
# pool = None





# # ==========================
# # ✅ Хэндлеры команд
# @dp.message_handler(commands=["start"])
# async def start_handler(message: Message, state: FSMContext):
#     user_id = message.from_user.id

#     state_name = await state.get_state()
#     if state_name:
#         await message.answer("Ты уже начал проходить опрос. Продолжим с того места или начнём сначала?", reply_markup=start_choice_keyboard)
#         return
#     await upsert_user(pool, user_id, message.from_user.username or "", message.from_user.first_name or "", False, 0, datetime.utcnow())

#     if not await check_access(pool, user_id):
#         await message.reply("❌ Нет доступа. Обратитесь в поддержку.", reply_markup=support_button)
#         return

#     dialogues[user_id] = [{"role": "system", "content": system_prompt}]
#     await message.reply(await chat_with_gpt(user_id, "Начни диалог"))



# # ✅ Общий обработчик
# @dp.message_handler()
# async def handle_chat(message: Message):
#     user_id = message.from_user.id
#     if not await check_access(pool, user_id):
#         await message.reply("❌ Нет доступа. Обратитесь в поддержку.", reply_markup=support_button)
#         return
#     text = message.text
#     if waiting_for_days.get(user_id):
#         days = extract_days(text)
#         deadline = datetime.datetime.now() + datetime.timedelta(days=days)
#         await create_progress_stage(pool, user_id, 1, deadline.strftime("%Y-%m-%d %H:%M:%S"))
#         await message.reply(f"✅ План установлен на {days} дней.")
#         waiting_for_days[user_id] = False
#         return
#     if user_id in waiting_for_completion:
#         if "да" in text.lower():
#             await mark_progress_completed(pool, user_id, waiting_for_completion[user_id])
#             await create_next_stage(pool, user_id, waiting_for_completion[user_id] + 1)
#             await message.reply("🔥 Отлично! Продолжаем!")
#         else:
#             await message.reply("Понимаю. Продолжай стараться!")
#         del waiting_for_completion[user_id]
#         return
#     response = await chat_with_gpt(user_id, text)
#     await message.reply(response)
#     if any(word in response.lower() for word in ["срок", "дедлайн"]):
#         waiting_for_days[user_id] = True

# # ==========================
# # ✅ Напоминания
# REMINDER_TEXTS = [
#     "⏰ Проверь свой план! Делаешь успехи?",
#     "🔔 Не забывай про свои цели!",
#     "📅 Время проверить прогресс.",
#     "🔥 Ты молодец! Но цели сами не выполнятся!"
# ]

# async def generate_reminder_message():
#     try:
#         resp = openai.ChatCompletion.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "Ты дружелюбный мотиватор."},
#                 {"role": "user", "content": "Создай короткое напоминание (одно предложение)."}
#             ],
#             max_tokens=50, temperature=0.8
#         )
#         return resp["choices"][0]["message"]["content"].strip()
#     except:
#         return random.choice(REMINDER_TEXTS)

