"""
Выгрузка дампа БД на Google Drive + ротация старых копий.

Зачем: до этого весь дневник, цели и память существовали ровно в одном
экземпляре — в docker volume на одном VPS. Потеря сервера означала
потерю всего (см. AUDIT.md, раздел 9).

Композиция уже существующего DriveClient, своей таблицы нет — как
MediaInboxService. Сам дамп делает pg_dump на хосте
(scripts/backup_db.sh), сюда приходит уже готовый файл: pg_dump живёт в
контейнере с Postgres, а Drive-токен — в контейнере с ботом, и смешивать
их в одном образе незачем.
"""

import logging
from pathlib import Path

from app.backup.retention import files_to_delete
from app.drive.client import DriveClient, DriveServiceError

logger = logging.getLogger(__name__)

# Та же корневая папка, что и у Media Inbox — всё, что бот кладёт на
# Диск, лежит в одном месте (см. app/media_inbox/service.py).
_ROOT_FOLDER = "LifeOS"
_BACKUP_FOLDER = "Бэкапы"
_MIME_TYPE = "application/gzip"


class BackupService:
    def __init__(self, drive_client: DriveClient, keep: int = 14) -> None:
        self._drive = drive_client
        self._keep = keep

    def upload(self, dump_path: Path) -> str:
        """Залить дамп и подчистить старые. Возвращает ссылку на файл.

        Ротация выполняется ПОСЛЕ успешной загрузки — иначе неудачная
        выгрузка сначала удалила бы старую копию, а новую не создала, и
        бэкапов стало бы меньше, чем было.
        """
        content = dump_path.read_bytes()
        if not content:
            raise DriveServiceError(f"Дамп пустой: {dump_path}")

        root_id = self._drive.ensure_folder(_ROOT_FOLDER)
        folder_id = self._drive.ensure_folder(_BACKUP_FOLDER, parent_id=root_id)
        url = self._drive.upload_file(folder_id, dump_path.name, content, _MIME_TYPE)
        logger.info("Бэкап %s выгружен (%d байт)", dump_path.name, len(content))

        self._drop_previous_versions(folder_id, dump_path.name, keep_file_url=url)
        self._prune(folder_id)
        return url

    def _drop_previous_versions(
        self, folder_id: str, filename: str, keep_file_url: str
    ) -> None:
        """Убрать более ранние файлы с ТЕМ ЖЕ именем.

        Drive допускает одноимённые файлы в одной папке, поэтому повторный
        запуск бэкапа в тот же день (ручной прогон, перезапуск крона)
        оставлял бы дубль. Ротация считает копии по именам и на дублях
        начала бы врать — 14 файлов могли оказаться семью днями.

        Свежезалитый файл узнаём по id внутри его же webViewLink: список
        приходит отсортированным по createdTime, но сравнивать по времени
        ненадёжно, а id в ссылке однозначен.
        """
        if not keep_file_url:
            # Ссылки нет — опознать только что залитый файл нечем, а
            # удалять "все одноимённые" в такой ситуации значит снести в
            # том числе свежий бэкап. Лучше оставить дубль.
            logger.warning("Drive не вернул ссылку — пропускаю чистку дублей")
            return

        try:
            files = self._drive.list_files(folder_id)
            for file in files:
                if file["name"] == filename and file["id"] not in keep_file_url:
                    self._drive.delete_file(file["id"])
                    logger.info("Удалён дубль бэкапа %s", filename)
        except DriveServiceError as exc:
            logger.warning("Не удалось убрать дубли бэкапа: %s", exc)

    def _prune(self, folder_id: str) -> None:
        """Сбой ротации не должен превращаться в сбой бэкапа — файл уже
        залит, это главное; лишние копии подчистятся на следующий раз."""
        try:
            files = self._drive.list_files(folder_id)
            stale_names = set(files_to_delete([f["name"] for f in files], self._keep))
            for file in files:
                if file["name"] in stale_names:
                    self._drive.delete_file(file["id"])
                    logger.info("Удалён старый бэкап %s", file["name"])
        except DriveServiceError as exc:
            logger.warning("Не удалось почистить старые бэкапы: %s", exc)
