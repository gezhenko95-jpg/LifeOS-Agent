from unittest.mock import AsyncMock

import pytest

from app.crm.models import Contact, ContactComment
from app.crm.service import ContactCommentService


@pytest.fixture
def repo():
    r = AsyncMock()
    r.add.side_effect = lambda comment: comment
    return r


@pytest.fixture
def contact_repo():
    return AsyncMock()


async def test_add_comment_success(repo, contact_repo):
    contact_repo.get_by_id.return_value = Contact(id=1, telegram_user_id=1, name="Аня")
    service = ContactCommentService(repo, contact_repo)

    comment = await service.add_comment(1, contact_id=1, text="Позвонить на праздники")

    assert comment.text == "Позвонить на праздники"
    assert comment.contact_id == 1
    assert comment.telegram_user_id == 1
    repo.add.assert_awaited_once()


async def test_add_comment_strips_text(repo, contact_repo):
    contact_repo.get_by_id.return_value = Contact(id=1, telegram_user_id=1, name="Аня")
    service = ContactCommentService(repo, contact_repo)

    comment = await service.add_comment(1, contact_id=1, text="  привет  ")

    assert comment.text == "привет"


async def test_add_comment_empty_text_raises(repo, contact_repo):
    contact_repo.get_by_id.return_value = Contact(id=1, telegram_user_id=1, name="Аня")
    service = ContactCommentService(repo, contact_repo)

    with pytest.raises(ValueError):
        await service.add_comment(1, contact_id=1, text="   ")


async def test_add_comment_missing_contact_returns_none(repo, contact_repo):
    contact_repo.get_by_id.return_value = None
    service = ContactCommentService(repo, contact_repo)

    result = await service.add_comment(1, contact_id=99, text="Привет")

    assert result is None
    repo.add.assert_not_awaited()


async def test_add_comment_someone_elses_contact_returns_none(repo, contact_repo):
    contact_repo.get_by_id.return_value = Contact(
        id=1, telegram_user_id=2, name="Чужой"
    )
    service = ContactCommentService(repo, contact_repo)

    result = await service.add_comment(1, contact_id=1, text="Привет")

    assert result is None
    repo.add.assert_not_awaited()


async def test_list_comments_delegates_to_repository(repo, contact_repo):
    contact_repo.get_by_id.return_value = Contact(id=1, telegram_user_id=1, name="Аня")
    repo.list_by_contact.return_value = [
        ContactComment(contact_id=1, telegram_user_id=1, text="A")
    ]
    service = ContactCommentService(repo, contact_repo)

    comments = await service.list_comments(1, contact_id=1)

    assert len(comments) == 1
    repo.list_by_contact.assert_awaited_once_with(1)


async def test_list_comments_someone_elses_contact_returns_empty(repo, contact_repo):
    contact_repo.get_by_id.return_value = Contact(
        id=1, telegram_user_id=2, name="Чужой"
    )
    service = ContactCommentService(repo, contact_repo)

    comments = await service.list_comments(1, contact_id=1)

    assert comments == []
    repo.list_by_contact.assert_not_awaited()


async def test_count_by_contacts_delegates_to_repository(repo, contact_repo):
    repo.count_by_contacts.return_value = {1: 3}
    service = ContactCommentService(repo, contact_repo)

    counts = await service.count_by_contacts([1])

    assert counts == {1: 3}


async def test_delete_comment_success(repo, contact_repo):
    comment = ContactComment(id=10, contact_id=1, telegram_user_id=1, text="A")
    repo.get_by_id.return_value = comment
    contact_repo.get_by_id.return_value = Contact(id=1, telegram_user_id=1, name="Аня")
    service = ContactCommentService(repo, contact_repo)

    deleted = await service.delete_comment(1, comment_id=10)

    assert deleted is comment
    repo.delete.assert_awaited_once_with(comment)


async def test_delete_comment_missing_returns_none(repo, contact_repo):
    repo.get_by_id.return_value = None
    service = ContactCommentService(repo, contact_repo)

    result = await service.delete_comment(1, comment_id=10)

    assert result is None
    repo.delete.assert_not_awaited()


async def test_delete_comment_someone_elses_contact_returns_none(repo, contact_repo):
    comment = ContactComment(id=10, contact_id=1, telegram_user_id=2, text="A")
    repo.get_by_id.return_value = comment
    contact_repo.get_by_id.return_value = Contact(
        id=1, telegram_user_id=2, name="Чужой"
    )
    service = ContactCommentService(repo, contact_repo)

    result = await service.delete_comment(1, comment_id=10)

    assert result is None
    repo.delete.assert_not_awaited()
