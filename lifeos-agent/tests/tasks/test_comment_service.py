from unittest.mock import AsyncMock

import pytest

from app.tasks.models import Task, TaskComment
from app.tasks.service import TaskCommentService


@pytest.fixture
def repo():
    r = AsyncMock()
    r.add.side_effect = lambda comment: comment
    return r


@pytest.fixture
def task_repo():
    return AsyncMock()


async def test_add_comment_success(repo, task_repo):
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=1, title="X")
    service = TaskCommentService(repo, task_repo)

    comment = await service.add_comment(1, task_id=1, text="Первый шаг сделан")

    assert comment.text == "Первый шаг сделан"
    assert comment.task_id == 1
    assert comment.telegram_user_id == 1
    repo.add.assert_awaited_once()


async def test_add_comment_strips_text(repo, task_repo):
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=1, title="X")
    service = TaskCommentService(repo, task_repo)

    comment = await service.add_comment(1, task_id=1, text="  готово  ")

    assert comment.text == "готово"


async def test_add_comment_empty_text_raises(repo, task_repo):
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=1, title="X")
    service = TaskCommentService(repo, task_repo)

    with pytest.raises(ValueError):
        await service.add_comment(1, task_id=1, text="   ")


async def test_add_comment_missing_task_returns_none(repo, task_repo):
    task_repo.get_by_id.return_value = None
    service = TaskCommentService(repo, task_repo)

    result = await service.add_comment(1, task_id=99, text="Привет")

    assert result is None
    repo.add.assert_not_awaited()


async def test_add_comment_someone_elses_task_returns_none(repo, task_repo):
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=2, title="Чужая")
    service = TaskCommentService(repo, task_repo)

    result = await service.add_comment(1, task_id=1, text="Привет")

    assert result is None
    repo.add.assert_not_awaited()


async def test_list_comments_delegates_to_repository(repo, task_repo):
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=1, title="X")
    repo.list_by_task.return_value = [
        TaskComment(task_id=1, telegram_user_id=1, text="A")
    ]
    service = TaskCommentService(repo, task_repo)

    comments = await service.list_comments(1, task_id=1)

    assert len(comments) == 1
    repo.list_by_task.assert_awaited_once_with(1)


async def test_list_comments_someone_elses_task_returns_empty(repo, task_repo):
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=2, title="Чужая")
    service = TaskCommentService(repo, task_repo)

    comments = await service.list_comments(1, task_id=1)

    assert comments == []
    repo.list_by_task.assert_not_awaited()


async def test_count_by_tasks_delegates_to_repository(repo, task_repo):
    repo.count_by_tasks.return_value = {1: 3}
    service = TaskCommentService(repo, task_repo)

    counts = await service.count_by_tasks([1])

    assert counts == {1: 3}


async def test_delete_comment_success(repo, task_repo):
    comment = TaskComment(id=10, task_id=1, telegram_user_id=1, text="A")
    repo.get_by_id.return_value = comment
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=1, title="X")
    service = TaskCommentService(repo, task_repo)

    deleted = await service.delete_comment(1, comment_id=10)

    assert deleted is comment
    repo.delete.assert_awaited_once_with(comment)


async def test_delete_comment_missing_returns_none(repo, task_repo):
    repo.get_by_id.return_value = None
    service = TaskCommentService(repo, task_repo)

    result = await service.delete_comment(1, comment_id=10)

    assert result is None
    repo.delete.assert_not_awaited()


async def test_delete_comment_someone_elses_task_returns_none(repo, task_repo):
    comment = TaskComment(id=10, task_id=1, telegram_user_id=2, text="A")
    repo.get_by_id.return_value = comment
    task_repo.get_by_id.return_value = Task(id=1, telegram_user_id=2, title="Чужая")
    service = TaskCommentService(repo, task_repo)

    result = await service.delete_comment(1, comment_id=10)

    assert result is None
    repo.delete.assert_not_awaited()
