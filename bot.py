import asyncio
import pytz
from datetime import datetime, timedelta
from create_bot import bot, dp, logger, scheduler
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from handlers.start_handler import start_router
from handlers.create_plan_handlers import create_plan_router
from handlers.current_plan_handler import current_plan_router
from handlers.admin_handler import admin_router
from handlers.support_handler import support_router
from handlers.reminder_handler import send_reminders, check_deadlines_send_reminders, reminder_router
from aiohttp import web
from config import WEBHOOK_PATH, WEBHOOK_URL, PORT
from database.core import db
from access_manager import get_access


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
                       support_router,
                       admin_router,
                       reminder_router,
                       create_plan_router)
    

    dp.startup.register(on_startup)

    scheduler.start()


    scheduler.add_job(
        send_reminders,
        'cron',
        hour=12,
        minute=00,
        timezone=pytz.timezone('Europe/Moscow'),
        args=(bot,)
    )
    scheduler.add_job(
        check_deadlines_send_reminders,
        'cron',
        hour=13,
        minute=00,
        timezone=pytz.timezone('Europe/Moscow'),
        args=(bot,)
    )
    scheduler.add_job(
        get_access,
        'interval',
        minutes=5,
        next_run_time=datetime.now(pytz.timezone('Europe/Moscow')) + timedelta(minutes=1),
        misfire_grace_time=60
    )

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
        scheduler.shutdown()
        await bot.session.close()


async def set_commands():
    commands = [
        BotCommand(command="start", description="Запускает бота")
    ]
    await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")

