"""
Проверка машины: всё ли на месте, чтобы работать над проектом.

    python lifeos-agent/scripts/doctor.py

Зачем. Секретов в гите нет, поэтому свежий клон сам по себе неполон. Без
этой проверки недостающий файл обнаруживается не сразу, а посреди работы
и в виде невнятной ошибки: пустой список на /ui вместо «нет api_token»,
молчащий бот вместо «нет токена».

Скрипт НИЧЕГО не чинит и не трогает файлы — только смотрит и говорит,
какой командой починить. Проверки разбиты на уровни: для правки кода
нужен минимум, для деплоя — максимум. Отсутствие того, что нужно только
деплою, не считается ошибкой, если деплоить не собираются.
"""

import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# Windows-консоль по умолчанию не в UTF-8, а весь вывод здесь русский.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GREEN, RED, YELLOW, GREY, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[90m",
    "\033[0m",
)

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent

# Ключи, без которых соответствующая часть проекта молча не работает.
REQUIRED_ENV = {
    "telegram_bot_token": "бот не запустится",
    "owner_telegram_user_id": "бот не узнает владельца и промолчит на всё",
    "api_token": "REST API отвечает 503, /ui показывает пустые списки",
}
OPTIONAL_ENV = {
    "openrouter_api_key": "AI-фолбэк, саммари дайджестов и поиск по памяти",
    "tmdb_api_key": "обложки фильмов на полке",
    "google_books_api_key": "обложки и описания книг",
    "POSTGRES_PASSWORD": "нужен только при поднятии своей БД в docker",
}

problems: list[str] = []


def say(status: str, title: str, detail: str = "") -> None:
    mark = {
        "ok": f"{GREEN}✓{RESET}",
        "fail": f"{RED}✗{RESET}",
        "warn": f"{YELLOW}!{RESET}",
    }[status]
    print(f"  {mark} {title}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"      {GREY}{line}{RESET}")


def section(name: str) -> None:
    print(f"\n{name}")


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, cwd=REPO
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return 1, str(exc)


def parse_env(path: Path) -> dict[str, str]:
    """Мини-парсер .env. Полноценный не нужен: здесь важно только,
    заполнено значение или пустое."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# --- 1. Инструменты ---------------------------------------------------
section("Инструменты")

if have("git"):
    say("ok", "git")
else:
    say("fail", "git не найден", "Установите git и повторите.")
    problems.append("git")

py = f"{sys.version_info.major}.{sys.version_info.minor}"
if sys.version_info >= (3, 11):
    say("ok", f"python {py}")
else:
    say("fail", f"python {py} — нужен 3.11+", "Проект собран под свежий Python.")
    problems.append("python")

try:
    import fastapi  # noqa: F401
    import sqlalchemy  # noqa: F401
    import telegram  # noqa: F401

    say("ok", "зависимости установлены")
except ImportError as exc:
    say(
        "fail",
        f"нет зависимостей ({exc.name})",
        "cd lifeos-agent && pip install -e .[dev]",
    )
    problems.append("deps")

if have("docker"):
    say("ok", "docker")
else:
    say("warn", "docker не найден", "Нужен только чтобы поднять Postgres локально.")

# --- 2. Репозиторий ---------------------------------------------------
section("Репозиторий")

code, out = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
if code == 0:
    branch = out.strip()
    say("ok", f"ветка {branch}")
else:
    say(
        "fail",
        "не git-репозиторий",
        "git clone https://github.com/gezhenko95-jpg/LifeOS-Agent.git",
    )
    problems.append("repo")

code, out = run(["git", "status", "--porcelain"])
if code == 0:
    if out:
        say(
            "warn",
            f"незакоммиченных файлов: {len(out.splitlines())}",
            "Деплой их не пропустит.",
        )
    else:
        say("ok", "рабочая папка чистая")

# --- 3. Секреты -------------------------------------------------------
section("Секреты")

env_path = ROOT / ".env"
if not env_path.exists():
    say(
        "fail",
        ".env отсутствует",
        "Забрать с сервера:  bash lifeos-agent/scripts/pull_secrets.sh\n"
        "Либо начать с нуля:  cp lifeos-agent/.env.example lifeos-agent/.env",
    )
    problems.append(".env")
else:
    env = parse_env(env_path)
    say("ok", f".env на месте ({len(env)} значений)")

    for key, why in REQUIRED_ENV.items():
        value = env.get(key, "")
        if not value or value == "0":
            say("fail", f"{key} не заполнен", f"Без него: {why}")
            problems.append(key)
    for key, why in OPTIONAL_ENV.items():
        if not env.get(key, ""):
            say("warn", f"{key} пуст", f"Отключено: {why}")

    # Сверка с образцом, но ТОЛЬКО по ключам, которые в образце оставлены
    # пустыми — это и есть «сюда надо вписать своё». Остальные там с
    # рабочими значениями по умолчанию, и их отсутствие в личном .env ни
    # на что не влияет: Settings подставит те же дефолты. Без этого
    # сужения проверка ругалась на сорок с лишним строк вроде host и
    # расписаний, и на её фоне терялось единственное важное.
    example = ROOT / ".env.example"
    if example.exists():
        blanks = [k for k, v in parse_env(example).items() if not v]
        missing = [k for k in blanks if not env.get(k)]
        # Про те, что уже разобраны выше поимённо, второй раз не пишем.
        missing = [
            k for k in missing if k not in REQUIRED_ENV and k not in OPTIONAL_ENV
        ]
        if missing:
            say(
                "warn",
                f"не заполнено в .env: {', '.join(missing)}",
                "Смотрите комментарии к ним в .env.example.",
            )

for name, why in (
    ("token.json", "Media Inbox (фото в Google Drive)"),
    ("credentials.json", "переавторизация Google Drive"),
):
    if (ROOT / name).exists():
        say("ok", name)
    else:
        say("warn", f"{name} нет", f"Выключено: {why}")

# --- 4. Доступ к серверу ---------------------------------------------
section("Доступ к серверу (нужен только для деплоя)")

ssh_config = Path.home() / ".ssh" / "config"
alias_ok = ssh_config.exists() and "lifeos-eu" in ssh_config.read_text(
    encoding="utf-8", errors="replace"
)
if alias_ok:
    say("ok", "алиас lifeos-eu в ~/.ssh/config")
else:
    say(
        "warn",
        "нет алиаса lifeos-eu",
        "Без него деплой не работает. Настройка — SETUP.md.",
    )

if alias_ok and have("ssh"):
    code, _ = run(
        ["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", "lifeos-eu", "true"],
        timeout=25,
    )
    if code == 0:
        say("ok", "ssh до сервера проходит")
    else:
        say(
            "warn",
            "ssh не проходит",
            "Ключ не тот, не добавлен на сервер или сеть режет.",
        )

# --- 5. Прод ----------------------------------------------------------
section("Прод")

try:
    socket.setdefaulttimeout(15)
    import urllib.request

    with urllib.request.urlopen("https://lifeos-agent.ru/health") as r:
        body = r.read().decode()
    commit = re.search(r'"commit":"(\w+)"', body)
    say("ok", f"сайт отвечает, коммит {commit.group(1)[:8] if commit else '?'}")

    code, local_head = run(["git", "rev-parse", "HEAD"])
    if commit and code == 0:
        if commit.group(1) == local_head.strip():
            say("ok", "прод совпадает с локальным HEAD")
        else:
            say(
                "warn",
                "прод отстаёт от локального HEAD",
                "Это нормально, если вы ещё не деплоили.",
            )
except Exception as exc:  # noqa: BLE001 — здесь важен сам факт недоступности
    say("warn", "прод недоступен", f"{type(exc).__name__}: {exc}")

# --- Итог -------------------------------------------------------------
print()
if problems:
    print(f"{RED}Не хватает: {', '.join(problems)}{RESET}")
    print("Что делать — в подсказках выше и в SETUP.md.")
    sys.exit(1)

print(f"{GREEN}Всё на месте — можно работать.{RESET}")
print(f"{GREY}Жёлтые пункты выше — необязательные фичи, они просто выключены.{RESET}")
sys.exit(0)
