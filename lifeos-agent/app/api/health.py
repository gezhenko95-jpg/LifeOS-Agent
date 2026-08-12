"""
Модуль health check для API
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])


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
