"""
Представление задач в тексте — общее для Conversation Engine и для
Telegram-клавиатур (по образцу app/insights/formatting.py).

Отдельный модуль, потому что одну и ту же задачу подтверждают в двух
местах: ConversationEngine._add_task (ответ на сообщение) и
keyboards.build_task_confirmation_message (ответ на нажатие кнопки).
Раньше формат дублировался и уже начал расходиться.
"""

from datetime import date, datetime, timedelta

from app.tasks.models import Task

# Статус задачи по сроку — цвет виден раньше, чем прочитан текст.
STATUS_OVERDUE = "🔴"
STATUS_TODAY = "🟠"
STATUS_TOMORROW = "🟡"
STATUS_LATER = "⚪"

_WEEKDAY_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def to_local(due_date: datetime) -> datetime:
    """Привести момент к локальному времени сервера (TZ=Europe/Moscow,
    см. docker-compose.yml).

    Обязательный шаг перед показом. В БД due_date лежит как timestamptz,
    и asyncpg возвращает его в UTC — без перевода «напомни в 9 утра»
    отвечало «в 06:00». Сама задача при этом создавалась верно, врал
    только текст, что хуже: пользователь видит неправильное время и не
    верит боту, хотя напоминание сработает вовремя.

    Наивные datetime (в тестах и в разборе без таймзоны) оставляем как
    есть — переводить нечего, а astimezone() на наивном объекте молча
    приписал бы ему локальную зону.
    """
    if due_date.tzinfo is None:
        return due_date
    return due_date.astimezone()


def format_due_date(due_date: datetime) -> str:
    """«16.08.2026 в 19:00» — всегда со временем, в местном времени.

    Владелец жаловался, что бот не говорит, на какое ВРЕМЯ создана
    задача: «напомни через пару часов» отвечало просто «на 15.08.2026»,
    и понять, когда сработает напоминание, было нельзя.

    Время показывается всегда, даже когда оно совпало с 9:00 по
    умолчанию (date_parser._DEFAULT_HOUR). Прятать именно это значение
    заманчиво — «на завтра» выглядит чище, чем «на завтра в 09:00», — но
    тогда у явного «в пятницу в 9» время исчезало бы из ответа, то есть
    ровно в том случае, когда пользователь назвал его сам. Момент
    срабатывания напоминания важнее лаконичности.
    """
    due_date = to_local(due_date)
    return f"{due_date:%d.%m.%Y} в {due_date:%H:%M}"


def format_due_human(due_date: datetime, today: date | None = None) -> str:
    """То же время, но человеческими словами: «сегодня в 19:00»,
    «завтра в 09:00», «пт, 21.08 в 09:00».

    Полная дата 16.08.2026 формально точнее, но в списке из пяти задач
    читателю приходится вычитать её из сегодняшнего числа в уме. Для
    ближайших дней слово быстрее цифры; дальше недели слово перестаёт
    помогать («через 12 дней» уже не ориентир), поэтому возвращается
    дата с днём недели.
    """
    due_date = to_local(due_date)
    today = today or date.today()
    due_day = due_date.date()
    clock = f"{due_date:%H:%M}"
    delta = (due_day - today).days

    if delta == 0:
        return f"сегодня в {clock}"
    if delta == 1:
        return f"завтра в {clock}"
    if delta == -1:
        return f"вчера в {clock}"
    if delta < 0:
        return f"{due_date:%d.%m} в {clock} (просрочено)"
    if delta < 7:
        return f"{_WEEKDAY_SHORT[due_day.weekday()]} в {clock}"
    return f"{_WEEKDAY_SHORT[due_day.weekday()]}, {due_date:%d.%m} в {clock}"


def task_created_prefix(task: Task) -> str:
    """«❗ Добавил задачу: «Название»» (без ❗ для обычного приоритета) —
    общая часть, собиравшаяся дословно в двух местах: ConversationEngine
    (ответ на сообщение) и keyboards.build_task_confirmation_message
    (ответ на нажатие кнопки). Суффикс (срок/повтор) у них разный —
    собирается отдельно на месте вызова."""
    prefix = "❗ " if task.priority == "high" else ""
    return f"{prefix}Добавил задачу: «{task.title}»"


def task_status_emoji(task: Task, today: date | None = None) -> str:
    """Кружок по срочности. Задача без срока — «когда-нибудь», это тоже
    состояние, а не отсутствие данных."""
    if task.due_date is None:
        return STATUS_LATER

    today = today or date.today()
    delta = (to_local(task.due_date).date() - today).days
    if delta < 0:
        return STATUS_OVERDUE
    if delta == 0:
        return STATUS_TODAY
    if delta == 1:
        return STATUS_TOMORROW
    return STATUS_LATER


def count_overdue(tasks: list[Task], today: date | None = None) -> int:
    today = today or date.today()
    return sum(
        1
        for t in tasks
        if t.due_date is not None and to_local(t.due_date).date() < today
    )


def is_due_soon(task: Task, within: timedelta = timedelta(hours=2)) -> bool:
    """Срок наступает совсем скоро — повод выделить задачу отдельно."""
    if task.due_date is None:
        return False
    left = task.due_date - datetime.now(task.due_date.tzinfo)
    return timedelta(0) <= left <= within
