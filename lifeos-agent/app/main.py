"""
Основной модуль FastAPI приложения LifeOS Agent
"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import goals, habits, health, memory, tasks

_WEB_STATIC_DIR = Path(__file__).parent / "web" / "static"

app = FastAPI(
    title="LifeOS Agent",
    description="Personal AI Chief of Staff - операционная система для управления жизнью",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Заменить на конкретные домены в production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(health.router, tags=["health"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(memory.router, tags=["memory"])
app.include_router(habits.router, tags=["habits"])
app.include_router(goals.router, tags=["goals"])

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
