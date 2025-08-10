import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandObject
from handlers.current_plan_handler import check_plan
from database.core import db
from database.models import User


admin_router = Router()

@admin_router.message(F.text == "⚙️ Админ панель")
async def get_admin_panel(message: Message, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user or not user.is_admin:
        return
    await message.answer("Команды для админа:\n\n"
                   "/access_true + *id пользователя* выдает юзеру доступ к боту\n\n"
                   "/access_false + *id пользователя* забирает у пользователя доступ\n\n"
                   "/add_admin + *id пользователя* добавляет админа с указаным id\n\n"
                   "/del_admin + *id пользователя* удаляет админа\n\n"
                   "/check_appeals позволяет проверять обращения пользователя в поддержку (В разработке!)")

@admin_router.message(Command("access_true"))
async def access_true(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user or not user.is_admin:
        return
    command_args: str = command.args
    db_repo = await db.get_repository()
    try:
        if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/access_true 123456789")
            return
        user = await db_repo.get_user(int(command_args))
        if not user:
            await message.answer("Кажется, пользователя с таким id не существует.")
            user = User(
                    id=message.from_user.id,
                    goal="",
                    stages_plan=None,
                    substages_plan = None,
                    messages=None,
                    access=True,
                    is_admin=False
                )
            await db_repo.create_user(user)
            await message.answer("Был создан новый пользователь с правами доступом к боту!")
            return
        user.access = True
        await db_repo.update_user(user)
        await message.answer("Доступ выдан успешно!")
    except Exception as e:
        logging.warning(e)
        await message.answer(f"ошибка\n\n{e}")


@admin_router.message(Command("access_false"))
async def access_true(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user or not user.is_admin:
        return
    command_args: str = command.args
    db_repo = await db.get_repository()
    try:
        if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/access_false 123456789")
            return
        user = await db_repo.get_user(int(command_args))
        user.access = False
        await db_repo.update_user(user)
        await message.answer("Доступ пользователю запрещен!")
    except Exception as e:
        logging.warning(e)
        await message.answer(f"ошибка\n\n{e}")


@admin_router.message(Command("add_admin"))
async def add_admin(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user or not user.is_admin:
        return
    command_args: str = command.args
    if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/add_admin 123456789")
            return
    db_repo = await db.get_repository()
    new_admin = await db_repo.get_user(int(command_args))
    if not new_admin:
        await message.answer("Кажется, пользователя с таким id не существует.")
        user = User(
                id=message.from_user.id,
                goal="",
                stages_plan=None,
                substages_plan = None,
                messages=None,
                access=False,
                is_admin=True
            )
        await db_repo.create_user(user)
        await message.answer("Был создан новый пользователь с правами администратора!")
        return
    new_admin.is_admin = True
    await db_repo.update_user(new_admin)
    await message.answer("Администратор добавлен!")


@admin_router.message(Command("del_admin"))
async def remove_admin(message: Message, command: CommandObject, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
        return
    command_args: str = command.args
    if not command.args or not command.args.isdigit():
            await message.answer("Пожалуйста, укажите ID пользователя числом, например:\n/remove_admin 123456789")
            return
    
    db_repo = await db.get_repository()
    old_admin = await db_repo.get_user(int(command_args))
    if not old_admin or not old_admin.is_admin:
        await message.answer("Кажется, пользователя с таким id не существует или он не является администратором.")
        return
    old_admin.is_admin = False
    await db_repo.update_user(old_admin)
    await message.answer("Администратор удален!")
