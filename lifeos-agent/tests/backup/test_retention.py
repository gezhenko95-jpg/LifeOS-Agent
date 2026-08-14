"""
Ротация бэкапов — чистая функция, без моков (см. app/backup/retention.py).
"""

from app.backup.retention import files_to_delete


def test_keeps_newest_and_deletes_the_rest():
    names = [
        "lifeos-2026-08-10.sql.gz",
        "lifeos-2026-08-11.sql.gz",
        "lifeos-2026-08-12.sql.gz",
        "lifeos-2026-08-13.sql.gz",
    ]

    assert files_to_delete(names, keep=2) == [
        "lifeos-2026-08-11.sql.gz",
        "lifeos-2026-08-10.sql.gz",
    ]


def test_order_from_drive_does_not_matter():
    """Свежесть берётся из имени (в нём дата), а не из порядка списка —
    иначе результат зависел бы от того, как Drive вернул файлы."""
    shuffled = [
        "lifeos-2026-08-12.sql.gz",
        "lifeos-2026-08-10.sql.gz",
        "lifeos-2026-08-13.sql.gz",
        "lifeos-2026-08-11.sql.gz",
    ]

    assert files_to_delete(shuffled, keep=1) == [
        "lifeos-2026-08-12.sql.gz",
        "lifeos-2026-08-11.sql.gz",
        "lifeos-2026-08-10.sql.gz",
    ]


def test_nothing_to_delete_when_under_limit():
    assert files_to_delete(["lifeos-2026-08-13.sql.gz"], keep=14) == []


def test_empty_list_is_fine():
    assert files_to_delete([], keep=14) == []


def test_zero_keep_deletes_nothing():
    """keep=0 — это почти наверняка обнулённая по ошибке настройка.
    Снести все бэкапы разом слишком дорого, чтобы делать это молча."""
    names = ["lifeos-2026-08-13.sql.gz", "lifeos-2026-08-12.sql.gz"]

    assert files_to_delete(names, keep=0) == []
    assert files_to_delete(names, keep=-5) == []
