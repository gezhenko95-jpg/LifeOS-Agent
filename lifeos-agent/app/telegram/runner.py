"""
Точка входа для запуска Telegram-бота отдельным процессом (polling).

Запуск:
    python -m app.telegram.runner
"""

import logging

from app.telegram.bot import build_application

logging.basicConfig(level=logging.INFO)


def main() -> None:
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
