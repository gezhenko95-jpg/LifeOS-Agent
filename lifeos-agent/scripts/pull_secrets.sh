#!/usr/bin/env bash
#
# Забрать секреты с прод-сервера на текущую машину.
#
#     bash lifeos-agent/scripts/pull_secrets.sh
#
# Зачем. Секретов в гите нет и не будет, поэтому на новой машине их
# приходится откуда-то брать. Единственный источник правды — сервер:
# там лежит рабочий .env, и именно его значения крутятся на проде.
# Пересылать пароли мессенджером или класть на Google Drive не нужно —
# достаточно доступа по ssh, который и так есть у того, кто деплоит.
#
# Что забирает:
#   /opt/lifeos/.env              -> lifeos-agent/.env
#   /opt/lifeos/token.json        -> lifeos-agent/token.json        (если есть)
#   /opt/lifeos/credentials.json  -> lifeos-agent/credentials.json  (если есть)
#
# Существующие файлы НЕ перезаписываются молча: делается копия с меткой
# времени. Затереть свой рабочий .env одной опечаткой — слишком дорого.

set -euo pipefail

SSH_HOST="lifeos-eu"
REMOTE_DIR="/opt/lifeos"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
die() { echo "${RED}✗ $*${RESET}" >&2; exit 1; }
ok() { echo "${GREEN}✓ $*${RESET}"; }
step() { echo "${YELLOW}→ $*${RESET}"; }

cd "$(git rev-parse --show-toplevel)"/lifeos-agent

step "Проверяю доступ к ${SSH_HOST}"
ssh -o ConnectTimeout=15 -o BatchMode=yes "${SSH_HOST}" true 2>/dev/null \
    || die "нет доступа по ssh к ${SSH_HOST}.
  Нужен ключ и запись в ~/.ssh/config — см. SETUP.md, раздел «Доступ к серверу»."
ok "ssh работает"

backup_if_exists() {
    local file="$1"
    if [ -e "${file}" ]; then
        local stamp
        stamp="$(date +%Y%m%d-%H%M%S)"
        cp "${file}" "${file}.bak-${stamp}"
        echo "    прежний ${file} сохранён как ${file}.bak-${stamp}"
    fi
}

step "Забираю .env"
backup_if_exists .env
ssh "${SSH_HOST}" "cat ${REMOTE_DIR}/.env" > .env.tmp \
    || die "не удалось прочитать ${REMOTE_DIR}/.env"
# Пустой файл — почти наверняка ошибка на той стороне, а не пустой .env.
[ -s .env.tmp ] || die "с сервера пришёл пустой .env — ничего не меняю"
mv .env.tmp .env
ok ".env получен ($(grep -c '=' .env) строк со значениями)"

# Google-файлы опциональны: без них выключается только Media Inbox.
for f in token.json credentials.json; do
    if ssh "${SSH_HOST}" "test -f ${REMOTE_DIR}/${f}" 2>/dev/null; then
        step "Забираю ${f}"
        backup_if_exists "${f}"
        ssh "${SSH_HOST}" "cat ${REMOTE_DIR}/${f}" > "${f}"
        ok "${f} получен"
    else
        echo "    ${f} на сервере нет — Media Inbox просто выключится"
    fi
done

echo
ok "готово. Проверить машину целиком: python lifeos-agent/scripts/doctor.py"
echo "${YELLOW}Помните:${RESET} бота локально с ЭТИМ токеном не запускать —"
echo "Telegram пускает только одного потребителя getUpdates, прод посыплется."
