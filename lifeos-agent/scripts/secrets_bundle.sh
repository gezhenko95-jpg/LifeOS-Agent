#!/usr/bin/env bash
#
# Собрать все секреты проекта в ОДИН зашифрованный файл — и обратно.
#
#     bash lifeos-agent/scripts/secrets_bundle.sh pack     # собрать
#     bash lifeos-agent/scripts/secrets_bundle.sh unpack   # разложить
#
# Зачем именно так. Держать пароли в обычном файле нельзя: он попадёт в
# бэкап, в облако, в чат — пароль DNS-панели однажды уже утёк ровно
# потому, что лежал открытым текстом в HANDOFF.md, а файл целиком
# вставляли в чаты. Здесь всё лежит под одним мастер-паролем, и его
# место — менеджер паролей, а не заметка.
#
# Что попадает в архив:
#   lifeos-agent/.env              — токены бота, БД, API, OpenRouter, TMDb, Books
#   lifeos-agent/token.json        — OAuth Google Drive
#   lifeos-agent/credentials.json  — клиент Google Drive
#   ~/.ssh/lifeos_main             — ключ до прод-сервера (если есть)
#
# Файл архива кладётся РЯДОМ с репозиторием, а не внутрь: так его
# физически нельзя закоммитить по невнимательности.
#
# Шифрование: openssl AES-256-CBC с PBKDF2 и солью. Без пароля файл
# бесполезен, восстановить его никак — забыли пароль, собирайте заново
# из сервера через pull_secrets.sh.

set -euo pipefail

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; GREY=$'\033[90m'; RESET=$'\033[0m'
die() { echo "${RED}✗ $*${RESET}" >&2; exit 1; }
ok() { echo "${GREEN}✓ $*${RESET}"; }
step() { echo "${YELLOW}→ $*${RESET}"; }

command -v openssl >/dev/null || die "нет openssl — им шифруется архив"

REPO="$(git rev-parse --show-toplevel)"
BUNDLE="$(dirname "${REPO}")/lifeos-secrets.enc"
MODE="${1:-}"

# Список: путь_в_архиве|откуда_брать
ITEMS=(
    "env|${REPO}/lifeos-agent/.env"
    "token.json|${REPO}/lifeos-agent/token.json"
    "credentials.json|${REPO}/lifeos-agent/credentials.json"
    "ssh_lifeos_main|${HOME}/.ssh/lifeos_main"
)

pack() {
    local staging
    staging="$(mktemp -d)"
    trap 'rm -rf "${staging}"' EXIT

    local count=0
    for item in "${ITEMS[@]}"; do
        local name="${item%%|*}" src="${item#*|}"
        if [ -f "${src}" ]; then
            cp "${src}" "${staging}/${name}"
            echo "    + ${name}"
            count=$((count + 1))
        else
            echo "    ${GREY}- ${name} (нет на этой машине, пропускаю)${RESET}"
        fi
    done
    [ "${count}" -gt 0 ] || die "нечего собирать — ни одного файла не найдено"

    step "Придумайте мастер-пароль (его же спросит unpack)"
    tar -C "${staging}" -czf - . \
        | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -out "${BUNDLE}" \
        || die "шифрование не удалось"

    ok "собрано ${count} файлов -> ${BUNDLE}"
    echo
    echo "Дальше:"
    echo "  1. Мастер-пароль — в менеджер паролей, запись «LifeOS secrets bundle»."
    echo "  2. Сам файл можно хранить где угодно, хоть на Google Drive:"
    echo "     без пароля он бесполезен."
    echo "  3. На новой машине: bash lifeos-agent/scripts/secrets_bundle.sh unpack"
}

unpack() {
    [ -f "${BUNDLE}" ] || die "нет файла ${BUNDLE}
  Положите архив рядом с папкой репозитория и повторите."

    local staging
    staging="$(mktemp -d)"
    trap 'rm -rf "${staging}"' EXIT

    step "Введите мастер-пароль"
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "${BUNDLE}" \
        | tar -C "${staging}" -xzf - \
        || die "не расшифровалось — неверный пароль или файл повреждён"

    for item in "${ITEMS[@]}"; do
        local name="${item%%|*}" dst="${item#*|}"
        [ -f "${staging}/${name}" ] || continue
        mkdir -p "$(dirname "${dst}")"
        # Существующее не затираем молча: потерять рабочий .env из-за
        # запуска не той команды — слишком дорого.
        if [ -e "${dst}" ]; then
            cp "${dst}" "${dst}.bak-$(date +%Y%m%d-%H%M%S)"
            echo "    ${GREY}прежний $(basename "${dst}") сохранён рядом с меткой времени${RESET}"
        fi
        cp "${staging}/${name}" "${dst}"
        # Приватный ключ обязан быть 600, иначе ssh откажется его читать.
        case "${name}" in ssh_*) chmod 600 "${dst}" ;; esac
        echo "    -> ${dst}"
    done

    ensure_ssh_alias
    ok "разложено"
    echo "Проверить машину: python lifeos-agent/scripts/doctor.py"
}

# Ключа мало: deploy.sh ходит на хост по имени lifeos-eu, а имя живёт в
# ~/.ssh/config. Без этой записи ключ лежит правильно, а деплой всё равно
# не работает — и причина неочевидная. Дописываем, если её нет.
ensure_ssh_alias() {
    local key="${HOME}/.ssh/lifeos_main"
    local config="${HOME}/.ssh/config"

    [ -f "${key}" ] || return 0
    if [ -f "${config}" ] && grep -qE "^[[:space:]]*Host[[:space:]]+.*lifeos-eu" "${config}"; then
        echo "    ${GREY}алиас lifeos-eu в ~/.ssh/config уже есть${RESET}"
        return 0
    fi

    mkdir -p "${HOME}/.ssh"
    chmod 700 "${HOME}/.ssh"
    # Пустая строка перед блоком: без неё запись слипнется с предыдущей
    # и ssh прочитает её как продолжение чужого Host.
    {
        echo ""
        echo "Host lifeos-eu"
        echo "  HostName 148.135.208.126"
        echo "  User root"
        echo "  IdentityFile ~/.ssh/lifeos_main"
        echo "  ServerAliveInterval 20"
        echo "  ServerAliveCountMax 6"
    } >> "${config}"
    chmod 600 "${config}"
    echo "    -> добавлен алиас lifeos-eu в ${config}"
}

case "${MODE}" in
    pack) pack ;;
    unpack) unpack ;;
    *)
        echo "Использование:"
        echo "  bash lifeos-agent/scripts/secrets_bundle.sh pack     — собрать в ${BUNDLE}"
        echo "  bash lifeos-agent/scripts/secrets_bundle.sh unpack   — разложить обратно"
        exit 1
        ;;
esac
