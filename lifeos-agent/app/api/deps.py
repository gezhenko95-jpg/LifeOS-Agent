"""
Общие зависимости FastAPI — сейчас только аутентификация.

REST API отдаёт задачи/память/цели по telegram_user_id из обычного
query-параметра. Пока эндпоинты были доступны только с localhost, этого
хватало; после выкладки на публичный домен любой желающий мог прочитать
и удалить чужой дневник, зная лишь Telegram ID (см. AUDIT.md, C-2).

Общий токен — не полноценная авторизация (пользователь один, PROJECT.md),
а замок на двери. Полноценный вход через Telegram Login Widget — отдельная
фича, здесь намеренно не делается.
"""

import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_api_token(x_api_token: str = Header(default="")) -> None:
    """401, если токен не совпал. Пустой api_token в настройках закрывает
    API полностью — забытая настройка должна ломать доступ, а не молча
    снимать защиту."""
    expected = get_settings().api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API не настроен: задайте api_token в .env",
        )
    # compare_digest вместо == — постоянное время сравнения, чтобы токен
    # нельзя было подобрать посимвольно по времени ответа.
    if not secrets.compare_digest(x_api_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен"
        )
