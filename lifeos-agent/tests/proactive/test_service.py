"""
Тесты gap-detection приоритета в PendingPromptService (см.
specs/006-proactive-engagement.md). Репозитории/сервисы — AsyncMock, без
реальной БД (по образцу tests/habits/test_service.py).
"""

from unittest.mock import AsyncMock, Mock

from app.proactive.questions import (
    DREAM_QUESTIONS,
    GOAL_QUESTIONS,
    HABIT_QUESTIONS,
    MUSING_QUESTIONS,
    PREFERENCE_QUESTIONS,
    PROJECT_QUESTIONS,
)
from app.proactive.service import PendingPromptService


def _service(goals=None, habits=None, projects=None, preferences=None):
    repository = AsyncMock()
    repository.upsert.side_effect = lambda uid, category, text: AsyncMock(
        category=category, question_text=text
    )

    goal_service = AsyncMock()
    goal_service.list_active_goals.return_value = goals or []

    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = habits or []

    memory_service = AsyncMock()

    def _list_entries(telegram_user_id, type=None):
        from app.memory.models import MemoryType

        if type is MemoryType.PROJECT:
            return projects or []
        if type is MemoryType.PREFERENCE:
            return preferences or []
        return []

    memory_service.list_entries.side_effect = _list_entries

    return (
        PendingPromptService(repository, goal_service, habit_service, memory_service),
        repository,
    )


def _no_musing(monkeypatch):
    """Гарантировать, что pick_gap_question_if_any не добавит вторую
    строку — чтобы тесты gap-detection не зависели от random (musing
    тестируется отдельно ниже, через pick_morning_reflection — только
    она вызывает _with_musing)."""
    monkeypatch.setattr("app.proactive.service.random.random", lambda: 0.99)


# Приоритет gap-detection (goal → habit → project → preference → reflect)
# проверяется через pick_gap_question_if_any — единственный оставшийся
# публичный метод, напрямую делегирующий в _pick_question без побочной
# логики поверх (в отличие от pick_morning_reflection, который решает,
# гнать ли gap-ветку вообще, см. AUDIT.md, раздел 5 — pick_and_open
# держался только этими тестами и был удалён).


async def test_no_goals_asks_goal_question(monkeypatch):
    _no_musing(monkeypatch)
    service, repository = _service()

    question = await service.pick_gap_question_if_any(1)

    assert question in GOAL_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "goal", question)


async def test_has_goals_but_no_habits_asks_habit_question(monkeypatch):
    _no_musing(monkeypatch)
    service, repository = _service(goals=[object()])

    question = await service.pick_gap_question_if_any(1)

    assert question in HABIT_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "habit", question)


async def test_has_goals_and_habits_but_no_projects_asks_project_question(
    monkeypatch,
):
    _no_musing(monkeypatch)
    service, repository = _service(goals=[object()], habits=[object()])

    question = await service.pick_gap_question_if_any(1)

    assert question in PROJECT_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "project", question)


async def test_fewer_than_three_preferences_asks_preference_question(monkeypatch):
    _no_musing(monkeypatch)
    service, repository = _service(
        goals=[object()],
        habits=[object()],
        projects=[object()],
        preferences=[object(), object()],
    )

    question = await service.pick_gap_question_if_any(1)

    assert question in PREFERENCE_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "preference", question)


# "Всё заполнено" → category="reflect" → pick_gap_question_if_any
# возвращает None без upsert — уже покрыто
# test_pick_gap_question_if_any_returns_none_when_no_gap ниже
# (REFLECT_QUESTIONS в этом случае вычисляется в _pick_question, но
# нигде не показывается пользователю — ни pick_gap_question_if_any, ни
# pick_morning_reflection не используют question_text при category ==
# "reflect", только сам факт "гэпа нет").


def _random_sequence(*values):
    """monkeypatch для random.random(), возвращающий values по очереди —
    pick_morning_reflection дважды зовёт random.random() (сначала выбор
    gap/journal-ветки, потом _with_musing внутри неё), одной константой
    оба решения независимо не выставить."""
    return Mock(side_effect=list(values))


async def test_musing_appended_about_half_the_time(monkeypatch):
    # 0.99 >= _MORNING_JOURNAL_CHANCE (0.7) → gap-ветка;
    # 0.0 < _MUSING_CHANCE (0.5) → musing добавлен
    monkeypatch.setattr(
        "app.proactive.service.random.random", _random_sequence(0.99, 0.0)
    )
    service, repository = _service()  # нет целей — гэп по цели есть

    question = await service.pick_morning_reflection(1)

    assert "🤔" in question
    assert any(musing in question for musing in MUSING_QUESTIONS)
    # В pending_prompts уходит ЧИСТЫЙ вопрос, без musing-строки
    stored_question = repository.upsert.await_args.args[2]
    assert stored_question in GOAL_QUESTIONS
    assert "🤔" not in stored_question


async def test_musing_not_appended_when_chance_misses(monkeypatch):
    # 0.99 >= _MORNING_JOURNAL_CHANCE и >= _MUSING_CHANCE — gap-ветка,
    # без musing
    monkeypatch.setattr(
        "app.proactive.service.random.random", _random_sequence(0.99, 0.99)
    )
    service, repository = _service()

    question = await service.pick_morning_reflection(1)

    assert "🤔" not in question
    repository.upsert.assert_awaited_once_with(1, "goal", question)


async def test_morning_reflection_journal_branch(monkeypatch):
    # random() >= _MORNING_JOURNAL_CHANCE (0.7) выбирает gap-ветку —
    # значение НИЖЕ 0.7 должно давать дневниковый вопрос
    monkeypatch.setattr("app.proactive.service.random.random", lambda: 0.1)
    service, repository = _service()  # гэп по цели точно есть

    question = await service.pick_morning_reflection(1)

    assert question in DREAM_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "journal", question)


async def test_morning_reflection_gap_branch_when_gap_exists(monkeypatch):
    monkeypatch.setattr("app.proactive.service.random.random", lambda: 0.99)
    service, repository = _service()  # нет целей — есть гэп

    question = await service.pick_morning_reflection(1)

    assert question in GOAL_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "goal", question)


async def test_morning_reflection_falls_back_to_journal_when_no_gap(monkeypatch):
    monkeypatch.setattr("app.proactive.service.random.random", lambda: 0.99)
    service, repository = _service(
        goals=[object()],
        habits=[object()],
        projects=[object()],
        preferences=[object(), object(), object()],
    )  # профиль полностью заполнен — _pick_question вернул бы "reflect"

    question = await service.pick_morning_reflection(1)

    assert question in DREAM_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "journal", question)


async def test_morning_reflection_allow_gap_false_always_journal(monkeypatch):
    # Даже когда жребий выпал бы на gap-ветку — allow_gap=False (нет
    # AI-ключа) должен всегда отдавать дневниковый вопрос
    monkeypatch.setattr("app.proactive.service.random.random", lambda: 0.99)
    service, repository = _service()  # гэп по цели есть

    question = await service.pick_morning_reflection(1, allow_gap=False)

    assert question in DREAM_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "journal", question)


async def test_pick_gap_question_if_any_returns_question_when_gap_exists():
    service, repository = _service()  # нет целей — гэп есть

    question = await service.pick_gap_question_if_any(1)

    assert question in GOAL_QUESTIONS
    repository.upsert.assert_awaited_once_with(1, "goal", question)


async def test_pick_gap_question_if_any_returns_none_when_no_gap():
    service, repository = _service(
        goals=[object()],
        habits=[object()],
        projects=[object()],
        preferences=[object(), object(), object()],
    )  # профиль полностью заполнен

    question = await service.pick_gap_question_if_any(1)

    assert question is None
    repository.upsert.assert_not_awaited()


async def test_get_open_delegates_to_repository():
    service, repository = _service()
    repository.get_for_user.return_value = "pending"

    result = await service.get_open(1)

    assert result == "pending"
    repository.get_for_user.assert_awaited_once_with(1)


async def test_clear_delegates_to_repository():
    service, repository = _service()

    await service.clear(1)

    repository.clear_for_user.assert_awaited_once_with(1)
