
from aiogram.dispatcher.filters.state import State, StatesGroup

class GoalStates(StatesGroup):
    waiting_for_goal = State()
    waiting_for_reason = State()
    waiting_for_deadline = State()