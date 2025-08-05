import asyncio
from create_bot import bot, dp, logger
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from handlers.start_handler import start_router
from handlers.create_plan_handlers import create_plan_router
from handlers.current_plan_handler import current_plan_router
from handlers.data_handler import data_router
from handlers.admin_handler import admin_router
from aiohttp import web
from config import WEBHOOK_PATH, WEBHOOK_URL, PORT
from database.core import db


async def on_startup():
    await set_commands()
    await bot.set_webhook(WEBHOOK_URL, 
                          drop_pending_updates=True,
                          allowed_updates=["message", "callback_query", "inline_query", "edited_message"])
    await db.connect()


async def main():
    await set_commands()

    dp.include_routers(start_router,
                       current_plan_router,
                       data_router,
                       admin_router,
                       create_plan_router)

    dp.startup.register(on_startup)

    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        handle_callback_query=True,
        handle_message=True,
        handle_edited_updates=True,
        handle_inline_query=True,
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

