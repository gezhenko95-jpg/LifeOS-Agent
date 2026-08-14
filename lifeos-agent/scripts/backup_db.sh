#!/usr/bin/env bash
#
# Ежедневный бэкап БД: pg_dump -> локальный файл -> Google Drive.
#
# Запускается по крону НА ХОСТЕ (не в контейнере):
#   0 4 * * * /opt/lifeos/scripts/backup_db.sh >> /var/log/lifeos-backup.log 2>&1
#
# Почему так, а не одной командой в контейнере: pg_dump есть только в
# образе Postgres, а токен Google Drive смонтирован только в контейнер
# бота. Хост — единственное место, которое видит оба.
#
# set -u: незаданная переменная это ошибка, а не пустая строка (иначе
# опечатка в имени превратила бы путь в "/" со всеми последствиями).
# set -o pipefail: падение pg_dump в конвейере с gzip не должно
# оставаться незамеченным — без него gzip вернул бы 0 на пустом входе и
# мы бы бодро выгрузили пустой "бэкап".
set -euo pipefail

PROJECT_DIR="/opt/lifeos"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_CONTAINER="lifeos-db-1"
BOT_CONTAINER="lifeos-bot-1"
KEEP_LOCAL_DAYS=7

STAMP="$(date +%F)"
FILENAME="lifeos-${STAMP}.sql.gz"
DUMP_PATH="${BACKUP_DIR}/${FILENAME}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date +'%F %T')] Дамп ${FILENAME}"

# Пишем во временный файл и переименовываем только после успеха — иначе
# оборванный на середине дамп остался бы лежать под правильным именем и
# выглядел бы как валидный бэкап.
docker exec "${DB_CONTAINER}" pg_dump -U postgres --clean --if-exists lifeos \
  | gzip > "${DUMP_PATH}.tmp"
mv "${DUMP_PATH}.tmp" "${DUMP_PATH}"

SIZE="$(stat -c %s "${DUMP_PATH}")"
if [ "${SIZE}" -lt 1000 ]; then
  echo "ОШИБКА: дамп подозрительно мал (${SIZE} байт) — не выгружаю"
  exit 1
fi
echo "[$(date +'%F %T')] Дамп готов, ${SIZE} байт"

# Контейнер бота видит ${BACKUP_DIR} как /app/backups (см. docker-compose.yml).
docker exec "${BOT_CONTAINER}" python -m scripts.backup_upload "/app/backups/${FILENAME}"

# Локальная копия — страховка на случай, если Drive недоступен; держим
# неделю, на Диске хранится дольше (backup_keep в .env).
find "${BACKUP_DIR}" -name 'lifeos-*.sql.gz' -mtime "+${KEEP_LOCAL_DAYS}" -delete
find "${BACKUP_DIR}" -name '*.tmp' -mtime +1 -delete

echo "[$(date +'%F %T')] Бэкап завершён"
