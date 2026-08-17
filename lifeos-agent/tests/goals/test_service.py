from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from app.goals.models import Goal
from app.goals.service import GoalService


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda goal: goal
    repo.save.side_effect = lambda goal: goal
    return repo


async def test_create_goal(repository):
    service = GoalService(repository)

    goal = await service.create_goal(telegram_user_id=1, title="Выучить английский")

    assert goal.title == "Выучить английский"
    assert goal.status == "active"
    assert goal.progress == 0
    repository.add.assert_awaited_once()


async def test_create_goal_with_target_date(repository):
    target = date.today() + timedelta(days=30)
    service = GoalService(repository)

    goal = await service.create_goal(
        telegram_user_id=1, title="Марафон", target_date=target
    )

    assert goal.target_date == target


async def test_create_goal_empty_title_raises(repository):
    service = GoalService(repository)

    with pytest.raises(ValueError):
        await service.create_goal(telegram_user_id=1, title="   ")


async def test_list_active_goals(repository):
    repository.list_by_user.return_value = [
        Goal(telegram_user_id=1, title="A", status="active", progress=0)
    ]
    service = GoalService(repository)

    goals = await service.list_active_goals(1)

    assert len(goals) == 1
    repository.list_by_user.assert_awaited_once_with(1, status="active")


async def test_update_progress(repository):
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    updated = await service.update_progress(1, 1, 40)

    assert updated is not None
    assert updated.progress == 40
    assert updated.updated_at is not None


async def test_update_progress_out_of_range_raises(repository):
    service = GoalService(repository)

    with pytest.raises(ValueError):
        await service.update_progress(1, 1, 150)

    with pytest.raises(ValueError):
        await service.update_progress(1, 1, -1)


async def test_progress_100_completes_the_goal(repository):
    """Поведение изменено 17.08.2026 по итогам живого использования:
    раньше цель со 100% оставалась активной, и её приходилось закрывать
    второй кнопкой — выглядело так, будто бот не заметил достижения."""
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    updated = await service.update_progress(1, 1, 100)

    assert updated is not None
    assert updated.status == "completed"


async def test_progress_below_100_keeps_goal_active(repository):
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    updated = await service.update_progress(1, 1, 90)

    assert updated.status == "active"


async def test_lowering_progress_reopens_completed_goal(repository):
    """«−10%» на только что закрытой цели должен вернуть её в работу, а
    не оставить завершённой с 90%."""
    goal = Goal(telegram_user_id=1, title="X", status="completed", progress=100)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    updated = await service.update_progress(1, 1, 90)

    assert updated.status == "active"


async def test_explicit_status_wins_over_progress(repository):
    """Явный статус сильнее догадки по прогрессу: 100% + «заброшена» —
    это заброшенная цель, а не достигнутая."""
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    updated = await service.update_goal(1, 1, status="abandoned", progress=100)

    assert updated.status == "abandoned"


async def test_update_progress_not_found(repository):
    repository.get_by_id.return_value = None
    service = GoalService(repository)

    result = await service.update_progress(1, 999, 50)

    assert result is None


async def test_update_progress_wrong_owner_returns_none(repository):
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    result = await service.update_progress(2, 1, 40)

    assert result is None


async def test_complete_goal(repository):
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=80)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    completed = await service.complete_goal(1, 1)

    assert completed is not None
    assert completed.status == "completed"
    # Завершённая цель с полоской на 80% выглядит как незакрытое дело.
    assert completed.progress == 100


async def test_update_goal_invalid_status_raises(repository):
    service = GoalService(repository)

    with pytest.raises(ValueError):
        await service.update_goal(1, 1, status="not_a_status")


async def test_delete_goal_found(repository):
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    result = await service.delete_goal(1, 1)

    assert result is goal
    repository.delete.assert_awaited_once_with(goal)


async def test_delete_goal_not_found(repository):
    repository.get_by_id.return_value = None
    service = GoalService(repository)

    result = await service.delete_goal(1, 999)

    assert result is None


async def test_delete_goal_wrong_owner_returns_none(repository):
    goal = Goal(telegram_user_id=1, title="X", status="active", progress=0)
    repository.get_by_id.return_value = goal
    service = GoalService(repository)

    result = await service.delete_goal(2, 1)

    assert result is None
