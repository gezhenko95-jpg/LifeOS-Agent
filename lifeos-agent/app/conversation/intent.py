"""
Типы намерений пользователя.

Rule-based парсер (см. parser.py) сейчас единственный, кто создает
ParsedIntent, но контракт спроектирован так, чтобы позже это мог делать
AI Service (LLM) без изменений в Telegram-слое.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    ADD_TASK = "add_task"
    LIST_TASKS = "list_tasks"
    QUERY_TASKS_BY_DATE = "query_tasks_by_date"
    COMPLETE_TASK = "complete_task"
    DELETE_TASK = "delete_task"
    LIST_HABITS = "list_habits"
    HABIT_DONE = "habit_done"
    JOURNAL_ENTRY = "journal_entry"
    HELP = "help"


@dataclass
class ParsedIntent:
    intent: Intent
    title: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "normal"
