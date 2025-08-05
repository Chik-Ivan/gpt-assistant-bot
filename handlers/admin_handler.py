import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandObject
from filters.is_admin import IsAdmin
from config import ADMINS
from handlers.current_plan_handler import check_plan
from database.core import db


admin_router = Router()


@admin_router.message(F.text == "⚙️ Админ панель", IsAdmin(ADMINS))
async def get_admin_panel(message: Message, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    await message.answer("Команды для админа:\n\n"
                   "/access_true + <id пользователя> выдает юзеру доступ к боту\n\n"
                   "/access_false + <id пользователя> забирает у пользователя доступ\n\n"
                   "/add_admin + <id пользователя> добавляет админа с указаным id\n\n"
                   "/del_admin + <id пользователя> удаляет админа\n\n"
                   "/check_appeals позволяет проверять обращения пользователя в поддержку (В разработке!)")

@admin_router.message(Command("access_true"), IsAdmin(ADMINS))
async def access_true(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    command_args: str = command.args
    db_repo = await db.get_repository()
    try:
        if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/access_true 123456789")
            return
        user = await db_repo.get_user(int(command_args))
        user.access = "TRUE"
        await db_repo.update_user(user)
        await message.answer("Доступ выдан успешно!")
    except Exception as e:
        logging.warning(e)
        await message.answer(f"ошибка\n\n{e}")


@admin_router.message(Command("access_false"), IsAdmin(ADMINS))
async def access_true(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    command_args: str = command.args
    db_repo = await db.get_repository()
    try:
        if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/access_true 123456789")
            return
        user = await db_repo.get_user(int(command_args))
        user.access = "FALSE"
        await db_repo.update_user(user)
        await message.answer("Доступ пользователю запрещен!")
    except Exception as e:
        logging.warning(e)
        await message.answer(f"ошибка\n\n{e}")


@admin_router.message(Command("add_admin"), IsAdmin(ADMINS))
async def add_admin(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    command_args: str = command.args
    if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/access_true 123456789")
            return
    ADMINS.append(command_args)
    await message.answer("Администратор добавлен!")


@admin_router.message(Command("del_admin"), IsAdmin(ADMINS))
async def add_admin(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    command_args: str = command.args
    if command_args in ADMINS:
        ADMINS.remove(command_args)
        await message.answer("Администратор удален!")
        return
    await message.answer("Администратор с таким id не найден!")
