from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel
import pytz
import asyncpg

class User(BaseModel):
    id: int
    goal: Optional[str] = None
    plan: Optional[Dict[str, Dict]] = None
    messages: Optional[List[Dict]] = None
    question_dialog: Optional[List[Dict]] = None
    access: bool = False
    created_at: datetime = datetime.now(pytz.timezone('Europe/Moscow'))

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


class UserTask(BaseModel):
    id: int
    current_step: int = 0
    reminder_time: int = 12
    deadlines: Optional[List[datetime]] = None

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }
