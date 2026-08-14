"""
Точка входа для запуска Telegram-бота отдельным процессом (polling).

Запуск:
    python -m app.telegram.runner
"""

import logging

from app.telegram.bot import build_application

logging.basicConfig(level=logging.INFO)

# httpx на уровне INFO логирует полный URL каждого запроса — а в URL
# Telegram Bot API входит ТОКЕН БОТА, то есть он оседал открытым текстом
# в логах контейнера на каждом getUpdates, раз в секунду (см. AUDIT.md,
# C-5). Ошибки при этом видны по-прежнему.
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
