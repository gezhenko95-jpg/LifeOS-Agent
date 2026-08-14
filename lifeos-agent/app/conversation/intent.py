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
    RECALL = "recall"
    COMPLETE_TASK = "complete_task"
    DELETE_TASK = "delete_task"
    LIST_HABITS = "list_habits"
    HABIT_DONE = "habit_done"
    JOURNAL_ENTRY = "journal_entry"
    ADD_WATCHLIST_ITEM = "add_watchlist_item"
    HELP = "help"


@dataclass
class ParsedIntent:
    intent: Intent
    title: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "normal"
    recurrence: Optional[str] = None  # только для ADD_TASK: daily|weekly|monthly
    media_type: Optional[str] = None  # только для ADD_WATCHLIST_ITEM: movie|book|other
