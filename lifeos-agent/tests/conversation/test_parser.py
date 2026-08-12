from app.conversation.intent import Intent
from app.conversation.parser import parse_intent


def test_add_task_with_date():
    result = parse_intent("Завтра купить молоко")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "купить молоко"
    assert result.due_date is not None


def test_add_task_without_date():
    result = parse_intent("Купить молоко")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "Купить молоко"
    assert result.due_date is None
    assert result.priority == "normal"


def test_add_task_with_high_priority_keyword():
    result = parse_intent("Важно позвонить в банк завтра")

    assert result.intent is Intent.ADD_TASK
    assert result.priority == "high"
    assert result.title == "позвонить в банк"
    assert result.due_date is not None


def test_add_task_with_urgent_keyword():
    result = parse_intent("Срочно закрыть отчет")

    assert result.intent is Intent.ADD_TASK
    assert result.priority == "high"
    assert result.title == "закрыть отчет"


def test_list_tasks_ru():
    result = parse_intent("Покажи задачи")

    assert result.intent is Intent.LIST_TASKS


def test_list_tasks_my_tasks_phrase():
    result = parse_intent("Мои задачи на сегодня")

    assert result.intent is Intent.LIST_TASKS


def test_list_tasks_command():
    result = parse_intent("/tasks")

    assert result.intent is Intent.LIST_TASKS


def test_complete_task():
    result = parse_intent("Выполнил купить молоко")

    assert result.intent is Intent.COMPLETE_TASK
    assert result.title == "купить молоко"


def test_complete_task_alternate_keyword():
    result = parse_intent("Готово, молоко купил")

    assert result.intent is Intent.COMPLETE_TASK


def test_delete_task():
    result = parse_intent("Удали молоко")

    assert result.intent is Intent.DELETE_TASK
    assert result.title == "молоко"


def test_help_command():
    result = parse_intent("/help")

    assert result.intent is Intent.HELP


def test_help_phrase():
    result = parse_intent("Что ты умеешь?")

    assert result.intent is Intent.HELP


def test_list_habits():
    result = parse_intent("Привычки")

    assert result.intent is Intent.LIST_HABITS


def test_habit_done():
    result = parse_intent("Привычка чтение")

    assert result.intent is Intent.HABIT_DONE
    assert result.title == "чтение"


def test_habit_done_is_checked_before_complete_task():
    # "сделал" — это COMPLETE_KEYWORD, но фраза с "привычка" должна
    # распознаваться как HABIT_DONE, а не COMPLETE_TASK
    result = parse_intent("Привычка сделал зарядку")

    assert result.intent is Intent.HABIT_DONE


def test_journal_entry_with_colon():
    result = parse_intent("Дневник: сегодня был продуктивный день")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title == "сегодня был продуктивный день"


def test_journal_entry_alternate_keyword():
    result = parse_intent("Рефлексия: закончил важный проект")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title == "закончил важный проект"


def test_journal_entry_two_word_keyword():
    result = parse_intent("Итоги дня: всё получилось")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title == "всё получилось"


def test_journal_entry_empty_content():
    result = parse_intent("Дневник")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title is None


def test_journal_keyword_in_the_middle_is_not_journal_entry():
    # "дневник" не в начале сообщения — это обычная задача, а не рефлексия
    result = parse_intent("Купить дневник для дочери")

    assert result.intent is Intent.ADD_TASK
