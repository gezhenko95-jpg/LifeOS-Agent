"""
REST API для графиков (specs/007-weekly-digest.md, specs/019-mood-tracker.md).

Один эндпоинт — карточка "Итоги недели" на /ui получила график (бэклог
23-24.08, "в итоги добавить изображение с графиками"). Сама отрисовка
(gather_chart_data/render_chart) уже существовала для еженедельного
дайджеста в Telegram (app/telegram/jobs.py::send_weekly_digest_job) —
здесь только новый вход к тому же коду, без дублирования.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import (
    build_habit_service,
    build_mood_service,
    build_task_service,
)
from app.db.session import get_session
from app.scheduler.charts import gather_chart_data, render_chart

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/weekly")
async def get_weekly_chart(
    telegram_user_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """PNG. 404, если показывать нечего (ни одной выполненной задачи за
    6 недель, ни одной привычки, ни одной отметки настроения) — тот же
    случай, что заставляет дайджест в Telegram уйти текстом без фото."""
    data = await gather_chart_data(
        telegram_user_id,
        build_task_service(session),
        build_habit_service(session),
        build_mood_service(session),
    )
    buf = render_chart(data)
    if buf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Нечего показать"
        )
    return Response(content=buf.getvalue(), media_type="image/png")
