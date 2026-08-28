from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from app.habits.models import Habit, HabitLog
from app.habits.service import (
    HabitFreezeError,
    HabitNotFoundError,
    HabitService,
    NoFreezeAvailableError,
    NothingToFreezeError,
)

TODAY = date.today()


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda habit: habit
    # Реальная фильтрация теперь в БД (см. app/habits/repository.py,
    # AUDIT.md P-2). Настоящая SQL-версия проверяется отдельно, против
    # SQLite: tests/habits/test_repository.py.
    repo.find_active_by_title.side_effect = lambda telegram_user_id, query: [
        habit
        for habit in repo.list_by_user.return_value
        if query.lower() in habit.title.lower()
    ]
    # Стрик-заморозка (specs/029) — по умолчанию ни у одной привычки нет
    # замороженных дней; тесты, которым это важно, переопределяют явно.
    repo.list_freeze_days_for_habits.return_value = {}
    return repo


async def test_create_habit(repository):
    service = HabitService(repository)

    habit = await service.create_habit(telegram_user_id=1, title="Читать")

    assert habit.title == "Читать"
    assert habit.telegram_user_id == 1
    repository.add.assert_awaited_once()


async def test_create_habit_empty_title_raises(repository):
    service = HabitService(repository)

    with pytest.raises(ValueError):
        await service.create_habit(telegram_user_id=1, title="   ")


async def test_list_active_habits(repository):
    repository.list_by_user.return_value = [Habit(telegram_user_id=1, title="Читать")]
    service = HabitService(repository)

    habits = await service.list_active_habits(1)

    assert len(habits) == 1


async def test_find_active_by_title_is_case_insensitive(repository):
    repository.list_by_user.return_value = [
        Habit(telegram_user_id=1, title="Читать книгу")
    ]
    service = HabitService(repository)

    matches = await service.find_active_by_title(1, "книгу")

    assert len(matches) == 1


async def test_mark_done_today_creates_log_when_not_done_yet(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.list_by_user.return_value = [habit]
    repository.has_log_on.return_value = False
    service = HabitService(repository)

    result = await service.mark_done_today(1, "читать")

    assert result is habit
    repository.add_log.assert_awaited_once_with(1, TODAY)


async def test_mark_done_today_is_idempotent(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.list_by_user.return_value = [habit]
    repository.has_log_on.return_value = True
    service = HabitService(repository)

    result = await service.mark_done_today(1, "читать")

    assert result is habit
    repository.add_log.assert_not_awaited()


async def test_mark_done_today_not_found(repository):
    repository.list_by_user.return_value = []
    service = HabitService(repository)

    result = await service.mark_done_today(1, "читать")

    assert result is None
    repository.add_log.assert_not_awaited()


async def test_mark_done_by_id(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.get_by_id.return_value = habit
    repository.has_log_on.return_value = False
    service = HabitService(repository)

    result = await service.mark_done_by_id(1, 1)

    assert result is habit
    repository.add_log.assert_awaited_once_with(1, TODAY)


async def test_mark_done_by_id_not_found(repository):
    repository.get_by_id.return_value = None
    service = HabitService(repository)

    result = await service.mark_done_by_id(1, 999)

    assert result is None


async def test_mark_done_by_id_wrong_owner_returns_none(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.get_by_id.return_value = habit
    service = HabitService(repository)

    result = await service.mark_done_by_id(2, 1)

    assert result is None


def _owned_habit(habit_id: int = 1, telegram_user_id: int = 1) -> Habit:
    return Habit(telegram_user_id=telegram_user_id, title="Читать", id=habit_id)


async def test_get_streak_no_logs_returns_zero(repository):
    repository.get_by_id.return_value = _owned_habit()
    repository.list_logs.return_value = []
    service = HabitService(repository)

    streak = await service.get_streak(1, 1)

    assert streak == 0


async def test_get_streak_counts_consecutive_days_including_today(repository):
    repository.get_by_id.return_value = _owned_habit()
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=1)),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=2)),
    ]
    service = HabitService(repository)

    streak = await service.get_streak(1, 1)

    assert streak == 3


async def test_get_streak_counts_from_yesterday_if_today_not_marked_yet(repository):
    repository.get_by_id.return_value = _owned_habit()
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=1)),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=2)),
    ]
    service = HabitService(repository)

    streak = await service.get_streak(1, 1)

    assert streak == 2


async def test_get_streak_breaks_on_gap(repository):
    repository.get_by_id.return_value = _owned_habit()
    repository.list_logs.return_value = [
        HabitLog(habit_id=1, completed_on=TODAY),
        HabitLog(habit_id=1, completed_on=TODAY - timedelta(days=3)),
    ]
    service = HabitService(repository)

    streak = await service.get_streak(1, 1)

    assert streak == 1


async def test_get_streak_wrong_owner_returns_zero(repository):
    repository.get_by_id.return_value = _owned_habit()
    service = HabitService(repository)

    streak = await service.get_streak(2, 1)

    assert streak == 0


async def test_delete_habit_found(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.get_by_id.return_value = habit
    service = HabitService(repository)

    result = await service.delete_habit(1, 1)

    assert result is habit
    repository.delete.assert_awaited_once_with(habit)


async def test_delete_habit_not_found(repository):
    repository.get_by_id.return_value = None
    service = HabitService(repository)

    result = await service.delete_habit(1, 999)

    assert result is None


async def test_delete_habit_wrong_owner_returns_none(repository):
    habit = Habit(telegram_user_id=1, title="Читать", id=1)
    repository.get_by_id.return_value = habit
    service = HabitService(repository)

    result = await service.delete_habit(2, 1)

    assert result is None


# --- пакетные методы: одним запросом на несколько привычек (P-1) ---


def _log(habit_id: int, on: date) -> HabitLog:
    return HabitLog(habit_id=habit_id, completed_on=on)


def _owned(*habit_ids: int, telegram_user_id: int = 1) -> list[Habit]:
    """Привычки, которые вернёт list_by_user — этим фильтруются id,
    переданные в *_bulk (см. HabitService._owned_ids)."""
    return [
        Habit(id=habit_id, telegram_user_id=telegram_user_id, title=f"H{habit_id}")
        for habit_id in habit_ids
    ]


async def test_get_streaks_bulk_uses_a_single_repository_call(repository):
    """Экран со списком привычек считает стрик каждой — без пакетного
    метода это было бы N запросов на N привычек (см. AUDIT.md, P-1)."""
    repository.list_by_user.return_value = _owned(1, 2, 3)
    repository.list_logs_for_habits.return_value = {
        1: [_log(1, TODAY), _log(1, TODAY - timedelta(days=1))],
        2: [_log(2, TODAY - timedelta(days=5))],
    }
    service = HabitService(repository)

    streaks = await service.get_streaks_bulk(1, [1, 2, 3])

    assert streaks == {1: 2, 2: 0, 3: 0}
    repository.list_logs_for_habits.assert_awaited_once_with([1, 2, 3])
    repository.list_logs.assert_not_awaited()


async def test_get_streaks_bulk_matches_single_get_streak(repository):
    """Пакетный и одиночный путь должны сходиться в одинаковом ответе —
    иначе список привычек и подтверждение после отметки покажут разные
    цифры для одной и той же привычки."""
    logs = [_log(1, TODAY), _log(1, TODAY - timedelta(days=1))]
    repository.get_by_id.return_value = _owned_habit()
    repository.list_by_user.return_value = _owned(1)
    repository.list_logs_for_habits.return_value = {1: logs}
    repository.list_logs.return_value = logs
    service = HabitService(repository)

    bulk = await service.get_streaks_bulk(1, [1])
    single = await service.get_streak(1, 1)

    assert bulk[1] == single == 2


async def test_get_streaks_bulk_empty_list(repository):
    """Пустой список привычек — пустой результат. Сама защита от
    похода в БД впустую живёт в репозитории (см. test_repository.py),
    сервис её не дублирует."""
    repository.list_by_user.return_value = []
    repository.list_logs_for_habits.return_value = {}
    service = HabitService(repository)

    streaks = await service.get_streaks_bulk(1, [])

    assert streaks == {}


async def test_get_streaks_bulk_drops_ids_not_owned_by_caller(repository):
    """id чужой привычки в списке — не должен попасть ни в запрос логов,
    ни в результат (см. AUDIT.md, A-1/B-2)."""
    repository.list_by_user.return_value = _owned(1)  # id 2 — чужая
    repository.list_logs_for_habits.return_value = {1: [_log(1, TODAY)]}
    service = HabitService(repository)

    streaks = await service.get_streaks_bulk(1, [1, 2])

    assert streaks == {1: 1}
    repository.list_logs_for_habits.assert_awaited_once_with([1])


async def test_get_longest_streaks_bulk(repository):
    repository.list_by_user.return_value = _owned(1, 2)
    repository.list_logs_for_habits.return_value = {
        1: [
            _log(1, TODAY - timedelta(days=10)),
            _log(1, TODAY - timedelta(days=9)),
            _log(1, TODAY - timedelta(days=8)),
            _log(1, TODAY),
        ]
    }
    service = HabitService(repository)

    streaks = await service.get_longest_streaks_bulk(1, [1, 2])

    assert streaks == {1: 3, 2: 0}


async def test_get_completed_days_bulk_filters_by_since(repository):
    since = TODAY - timedelta(days=2)
    repository.list_by_user.return_value = _owned(1)
    repository.list_logs_for_habits.return_value = {
        1: [
            _log(1, TODAY),
            _log(1, TODAY - timedelta(days=1)),
            _log(1, TODAY - timedelta(days=10)),  # раньше since — не входит
        ]
    }
    service = HabitService(repository)

    result = await service.get_completed_days_bulk(1, [1], since)

    assert result == {1: {TODAY, TODAY - timedelta(days=1)}}


async def test_days_since_last_completion_bulk(repository):
    repository.list_by_user.return_value = _owned(1, 2)
    repository.list_logs_for_habits.return_value = {
        1: [_log(1, TODAY - timedelta(days=3))],
        # 2 отсутствует в ответе репозитория — ни разу не отмечалась
    }
    service = HabitService(repository)

    result = await service.days_since_last_completion_bulk(1, [1, 2])

    assert result == {1: 3, 2: None}


# --- Стрик-заморозка (specs/029, по мотивам Duolingo) -------------------

YESTERDAY = TODAY - timedelta(days=1)
DAY_BEFORE_YESTERDAY = TODAY - timedelta(days=2)


@pytest.fixture
def shop_repository():
    repo = AsyncMock()
    repo.purchased_counts.return_value = {}
    return repo


async def test_available_freezes_without_shop_repository_is_zero(repository):
    service = HabitService(repository)

    assert await service.available_freezes(1) == 0


async def test_available_freezes_subtracts_used(repository, shop_repository):
    shop_repository.purchased_counts.return_value = {"streak_freeze": 3}
    repository.count_used_freezes.return_value = 1
    service = HabitService(repository, shop_repository)

    assert await service.available_freezes(1) == 2


async def test_freeze_yesterday_missing_habit_raises_not_found(repository):
    repository.get_by_id.return_value = None
    service = HabitService(repository)

    with pytest.raises(HabitNotFoundError):
        await service.freeze_yesterday(1, 999)


async def test_freeze_yesterday_wrong_owner_raises_not_found(repository):
    repository.get_by_id.return_value = _owned_habit(telegram_user_id=2)
    service = HabitService(repository)

    with pytest.raises(HabitNotFoundError):
        await service.freeze_yesterday(1, 1)


async def test_freeze_yesterday_no_freezes_available_raises(repository):
    repository.get_by_id.return_value = _owned_habit()
    service = HabitService(repository)  # без shop_repository — 0 в инвентаре

    with pytest.raises(NoFreezeAvailableError):
        await service.freeze_yesterday(1, 1)


async def test_freeze_yesterday_already_logged_raises(repository, shop_repository):
    repository.get_by_id.return_value = _owned_habit()
    shop_repository.purchased_counts.return_value = {"streak_freeze": 1}
    repository.count_used_freezes.return_value = 0
    repository.list_logs.return_value = [_log(1, YESTERDAY)]
    service = HabitService(repository, shop_repository)

    with pytest.raises(NothingToFreezeError):
        await service.freeze_yesterday(1, 1)


async def test_freeze_yesterday_no_streak_to_bridge_raises(repository, shop_repository):
    """Позавчера не отмечено — заморозка вчерашнего дня ничего не продлит."""
    repository.get_by_id.return_value = _owned_habit()
    shop_repository.purchased_counts.return_value = {"streak_freeze": 1}
    repository.count_used_freezes.return_value = 0
    repository.list_logs.return_value = []
    service = HabitService(repository, shop_repository)

    with pytest.raises(NothingToFreezeError):
        await service.freeze_yesterday(1, 1)


async def test_freeze_yesterday_already_frozen_raises(repository, shop_repository):
    repository.get_by_id.return_value = _owned_habit()
    shop_repository.purchased_counts.return_value = {"streak_freeze": 1}
    repository.count_used_freezes.return_value = 0
    repository.list_logs.return_value = [_log(1, DAY_BEFORE_YESTERDAY)]
    repository.list_freeze_days_for_habits.return_value = {1: {YESTERDAY}}
    service = HabitService(repository, shop_repository)

    with pytest.raises(NothingToFreezeError):
        await service.freeze_yesterday(1, 1)


async def test_freeze_yesterday_success_records_freeze(repository, shop_repository):
    habit = _owned_habit()
    repository.get_by_id.return_value = habit
    shop_repository.purchased_counts.return_value = {"streak_freeze": 1}
    repository.count_used_freezes.return_value = 0
    repository.list_logs.return_value = [_log(1, DAY_BEFORE_YESTERDAY)]
    service = HabitService(repository, shop_repository)

    result = await service.freeze_yesterday(1, 1)

    assert result is habit
    repository.add_streak_freeze.assert_awaited_once_with(1, YESTERDAY)


async def test_get_streak_extended_by_freeze(repository, shop_repository):
    """Позавчера отмечено, вчера — заморожено: текущий стрик считает
    заморозку как продолжение серии."""
    repository.get_by_id.return_value = _owned_habit()
    repository.list_logs.return_value = [_log(1, DAY_BEFORE_YESTERDAY)]
    repository.list_freeze_days_for_habits.return_value = {1: {YESTERDAY}}
    service = HabitService(repository, shop_repository)

    streak = await service.get_streak(1, 1)

    assert streak == 2


async def test_can_freeze_yesterday_bulk_true_when_gap_bridgeable(repository):
    repository.list_by_user.return_value = _owned(1)
    repository.list_logs_for_habits.return_value = {1: [_log(1, DAY_BEFORE_YESTERDAY)]}
    service = HabitService(repository)

    result = await service.can_freeze_yesterday_bulk(1, [1])

    assert result == {1: True}


async def test_can_freeze_yesterday_bulk_false_when_yesterday_already_done(repository):
    repository.list_by_user.return_value = _owned(1)
    repository.list_logs_for_habits.return_value = {
        1: [_log(1, DAY_BEFORE_YESTERDAY), _log(1, YESTERDAY)]
    }
    service = HabitService(repository)

    result = await service.can_freeze_yesterday_bulk(1, [1])

    assert result == {1: False}


async def test_can_freeze_yesterday_bulk_false_without_streak_to_bridge(repository):
    repository.list_by_user.return_value = _owned(1)
    repository.list_logs_for_habits.return_value = {1: []}
    service = HabitService(repository)

    result = await service.can_freeze_yesterday_bulk(1, [1])

    assert result == {1: False}


async def test_can_freeze_yesterday_bulk_false_when_already_frozen(repository):
    repository.list_by_user.return_value = _owned(1)
    repository.list_logs_for_habits.return_value = {1: [_log(1, DAY_BEFORE_YESTERDAY)]}
    repository.list_freeze_days_for_habits.return_value = {1: {YESTERDAY}}
    service = HabitService(repository)

    result = await service.can_freeze_yesterday_bulk(1, [1])

    assert result == {1: False}


def test_habit_freeze_errors_share_common_base():
    assert issubclass(HabitNotFoundError, HabitFreezeError)
    assert issubclass(NoFreezeAvailableError, HabitFreezeError)
    assert issubclass(NothingToFreezeError, HabitFreezeError)
