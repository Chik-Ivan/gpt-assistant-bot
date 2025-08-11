import requests
import logging
from typing import List, Dict
from database.core import db
from database.models import User
from config import TOKEN_FOR_API

def fetch_all_users(chat_id: int, category_id: int) -> List[Dict]:
    all_users = []
    page = 1
    while True:
        url = f"https://api.puzzlebot.top/?token={TOKEN_FOR_API}&method=getUsersInChat&chat_id={chat_id}&page={page}&category_id={category_id}"
        response = requests.get(url)
        if response.status_code != 200:
            logging.error(f"Ошибка на странице {page}: {response.text}")
            break
        data = response.json()
        users = data.get('data', [])
        if not users:
            break
        all_users.extend(users)
        if len(users) < 200:
            break
        page += 1
    
    return all_users

async def get_access():
    chat_id = 7380235442
    category_id = 761552
    
    users_from_api = fetch_all_users(chat_id, category_id)
    logging.info(f"Получено пользователей с категорией доступа к боту: {len(users_from_api)}")
    db_repo = await db.get_repository()
    users_from_db = await db_repo.get_all_users()

    api_user_ids = {user["user_id"] for user in users_from_api}
    db_user_ids = {user.id for user in users_from_db}

    
    for new_user_id in api_user_ids:
        user = await db_repo.get_user(new_user_id)
        if user:
            if user.access:
                continue
            user.access = True
            user.last_access = None
            await db_repo.update_user(user)
            continue
        user = User(
            id=new_user_id,
            goal=None,
            stages_plan=None,
            substages_plan = None,
            messages=None,
            access=True,
            is_admin=False,
            last_access=None
        )
        await db_repo.create_user(user)
    
    removed_users = db_user_ids - api_user_ids
    if removed_users:
        await db_repo.bulk_update_access(removed_users, False)


async def delete_users():
    db_repo = await db.get_repository()
    await db_repo.delete_old_users()
    