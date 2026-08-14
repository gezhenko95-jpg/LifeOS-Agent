#!/usr/bin/env bash
#
# Деплой на прод ИЗ ГИТА, а не из рабочей папки.
#
# Запускать с ноутбука, из корня репозитория:
#     lifeos-agent/scripts/deploy.sh
#
# Зачем именно так. Раньше деплой паковал tar прямо из рабочей папки, и
# три копии кода (ноутбук / GitHub / сервер) могли разъехаться незаметно:
# ничто не мешало выкатить незакоммиченную правку или, наоборот,
# закоммитить и забыть выкатить. Здесь источник — git archive от HEAD,
# то есть на сервер физически не может попасть то, чего нет в коммите.
#
# Три проверки перед выкаткой (любая роняет деплой):
#   1. рабочая папка чистая — иначе выкатилось бы не то, что в коммите;
#   2. HEAD запушен в origin — иначе на сервере окажется код, которого
#      нет ни у кого, кроме этого ноутбука (потеряется вместе с ним);
#   3. тесты зелёные.
#
# Развёрнутый коммит записывается в /opt/lifeos/DEPLOYED_COMMIT и виден
# снаружи в /health — проверить соответствие прода гиту можно в любой
# момент, не заходя на сервер (см. --check).

set -euo pipefail

SSH_HOST="lifeos-eu"
REMOTE_DIR="/opt/lifeos"
STAGING_DIR="/opt/lifeos.staging"
SOURCE_SUBDIR="lifeos-agent"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

die() { echo "${RED}✗ $*${RESET}" >&2; exit 1; }
ok() { echo "${GREEN}✓ $*${RESET}"; }
step() { echo "${YELLOW}→ $*${RESET}"; }

cd "$(git rev-parse --show-toplevel)"

# --- Режим проверки: совпадает ли прод с гитом ---------------------------
if [ "${1:-}" = "--check" ]; then
    DEPLOYED="$(ssh "${SSH_HOST}" "cat ${REMOTE_DIR}/DEPLOYED_COMMIT 2>/dev/null || echo '(неизвестно)'")"
    LOCAL_HEAD="$(git rev-parse HEAD)"
    ORIGIN_HEAD="$(git rev-parse origin/main 2>/dev/null || echo '(нет origin/main)')"
    echo "на сервере:  ${DEPLOYED}"
    echo "HEAD локально: ${LOCAL_HEAD}"
    echo "origin/main:   ${ORIGIN_HEAD}"
    if [ "${DEPLOYED}" = "${ORIGIN_HEAD}" ]; then
        ok "прод соответствует origin/main"
    else
        die "прод НЕ соответствует origin/main"
    fi
    exit 0
fi

# --- Проверки перед выкаткой ---------------------------------------------
step "Проверяю рабочую папку"
[ -z "$(git status --porcelain)" ] \
    || die "есть незакоммиченные изменения — закоммитьте или спрячьте (git stash)"
ok "рабочая папка чистая"

step "Проверяю, что коммит запушен"
COMMIT="$(git rev-parse HEAD)"
git fetch --quiet origin
git merge-base --is-ancestor "${COMMIT}" origin/main \
    || die "HEAD не запушен в origin/main — сначала git push"
ok "коммит ${COMMIT:0:8} есть в origin/main"

step "Прогоняю тесты"
(cd "${SOURCE_SUBDIR}" && python -m pytest -q >/dev/null) \
    || die "тесты не прошли — деплой отменён"
ok "тесты зелёные"

# --- Выкатка --------------------------------------------------------------
step "Отправляю ${COMMIT:0:8} на ${SSH_HOST}"
# git archive берёт содержимое ИЗ КОММИТА, а не из файлов на диске.
git archive --format=tar "HEAD:${SOURCE_SUBDIR}" \
    | ssh "${SSH_HOST}" "rm -rf ${STAGING_DIR} && mkdir -p ${STAGING_DIR} && tar x -C ${STAGING_DIR}"

# rsync --delete убирает с сервера файлы, удалённые в репозитории: tar
# только накладывает поверх, из-за чего мёртвый код жил бы на проде вечно.
# Исключения — то, чего в гите нет и не должно быть.
step "Синхронизирую ${REMOTE_DIR}"
ssh "${SSH_HOST}" "rsync -a --delete \
    --exclude='.env' \
    --exclude='token.json' \
    --exclude='credentials.json' \
    --exclude='backups/' \
    --exclude='DEPLOYED_COMMIT' \
    ${STAGING_DIR}/ ${REMOTE_DIR}/ && rm -rf ${STAGING_DIR}"

ssh "${SSH_HOST}" "echo '${COMMIT}' > ${REMOTE_DIR}/DEPLOYED_COMMIT"

# Порядок важен: сборка -> миграции -> запуск. Если применять миграции до
# сборки, они выполнятся СТАРЫМ образом, где новой ревизии ещё нет.
step "Собираю образ"
ssh "${SSH_HOST}" "cd ${REMOTE_DIR} && docker compose build" || die "сборка упала"

step "Применяю миграции"
ssh "${SSH_HOST}" "cd ${REMOTE_DIR} && docker compose run --rm --no-deps api alembic upgrade head" \
    || die "миграции не применились — контейнеры не перезапускались, прод работает на старой версии"

step "Перезапускаю контейнеры"
ssh "${SSH_HOST}" "cd ${REMOTE_DIR} && docker compose up -d"

# --- Проверка -------------------------------------------------------------
step "Проверяю"
sleep 8
ssh "${SSH_HOST}" "cd ${REMOTE_DIR} && docker compose ps --format '{{.Name}}\t{{.Status}}'"
ok "развёрнут коммит ${COMMIT:0:8}"
