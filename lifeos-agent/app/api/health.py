"""
Модуль health check для API
"""

from pathlib import Path

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])

# Пишется скриптом деплоя (scripts/deploy.sh) и монтируется в контейнер.
# Отдаём наружу, чтобы сверить прод с гитом можно было одним curl, не
# заходя на сервер по ssh — иначе три копии кода (ноутбук/GitHub/сервер)
# расходятся незаметно.
_DEPLOYED_COMMIT_FILE = Path("/app/DEPLOYED_COMMIT")


def _deployed_commit() -> str:
    """Хеш развёрнутого коммита, либо "unknown".

    OSError, а не только FileNotFoundError: Docker создаёт ПУСТУЮ
    ДИРЕКТОРИЮ на месте незамонтированного файла в bind mount, и чтение
    падает с IsADirectoryError (те же грабли, что у token.json в
    app/drive/client.py).
    """
    try:
        return _DEPLOYED_COMMIT_FILE.read_text().strip() or "unknown"
    except OSError:
        return "unknown"


@router.get("")
async def health_check():
    """
    Проверка состояния системы
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "lifeos-agent",
            "version": "0.1.0",
            "commit": _deployed_commit(),
        },
    )


@router.get("/ready")
async def readiness_check():
    """
    Проверка готовности системы (для kubernetes)
    """
    # TODO: Добавить проверку подключения к базе данных
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ready"},
    )


@router.get("/live")
async def liveness_check():
    """
    Проверка живости системы (для kubernetes)
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "live"},
    )
