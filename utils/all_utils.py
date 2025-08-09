import re
from datetime import datetime

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return ""

def extract_days(text: str) -> int:
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if (numbers and 1 <= numbers[0] <= 7) else 7


def parse_plan(plan_text: str) -> dict:
    result = {}
    weeks = re.split(r'\n*Неделя \d+:\n', plan_text)
    week_titles = re.findall(r'Неделя \d+:', plan_text)
    
    for i, week_content in enumerate(weeks[1:]):
        week_key = week_titles[i].strip(':')
        result[week_key] = {}
        
        actions = re.findall(r'- (\w+): (.+)', week_content)
        for action, description in actions:
            result[week_key][action] = description.strip()
    return result

def extract_number(text: str) -> int | None:
    match = re.search(r'\b(\d+)\b', text)
    if match:
        return int(match.group(1))
    else:
        return None
    
def extract_date_from_string(text: str) -> datetime:
    date_pattern = r"\b(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})\b"
    match = re.search(date_pattern, text)
    
    if not match:
        raise ValueError(f"Дата не найдена в строке: '{text}'")
    
    day, month, year = match.groups()
    date_str = f"{day}.{month}.{year}"
    
    return datetime.strptime(date_str, "%d.%m.%Y").date()
