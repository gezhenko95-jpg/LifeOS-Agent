"""
REST API для графиков (specs/007-weekly-digest.md, specs/019-mood-tracker.md).

Один эндпоинт — карточка "Итоги недели" на /ui получила график (бэклог
23-24.08, "в итоги добавить изображение с графиками"). Сама отрисовка
(gather_chart_data/render_chart) уже существовала для еженедельного
дайджеста в Telegram (app/telegram/jobs.py::send_weekly_digest_job) —
здесь только новый вход к тому же коду, без дублирования.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import (
    build_habit_service,
    build_mood_service,
    build_task_service,
)
from app.db.session import get_session
from app.scheduler.charts import gather_chart_data, render_chart

router = APIRouter(prefix="/charts", tags=["charts"])


class WeeklyTaskPoint(BaseModel):
    label: str
    count: int


class HabitDayRow(BaseModel):
    title: str
    days: list[bool]


class MoodPoint(BaseModel):
    date: date
    score: int


class WeeklyChartData(BaseModel):
    """JSON-версия ChartData (app/scheduler/charts.py) — тот же
    gather_chart_data, без render_chart: /ui рисует HTML/CSS-бары сам
    (отчёт владельца 24.08, вечер #6, волна 6: "не картинку, а график
    как в финансах"), PNG-роут ниже остаётся для дайджеста в Telegram,
    без изменений."""

    weekly_task_counts: list[WeeklyTaskPoint]
    habit_series: list[HabitDayRow]
    mood_series: list[MoodPoint]


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


@router.get("/weekly/data", response_model=WeeklyChartData)
async def get_weekly_chart_data(
    telegram_user_id: int,
    weeks: int = Query(default=12, ge=1, le=52),
    session: AsyncSession = Depends(get_session),
) -> WeeklyChartData:
    """Те же данные, что рисует /charts/weekly в PNG — здесь сырыми
    числами, HTML/CSS-график на /ui строит сам (см. WeeklyChartData).
    Никогда не 404 — пустые массивы вместо картинки-заглушки, фронту
    есть чем управлять (показать "нечего показать" самому)."""
    data = await gather_chart_data(
        telegram_user_id,
        build_task_service(session),
        build_habit_service(session),
        build_mood_service(session),
        weeks=weeks,
    )
    return WeeklyChartData(
        weekly_task_counts=[
            WeeklyTaskPoint(label=label, count=count)
            for label, count in data.weekly_task_counts
        ],
        habit_series=[
            HabitDayRow(title=title, days=days) for title, days in data.habit_series
        ],
        mood_series=[MoodPoint(date=d, score=score) for d, score in data.mood_series],
    )
