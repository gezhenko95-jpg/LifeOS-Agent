"""
BackupService — DriveClient замокан, реальных вызовов к Google нет
(см. tests/drive/test_client.py).
"""

from unittest.mock import MagicMock

import pytest

from app.backup.service import BackupService
from app.drive.client import DriveServiceError


def _drive(existing: list[dict] | None = None) -> MagicMock:
    drive = MagicMock()
    drive.ensure_folder.side_effect = ["root-id", "backups-id"]
    drive.upload_file.return_value = "https://drive.google.com/file/xyz"
    drive.list_files.return_value = existing if existing is not None else []
    return drive


def _dump(
    tmp_path, name: str = "lifeos-2026-08-15.sql.gz", content: bytes = b"x" * 5000
):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_upload_puts_dump_into_lifeos_backups_folder(tmp_path):
    drive = _drive()

    url = BackupService(drive).upload(_dump(tmp_path))

    assert url == "https://drive.google.com/file/xyz"
    assert drive.ensure_folder.call_args_list[0].args == ("LifeOS",)
    assert drive.ensure_folder.call_args_list[1].args == ("Бэкапы",)
    folder_id, filename, content, mime = drive.upload_file.call_args.args
    assert folder_id == "backups-id"
    assert filename == "lifeos-2026-08-15.sql.gz"
    assert mime == "application/gzip"
    assert len(content) == 5000


def test_empty_dump_is_refused(tmp_path):
    """Пустой файл — признак того, что pg_dump упал. Заливать его нельзя:
    он вытеснит ротацией настоящий бэкап."""
    drive = _drive()

    with pytest.raises(DriveServiceError):
        BackupService(drive).upload(_dump(tmp_path, content=b""))

    drive.upload_file.assert_not_called()


def test_old_backups_are_deleted_after_upload(tmp_path):
    existing = [
        # id совпадает с тем, что в ссылке из _drive() — это только что
        # залитый файл, а не дубль (см. _drop_previous_versions).
        {"id": "xyz", "name": "lifeos-2026-08-15.sql.gz"},
        {"id": "2", "name": "lifeos-2026-08-14.sql.gz"},
        {"id": "3", "name": "lifeos-2026-08-13.sql.gz"},
    ]
    drive = _drive(existing)

    BackupService(drive, keep=2).upload(_dump(tmp_path))

    drive.delete_file.assert_called_once_with("3")


def test_pruning_happens_after_upload_not_before(tmp_path):
    """Иначе неудачная выгрузка сначала снесла бы старую копию, а новую
    не создала — бэкапов стало бы меньше, чем было."""
    drive = _drive(
        [
            {"id": "2", "name": "lifeos-2026-08-14.sql.gz"},
            {"id": "3", "name": "lifeos-2026-08-13.sql.gz"},
        ]
    )
    calls: list[str] = []
    drive.upload_file.side_effect = lambda *a: calls.append("upload") or "url"
    drive.delete_file.side_effect = lambda *a: calls.append("delete")

    BackupService(drive, keep=1).upload(_dump(tmp_path))

    assert calls == ["upload", "delete"]


def test_failed_pruning_does_not_fail_the_backup(tmp_path):
    """Файл уже на Диске — это главное; лишние копии подчистятся завтра."""
    drive = _drive([{"id": "3", "name": "lifeos-2026-08-01.sql.gz"}])
    drive.list_files.side_effect = DriveServiceError("Drive прилёг")

    url = BackupService(drive, keep=1).upload(_dump(tmp_path))

    assert url == "https://drive.google.com/file/xyz"


def test_same_day_rerun_does_not_leave_a_duplicate(tmp_path):
    """Drive допускает одноимённые файлы; без чистки повторный прогон
    оставлял бы дубль, и ротация начала бы считать копии неверно."""
    drive = _drive(
        [
            {"id": "new-xyz", "name": "lifeos-2026-08-15.sql.gz"},
            {"id": "old-abc", "name": "lifeos-2026-08-15.sql.gz"},
            {"id": "2", "name": "lifeos-2026-08-14.sql.gz"},
        ]
    )
    drive.upload_file.return_value = "https://drive.google.com/file/d/new-xyz/view"

    BackupService(drive, keep=14).upload(_dump(tmp_path))

    drive.delete_file.assert_called_once_with("old-abc")


def test_missing_link_skips_dedup_instead_of_deleting_everything(tmp_path):
    """Без ссылки свежий файл не опознать — удалять "все одноимённые"
    значит снести в том числе только что залитый бэкап."""
    drive = _drive([{"id": "old-abc", "name": "lifeos-2026-08-15.sql.gz"}])
    drive.upload_file.return_value = ""

    BackupService(drive, keep=14).upload(_dump(tmp_path))

    drive.delete_file.assert_not_called()
