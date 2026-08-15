from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.conversation.engine import ConversationEngine


@pytest.fixture
def task_service():
    return AsyncMock()


@pytest.fixture
def habit_service():
    return AsyncMock()


@pytest.fixture
def memory_service():
    return AsyncMock()


@pytest.fixture
def goal_service():
    return AsyncMock()


@pytest.fixture
def pending_prompt_service():
    return AsyncMock()


@pytest.fixture
def watchlist_service():
    return AsyncMock()


async def test_add_task_without_date(task_service, habit_service, memory_service):
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Купить молоко" in reply
    assert "❗" not in reply
    task_service.create_task.assert_awaited_once_with(
        1, "Купить молоко", None, "normal", None
    )


async def test_add_task_with_date_shown_in_reply(
    task_service, habit_service, memory_service
):
    from datetime import datetime

    due = datetime(2026, 8, 13, 9, 0)
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=due, priority="normal", recurrence=None
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Завтра купить молоко")

    assert "13.08" in reply


async def test_add_task_with_high_priority_marker(
    task_service, habit_service, memory_service
):
    task_service.create_task.return_value = SimpleNamespace(
        title="Позвонить в банк", due_date=None, priority="high", recurrence=None
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Важно позвонить в банк")

    assert "❗" in reply
    task_service.create_task.assert_awaited_once_with(
        1, "позвонить в банк", None, "high", None
    )


async def test_add_recurring_task_shows_recurrence_marker(
    task_service, habit_service, memory_service
):
    from datetime import datetime

    task_service.create_task.return_value = SimpleNamespace(
        title="Оплатить интернет",
        due_date=datetime(2026, 8, 17, 9, 0),
        priority="normal",
        recurrence="weekly",
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Каждый понедельник оплатить интернет")

    assert "🔁" in reply
    task_service.create_task.assert_awaited_once()
    args = task_service.create_task.await_args.args
    assert args[4] == "weekly"


async def test_add_task_empty_title_does_not_call_service(
    task_service, habit_service, memory_service
):
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Завтра")

    task_service.create_task.assert_not_awaited()
    assert "Не понял" in reply


async def test_list_tasks_empty(task_service, habit_service, memory_service):
    task_service.list_active_tasks.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "покажи задачи")

    assert reply == "Активных задач нет."


async def test_list_tasks_with_items(task_service, habit_service, memory_service):
    task_service.list_active_tasks.return_value = [
        SimpleNamespace(title="Купить молоко", due_date=None, priority="high"),
        SimpleNamespace(title="Позвонить маме", due_date=None, priority="normal"),
    ]
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "покажи задачи")

    assert "1. ❗ Купить молоко" in reply
    assert "2. Позвонить маме" in reply


async def test_query_tasks_by_date_filters_only_matching_date(
    task_service, habit_service, memory_service
):
    tomorrow = datetime.now().astimezone() + timedelta(days=1)
    other_day = datetime.now().astimezone() + timedelta(days=5)
    task_service.list_active_tasks.return_value = [
        SimpleNamespace(title="Купить молоко", due_date=tomorrow, priority="normal"),
        SimpleNamespace(title="Сдать отчёт", due_date=other_day, priority="normal"),
        SimpleNamespace(title="Без даты", due_date=None, priority="normal"),
    ]
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Что на завтра?")

    assert "Купить молоко" in reply
    assert "Сдать отчёт" not in reply
    assert "Без даты" not in reply
    assert f"{tomorrow:%d.%m.%Y}" in reply


async def test_query_tasks_by_date_empty(task_service, habit_service, memory_service):
    task_service.list_active_tasks.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Что я собирался сделать завтра?")

    assert "задач нет" in reply


async def test_query_tasks_by_date_shows_priority_marker(
    task_service, habit_service, memory_service
):
    tomorrow = datetime.now().astimezone() + timedelta(days=1)
    task_service.list_active_tasks.return_value = [
        SimpleNamespace(title="Позвонить в банк", due_date=tomorrow, priority="high"),
    ]
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Что на завтра?")

    assert "❗ Позвонить в банк" in reply


async def test_recall_with_results(task_service, habit_service, memory_service):
    memory_service.search.return_value = [
        SimpleNamespace(content="Хочу съездить в отпуск в сентябре"),
    ]
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Напомни про отпуск")

    assert "Хочу съездить в отпуск в сентябре" in reply
    memory_service.search.assert_awaited_once_with(1, "отпуск")


async def test_recall_no_results(task_service, habit_service, memory_service):
    memory_service.search.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Напомни про единорогов")

    assert "Ничего не нашёл" in reply


async def test_recall_empty_query_asks_what(
    task_service, habit_service, memory_service
):
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Вспомни")

    assert "Что напомнить" in reply
    memory_service.search.assert_not_awaited()


async def test_recall_falls_back_to_semantic_search_when_literal_empty(
    task_service, habit_service, memory_service
):
    memory_service.search.return_value = []
    memory_service.semantic_search.return_value = [
        SimpleNamespace(content="Думаю уволиться и сменить сферу"),
    ]
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service, habit_service, memory_service, ai_client=ai_client
    )

    reply = await engine.handle_message(1, "Напомни про смену работы")

    assert "Думаю уволиться и сменить сферу" in reply
    assert "Точных совпадений" in reply
    memory_service.semantic_search.assert_awaited_once_with(
        1, "смену работы", ai_client
    )


async def test_recall_skips_semantic_search_when_literal_found_results(
    task_service, habit_service, memory_service
):
    memory_service.search.return_value = [SimpleNamespace(content="Найдено буквально")]
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service, habit_service, memory_service, ai_client=ai_client
    )

    reply = await engine.handle_message(1, "Напомни про отпуск")

    assert "Найдено буквально" in reply
    memory_service.semantic_search.assert_not_awaited()


async def test_recall_no_semantic_fallback_without_ai_client(
    task_service, habit_service, memory_service
):
    memory_service.search.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Напомни про единорогов")

    assert "Ничего не нашёл" in reply
    memory_service.semantic_search.assert_not_awaited()


async def test_complete_task_found(task_service, habit_service, memory_service):
    task = SimpleNamespace(title="Купить молоко", recurrence=None)
    task_service.find_active_by_title.return_value = [task]
    task_service.complete_task_by_title.return_value = task
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Выполнил молоко")

    assert "сделано" in reply
    assert "Под «" not in reply
    task_service.complete_task_by_title.assert_awaited_once_with(1, "молоко")


async def test_complete_recurring_task_mentions_next_occurrence(
    task_service, habit_service, memory_service
):
    task = SimpleNamespace(title="Пить воду", recurrence="daily")
    task_service.find_active_by_title.return_value = [task]
    task_service.complete_task_by_title.return_value = task
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Выполнил пить воду")

    assert "сделано" in reply
    assert "повторится автоматически" in reply


async def test_complete_task_not_found(task_service, habit_service, memory_service):
    task_service.find_active_by_title.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Выполнил молоко")

    assert "Не нашёл" in reply
    task_service.complete_task_by_title.assert_not_awaited()


async def test_complete_task_ambiguous_lists_other_matches(
    task_service, habit_service, memory_service
):
    task = SimpleNamespace(title="Купить молоко", recurrence=None)
    other = SimpleNamespace(title="Купить молоко и хлеб")
    task_service.find_active_by_title.return_value = [task, other]
    task_service.complete_task_by_title.return_value = task
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Выполнил молоко")

    assert "сделано" in reply
    assert "Купить молоко и хлеб" in reply


async def test_delete_task_found(task_service, habit_service, memory_service):
    task = SimpleNamespace(title="Купить молоко")
    task_service.find_active_by_title.return_value = [task]
    task_service.delete_task_by_title.return_value = task
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Удали молоко")

    assert "Удалил" in reply
    assert "Под «" not in reply


async def test_delete_task_not_found(task_service, habit_service, memory_service):
    task_service.find_active_by_title.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Удали молоко")

    assert "Не нашёл" in reply
    task_service.delete_task_by_title.assert_not_awaited()


async def test_help(task_service, habit_service, memory_service):
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "/help")

    assert "умею" in reply


async def test_list_habits_empty(task_service, habit_service, memory_service):
    habit_service.list_active_habits.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "привычки")

    assert reply == "Активных привычек нет."


async def test_list_habits_with_streak(task_service, habit_service, memory_service):
    habit_service.list_active_habits.return_value = [
        SimpleNamespace(title="Читать", id=1),
        SimpleNamespace(title="Спорт", id=2),
    ]
    habit_service.get_streaks_bulk.return_value = {1: 3, 2: 0}
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "привычки")

    assert "1. Читать — 🔥 3 дней подряд" in reply
    assert "2. Спорт" in reply
    assert "Спорт — 🔥" not in reply


async def test_habit_done_found(task_service, habit_service, memory_service):
    habit = SimpleNamespace(title="Читать", id=1)
    habit_service.find_active_by_title.return_value = [habit]
    habit_service.mark_done_today.return_value = habit
    habit_service.get_streak.return_value = 1
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Привычка читать")

    assert "подряд" in reply
    assert "🔥" in reply and "1 дн" in reply
    habit_service.mark_done_today.assert_awaited_once_with(1, "читать")


async def test_habit_done_celebrates_streak_milestone(
    task_service, habit_service, memory_service
):
    habit = SimpleNamespace(title="Читать", id=1)
    habit_service.find_active_by_title.return_value = [habit]
    habit_service.mark_done_today.return_value = habit
    habit_service.get_streak.return_value = 7
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Привычка читать")

    assert "🎉" in reply
    # Число серии называется строкой выше — юбилей его не повторяет.
    assert reply.count("7") == 1


async def test_habit_done_no_celebration_outside_milestone(
    task_service, habit_service, memory_service
):
    habit = SimpleNamespace(title="Читать", id=1)
    habit_service.find_active_by_title.return_value = [habit]
    habit_service.mark_done_today.return_value = habit
    habit_service.get_streak.return_value = 8
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Привычка читать")

    assert "🎉" not in reply


async def test_habit_done_not_found(task_service, habit_service, memory_service):
    habit_service.find_active_by_title.return_value = []
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Привычка читать")

    assert "Не нашёл" in reply
    habit_service.mark_done_today.assert_not_awaited()


async def test_journal_entry_saved_to_memory(
    task_service, habit_service, memory_service
):
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Дневник: продуктивный день")

    assert reply == "📝 Записал в дневник."
    from app.memory.models import MemoryType

    memory_service.save.assert_awaited_once_with(
        1, MemoryType.JOURNAL, "продуктивный день", source="telegram"
    )


async def test_journal_entry_empty_content_asks_to_reformulate(
    task_service, habit_service, memory_service
):
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Дневник")

    assert "Что записать" in reply
    memory_service.save.assert_not_awaited()


async def test_ai_fallback_not_used_when_client_not_configured(
    task_service, habit_service, memory_service, monkeypatch
):
    called = AsyncMock()
    monkeypatch.setattr("app.conversation.engine.parse_intent_with_ai", called)
    engine = ConversationEngine(
        task_service, habit_service, memory_service, ai_client=None
    )

    reply = await engine.handle_message(1, "Завтра")

    called.assert_not_called()
    assert "Не понял" in reply


async def test_ai_fallback_used_when_rule_based_fails(
    task_service, habit_service, memory_service, monkeypatch
):
    from app.conversation.intent import Intent, ParsedIntent

    fake_ai_client = AsyncMock()
    monkeypatch.setattr(
        "app.conversation.engine.parse_intent_with_ai",
        AsyncMock(
            return_value=ParsedIntent(
                intent=Intent.ADD_TASK, title="День рождения сестры", due_date=None
            )
        ),
    )
    task_service.create_task.return_value = SimpleNamespace(
        title="День рождения сестры", due_date=None, priority="normal", recurrence=None
    )
    engine = ConversationEngine(
        task_service, habit_service, memory_service, ai_client=fake_ai_client
    )

    reply = await engine.handle_message(1, "Завтра")

    task_service.create_task.assert_awaited_once_with(
        1, "День рождения сестры", None, "normal", None
    )
    assert "День рождения сестры" in reply


async def test_pending_prompt_answer_creates_goal(
    task_service,
    habit_service,
    memory_service,
    goal_service,
    pending_prompt_service,
    monkeypatch,
):
    from app.proactive.ai_extract import PromptAnswer

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="goal",
        question_text="Какая у тебя цель?",
        asked_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "app.conversation.engine.extract_prompt_answer",
        AsyncMock(return_value=PromptAnswer(action="create_goal", title="Марафон")),
    )
    goal_service.create_goal.return_value = SimpleNamespace(title="Марафон")
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Хочу пробежать марафон")

    assert "Марафон" in reply
    goal_service.create_goal.assert_awaited_once_with(1, "Марафон", None)
    pending_prompt_service.clear.assert_awaited_once_with(1)
    task_service.create_task.assert_not_awaited()


async def test_pending_prompt_answer_creates_habit(
    task_service,
    habit_service,
    memory_service,
    goal_service,
    pending_prompt_service,
    monkeypatch,
):
    from app.proactive.ai_extract import PromptAnswer

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="habit",
        question_text="Какую привычку хочешь завести?",
        asked_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "app.conversation.engine.extract_prompt_answer",
        AsyncMock(return_value=PromptAnswer(action="create_habit", title="Медитация")),
    )
    habit_service.create_habit.return_value = SimpleNamespace(title="Медитация")
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Хочу медитировать")

    assert "Медитация" in reply
    habit_service.create_habit.assert_awaited_once_with(1, "Медитация")
    pending_prompt_service.clear.assert_awaited_once_with(1)


async def test_pending_prompt_answer_saves_memory(
    task_service,
    habit_service,
    memory_service,
    goal_service,
    pending_prompt_service,
    monkeypatch,
):
    from app.memory.models import MemoryType
    from app.proactive.ai_extract import PromptAnswer

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="preference",
        question_text="Что мне о тебе запомнить?",
        asked_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "app.conversation.engine.extract_prompt_answer",
        AsyncMock(
            return_value=PromptAnswer(
                action="save_memory",
                memory_type="preference",
                content="Утренний человек",
            )
        ),
    )
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Я лучше работаю утром")

    assert "Утренний человек" in reply
    memory_service.save.assert_awaited_once_with(
        1, MemoryType.PREFERENCE, "Утренний человек", source="proactive_prompt"
    )
    pending_prompt_service.clear.assert_awaited_once_with(1)


async def test_pending_prompt_unrelated_falls_back_to_add_task(
    task_service,
    habit_service,
    memory_service,
    goal_service,
    pending_prompt_service,
    monkeypatch,
):
    from app.proactive.ai_extract import PromptAnswer

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="goal",
        question_text="Какая у тебя цель?",
        asked_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "app.conversation.engine.extract_prompt_answer",
        AsyncMock(return_value=PromptAnswer(action="unrelated")),
    )
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Купить молоко" in reply
    task_service.create_task.assert_awaited_once()
    pending_prompt_service.clear.assert_not_awaited()
    # Вопрос задан только что — пользователь должен узнать, что бот не
    # понял его ответ (см. историю с "Сохрани лес")
    assert "Не понял это как ответ на «Какая у тебя цель?»" in reply


async def test_pending_prompt_unrelated_stale_question_no_note(
    task_service,
    habit_service,
    memory_service,
    goal_service,
    pending_prompt_service,
    monkeypatch,
):
    from app.proactive.ai_extract import PromptAnswer

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="goal",
        question_text="Какая у тебя цель?",
        asked_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    monkeypatch.setattr(
        "app.conversation.engine.extract_prompt_answer",
        AsyncMock(return_value=PromptAnswer(action="unrelated")),
    )
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Купить молоко" in reply
    # Вопрос давно неактуален — не нагружаем пользователя пояснением
    assert "Не понял это как ответ" not in reply


async def test_no_open_pending_prompt_behaves_normally(
    task_service,
    habit_service,
    memory_service,
    goal_service,
    pending_prompt_service,
    monkeypatch,
):
    called = AsyncMock()
    monkeypatch.setattr("app.conversation.engine.extract_prompt_answer", called)
    pending_prompt_service.get_open.return_value = None
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    ai_client = AsyncMock()
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Купить молоко" in reply
    called.assert_not_called()


async def test_pending_prompt_service_not_configured_keeps_old_behavior(
    task_service,
    habit_service,
    memory_service,
    monkeypatch,
):
    called = AsyncMock()
    monkeypatch.setattr("app.conversation.engine.extract_prompt_answer", called)
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    engine = ConversationEngine(
        task_service, habit_service, memory_service, ai_client=AsyncMock()
    )  # pending_prompt_service не передан — как в проде до этой фичи

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Купить молоко" in reply
    called.assert_not_called()


async def test_journal_capture_fresh_pending_saves_verbatim(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    from app.memory.models import MemoryType

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Что запишем в дневник?",
        asked_at=datetime.now(timezone.utc),
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )  # ai_client не передан — журнал не должен его требовать вообще

    reply = await engine.handle_message(1, "Сегодня выполнил кучу дел, устал")

    assert reply == "📝 Записал в дневник."
    memory_service.save.assert_awaited_once_with(
        1,
        MemoryType.JOURNAL,
        "Сегодня выполнил кучу дел, устал",
        source="quick_capture",
    )
    pending_prompt_service.clear.assert_awaited_once_with(1)
    task_service.create_task.assert_not_awaited()


async def test_journal_capture_intercepts_before_keyword_matching(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    """Регрессия: текст со словом 'выполнил' внутри длинной фразы раньше
    (до перехвата ДО parse_intent) улетал бы в COMPLETE_TASK вместо
    дневника — см. specs/006-proactive-engagement.md."""
    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Что тебе снилось?",
        asked_at=datetime.now(timezone.utc),
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(
        1, "Мне снилось, что я выполнил привычка какую-то марафонскую дистанцию"
    )

    assert reply == "📝 Записал в дневник."
    memory_service.save.assert_awaited_once()
    task_service.complete_task_by_title.assert_not_awaited()


async def test_journal_capture_stale_pending_falls_back_to_normal_processing(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Что тебе снилось?",
        asked_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Добавил задачу" in reply
    assert "Записал в дневник" not in reply
    task_service.create_task.assert_awaited_once()
    memory_service.save.assert_not_awaited()
    pending_prompt_service.clear.assert_not_awaited()


async def test_journal_category_ignored_when_no_pending_service(
    task_service, habit_service, memory_service
):
    task_service.create_task.return_value = SimpleNamespace(
        title="Купить молоко", due_date=None, priority="normal", recurrence=None
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "Купить молоко")

    assert "Добавил задачу" in reply
    memory_service.save.assert_not_awaited()


async def test_ai_fallback_failure_keeps_old_message(
    task_service, habit_service, memory_service, monkeypatch
):
    fake_ai_client = AsyncMock()
    monkeypatch.setattr(
        "app.conversation.engine.parse_intent_with_ai", AsyncMock(return_value=None)
    )
    engine = ConversationEngine(
        task_service, habit_service, memory_service, ai_client=fake_ai_client
    )

    reply = await engine.handle_message(1, "Завтра")

    task_service.create_task.assert_not_awaited()
    assert "Не понял" in reply


# --- ADD_WATCHLIST_ITEM -------------------------------------------------


async def test_add_watchlist_item(
    task_service, habit_service, memory_service, watchlist_service
):
    watchlist_service.create_item.return_value = SimpleNamespace(
        title="Дюна", media_type="movie"
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        watchlist_service=watchlist_service,
    )

    reply = await engine.handle_message(1, "посмотреть фильм Дюна")

    watchlist_service.create_item.assert_awaited_once_with(1, "Дюна", "movie")
    assert reply == "🎬 Добавил в список: «Дюна»"


async def test_add_watchlist_item_book_emoji(
    task_service, habit_service, memory_service, watchlist_service
):
    watchlist_service.create_item.return_value = SimpleNamespace(
        title="Дюна", media_type="book"
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        watchlist_service=watchlist_service,
    )

    reply = await engine.handle_message(1, "прочитать книгу Дюна")

    assert "📖" in reply


async def test_add_watchlist_item_empty_title(
    task_service, habit_service, memory_service, watchlist_service
):
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        watchlist_service=watchlist_service,
    )

    reply = await engine.handle_message(1, "посмотреть фильм")

    watchlist_service.create_item.assert_not_awaited()
    assert "Что посмотреть" in reply


async def test_add_watchlist_item_without_service_falls_back_to_task(
    task_service, habit_service, memory_service
):
    task_service.create_task.return_value = SimpleNamespace(
        title="Дюна", due_date=None, priority="normal", recurrence=None
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "посмотреть фильм Дюна")

    task_service.create_task.assert_awaited_once()
    assert "Добавил задачу" in reply


# --- LIST_WATCHLIST ------------------------------------------------------


async def test_list_watchlist_with_items(
    task_service, habit_service, memory_service, watchlist_service
):
    watchlist_service.list_active_items.return_value = [
        SimpleNamespace(title="Дюна", media_type="movie"),
        SimpleNamespace(title="1984", media_type="book"),
    ]
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        watchlist_service=watchlist_service,
    )

    reply = await engine.handle_message(1, "список книг")

    assert "Дюна" in reply
    assert "1984" in reply


async def test_list_watchlist_empty(
    task_service, habit_service, memory_service, watchlist_service
):
    watchlist_service.list_active_items.return_value = []
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        watchlist_service=watchlist_service,
    )

    reply = await engine.handle_message(1, "полка")

    assert "нечего" in reply


async def test_list_watchlist_without_service(
    task_service, habit_service, memory_service
):
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "список фильмов")

    assert "нечего" in reply


async def test_command_is_not_swallowed_by_open_journal_prompt(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    """Регрессия из боевой БД: при открытом дневниковом вопросе /help
    сохранялся как запись {"type": "journal", "content": "/help"}, а
    справка не показывалась вообще (см. AUDIT.md, B-1)."""
    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Что запишем в дневник?",
        asked_at=datetime.now(timezone.utc),
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "/help")

    assert "Я умею" in reply
    memory_service.save.assert_not_awaited()
    # Вопрос остаётся открытым: пользователь спросил справку, а не
    # отказался отвечать на дневник.
    pending_prompt_service.clear.assert_not_awaited()


async def test_journal_still_captures_text_that_merely_contains_a_slash(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    """Слэш внутри фразы — не команда, это обычная дневниковая запись."""
    from app.memory.models import MemoryType

    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Как прошёл день?",
        asked_at=datetime.now(timezone.utc),
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(1, "Работал 9/10 часов, вымотался")

    assert reply == "📝 Записал в дневник."
    memory_service.save.assert_awaited_once_with(
        1, MemoryType.JOURNAL, "Работал 9/10 часов, вымотался", source="quick_capture"
    )


# --- ответ должен называть время, если оно задано (жалоба владельца) ---


def test_format_due_date_shows_time_when_set():
    from datetime import datetime as dt

    from app.tasks.formatting import format_due_date

    assert format_due_date(dt(2026, 8, 16, 19, 0)) == "16.08.2026 в 19:00"
    assert format_due_date(dt(2026, 8, 16, 3, 22)) == "16.08.2026 в 03:22"


def test_format_due_date_shows_default_hour_too():
    """Прятать 9:00 (значение по умолчанию) заманчиво, но тогда у явного
    «в пятницу в 9» время исчезало бы из ответа — ровно в том случае,
    когда пользователь назвал его сам."""
    from datetime import datetime as dt

    from app.tasks.formatting import format_due_date

    assert format_due_date(dt(2026, 8, 16, 9, 0)) == "16.08.2026 в 09:00"


async def test_add_task_reply_names_the_time(
    task_service, habit_service, memory_service
):
    from app.tasks.models import Task

    task_service.create_task.return_value = Task(
        id=1,
        telegram_user_id=1,
        title="позвонить маме",
        # Наивная дата: to_local оставляет её как есть, поэтому тест
        # не зависит от таймзоны машины, на которой запущен.
        due_date=datetime(2026, 8, 16, 19, 0),
        status="active",
        priority="normal",
    )
    engine = ConversationEngine(task_service, habit_service, memory_service)

    reply = await engine.handle_message(1, "напомни в 19:00 позвонить маме")

    assert reply == "Добавил задачу: «позвонить маме»\n🕘 завтра в 19:00"


async def test_reminder_is_not_swallowed_by_open_journal_prompt(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    """Регрессия из живого использования: при открытом дневниковом
    вопросе «напомни сегодня в 9 утра запустить стиралку» уходило в
    дневник, и напоминание не создавалось вовсе (см. AUDIT.md, B-1)."""
    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Что запишем в дневник?",
        asked_at=datetime.now(timezone.utc),
    )
    from app.tasks.models import Task

    task_service.create_task.return_value = Task(
        id=1,
        telegram_user_id=1,
        title="запустить стиралку",
        due_date=datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc),
        status="active",
        priority="normal",
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(
        1, "напомни сегодня в 9 утра запустить стиралку"
    )

    assert "Добавил задачу" in reply
    memory_service.save.assert_not_awaited()
    task_service.create_task.assert_awaited_once()


async def test_journal_still_captures_prose_containing_command_words(
    task_service, habit_service, memory_service, goal_service, pending_prompt_service
):
    """Отсекаем только НАЧАЛО сообщения: «напомни» посреди прозы — обычное
    слово, такая запись должна остаться дневниковой."""
    pending_prompt_service.get_open.return_value = SimpleNamespace(
        category="journal",
        question_text="Как прошёл день?",
        asked_at=datetime.now(timezone.utc),
    )
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        goal_service=goal_service,
        pending_prompt_service=pending_prompt_service,
    )

    reply = await engine.handle_message(
        1, "Весь день крутилось в голове, надо напомни себе не тянуть с отчётом"
    )

    assert reply == "📝 Записал в дневник."
    memory_service.save.assert_awaited_once()
