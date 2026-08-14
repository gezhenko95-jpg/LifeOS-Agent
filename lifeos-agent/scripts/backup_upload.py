"""
Залить готовый дамп БД на Google Drive.

Запускается ВНУТРИ контейнера бота (там смонтирован token.json):

    docker exec lifeos-bot-1 python -m scripts.backup_upload /app/backups/файл.sql.gz

Сам дамп делает scripts/backup_db.sh на хосте — pg_dump живёт в
контейнере с Postgres, а токен Drive в контейнере с ботом.
"""

import logging
import sys
from pathlib import Path

from app.backup.service import BackupService
from app.core.config import get_settings
from app.drive.client import DriveServiceError, get_drive_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("backup")


def main() -> int:
    if len(sys.argv) != 2:
        logger.error("Использование: python -m scripts.backup_upload <путь к дампу>")
        return 2

    dump_path = Path(sys.argv[1])
    if not dump_path.is_file():
        logger.error("Файл не найден: %s", dump_path)
        return 1

    settings = get_settings()
    drive_client = get_drive_client(settings)
    if drive_client is None:
        logger.error(
            "Google Drive не настроен (нет %s) — бэкап не выгружен",
            settings.drive_token_file,
        )
        return 1

    try:
        url = BackupService(drive_client, keep=settings.backup_keep).upload(dump_path)
    except DriveServiceError as exc:
        logger.error("Выгрузка не удалась: %s", exc)
        return 1

    logger.info("Готово: %s", url or "(ссылка не возвращена)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
