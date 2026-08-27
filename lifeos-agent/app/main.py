"""
Основной модуль FastAPI приложения LifeOS Agent
"""

from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    assistant,
    charts,
    crm,
    digest,
    finance,
    focus,
    goals,
    habits,
    health,
    memory,
    mood,
    poster,
    rewards,
    shop,
    tasks,
    watchlist,
)
from app.api.deps import require_api_token
from app.core.config import get_settings

_WEB_STATIC_DIR = Path(__file__).parent / "web" / "static"

_settings = get_settings()
_is_production = _settings.environment != "development"

app = FastAPI(
    title="LifeOS Agent",
    description="Personal AI Chief of Staff - операционная система для управления жизнью",
    version="0.1.0",
    # На проде схема API наружу не отдаётся: /docs публично рисовал полную
    # карту эндпоинтов (см. AUDIT.md, раздел 7).
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# CORS: allow_origins=["*"] вместе с allow_credentials=True запрещён
# спецификацией и игнорируется браузерами — фронт /ui ходит на свой же
# origin, звёздочка ему не нужна (см. AUDIT.md, раздел 7).
_allowed_origins = (
    [_settings.public_ui_url.rsplit("/ui", 1)[0]] if _settings.public_ui_url else []
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров.
# Всё, кроме /health, закрыто общим токеном (см. app/api/deps.py) —
# health нужен снаружи для проверки живости и приватных данных не отдаёт.
_protected = [Depends(require_api_token)]

app.include_router(health.router, tags=["health"])
# Прокси обложек — без токена намеренно: <img> не умеет слать заголовки,
# а пользовательских данных в запросе нет (см. app/api/poster.py).
app.include_router(poster.router)
app.include_router(tasks.router, tags=["tasks"], dependencies=_protected)
app.include_router(memory.router, tags=["memory"], dependencies=_protected)
app.include_router(habits.router, tags=["habits"], dependencies=_protected)
app.include_router(goals.router, tags=["goals"], dependencies=_protected)
app.include_router(watchlist.router, tags=["watchlist"], dependencies=_protected)
app.include_router(rewards.router, tags=["rewards"], dependencies=_protected)
app.include_router(digest.router, tags=["digest"], dependencies=_protected)
app.include_router(finance.router, tags=["finance"], dependencies=_protected)
app.include_router(crm.router, tags=["crm"], dependencies=_protected)
app.include_router(mood.router, tags=["mood"], dependencies=_protected)
app.include_router(assistant.router, tags=["assistant"], dependencies=_protected)
# В отличие от poster — график содержит личные данные (задачи/привычки/
# настроение), токен обязателен. /ui грузит его через fetch()+blob, не
# голым <img src>, ровно из-за этого (см. loadWeeklyChart в index.html).
app.include_router(charts.router, tags=["charts"], dependencies=_protected)
app.include_router(focus.router, tags=["focus"], dependencies=_protected)
app.include_router(shop.router, tags=["shop"], dependencies=_protected)

# Простейший веб-интерфейс — статическая страница, использует REST API выше.
app.mount("/ui", StaticFiles(directory=_WEB_STATIC_DIR, html=True), name="ui")


@app.get("/")
async def root():
    """
    Корневой эндпоинт
    """
    return {
        "name": "LifeOS Agent",
        "version": "0.1.0",
        "description": "Personal AI Chief of Staff",
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
