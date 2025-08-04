from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel
import pytz
import asyncpg

class User(BaseModel):
    id: int
    goal: str
    plan: Optional[Dict[str, Dict]] = None
    messages: Optional[List[Dict]] = None
    access: bool = False
    created_at: datetime = datetime.now(pytz.timezone('Europe/Moscow'))

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }
