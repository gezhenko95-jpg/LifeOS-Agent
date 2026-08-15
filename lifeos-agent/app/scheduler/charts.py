"""
Графики для еженедельного дайджеста (см. specs/007-weekly-digest.md).

Разделение по образцу остального scheduler-кода: `gather_chart_data`
ходит в сервисы за данными (тестируется с замоканными сервисами, как
`_format_*_section` в weekly_digest.py), `render_chart` — чистая функция
без БД (тестируется без моков — на вход простые данные, на выходе байты
PNG или None).

Строим только то, для чего уже есть данные (ADR-004 — не заводили
историю прогресса целей ради графика, поэтому графика "цель во времени"
здесь нет):
- столбчатый график "выполнено задач по неделям" (последние 6 недель);
- тепловая карта привычек за последние 30 дней (зелёная клетка —
  привычка отмечена в этот день).
"""

import matplotlib

matplotlib.use("Agg")  # без дисплея (Docker) — обязательно до pyplot

from dataclasses import dataclass  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from io import BytesIO  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from app.habits.service import HabitService  # noqa: E402
from app.tasks.service import TaskService  # noqa: E402

_WEEKS = 6
_HABIT_DAYS = 30
_DONE_COLOR = "#4CAF50"
_NOT_DONE_COLOR = "#e0e0e0"
_BAR_COLOR = "#4C8BF5"


@dataclass
class ChartData:
    weekly_task_counts: list[tuple[str, int]]  # [(label, count), ...] старое→новое
    habit_series: list[tuple[str, list[bool]]]  # [(title, [день1..день30]), ...]


async def gather_chart_data(
    telegram_user_id: int, task_service: TaskService, habit_service: HabitService
) -> ChartData:
    now = datetime.now(timezone.utc)
    weekly_counts = []
    for weeks_ago in range(_WEEKS - 1, -1, -1):
        until = now - timedelta(weeks=weeks_ago)
        since = until - timedelta(weeks=1)
        count = await task_service.count_tasks_completed_between(
            telegram_user_id, since, until
        )
        weekly_counts.append((since.strftime("%d.%m"), count))

    habits = await habit_service.list_active_habits(telegram_user_id)
    since_date = date.today() - timedelta(days=_HABIT_DAYS - 1)
    completed_by_habit = await habit_service.get_completed_days_bulk(
        [h.id for h in habits], since_date
    )
    habit_series = []
    for habit in habits:
        completed_days = completed_by_habit.get(habit.id, set())
        days = [
            (since_date + timedelta(days=offset)) in completed_days
            for offset in range(_HABIT_DAYS)
        ]
        habit_series.append((habit.title, days))

    return ChartData(weekly_task_counts=weekly_counts, habit_series=habit_series)


def render_chart(data: ChartData) -> BytesIO | None:
    """None — нечего показать (ни одной привычки и ни одной выполненной
    задачи за все 6 недель); дайджест в этом случае уходит просто текстом
    (см. app/telegram/jobs.py::send_weekly_digest_job)."""
    has_habits = bool(data.habit_series)
    has_task_activity = any(count > 0 for _, count in data.weekly_task_counts)
    if not has_habits and not has_task_activity:
        return None

    rows = 2 if has_habits else 1
    height = 3.0 + (0.4 * len(data.habit_series) if has_habits else 0)
    fig, axes = plt.subplots(rows, 1, figsize=(7, height))
    axes = [axes] if rows == 1 else axes

    _draw_weekly_bar_chart(axes[0], data.weekly_task_counts)
    if has_habits:
        _draw_habit_heatmap(axes[1], data.habit_series)

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return buf


def _draw_weekly_bar_chart(ax, weekly_counts: list[tuple[str, int]]) -> None:
    labels = [label for label, _ in weekly_counts]
    counts = [count for _, count in weekly_counts]

    ax.bar(labels, counts, color=_BAR_COLOR)
    ax.set_title("Выполнено задач по неделям")
    ax.set_ylim(0, max(counts, default=0) + 1)
    for index, count in enumerate(counts):
        ax.text(index, count + 0.05, str(count), ha="center", va="bottom", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)


def _draw_habit_heatmap(ax, habit_series: list[tuple[str, list[bool]]]) -> None:
    titles = [title for title, _ in habit_series]
    matrix = np.array([[1 if done else 0 for done in days] for _, days in habit_series])

    cmap = ListedColormap([_NOT_DONE_COLOR, _DONE_COLOR])
    ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=1)
    ax.set_yticks(range(len(titles)))
    ax.set_yticklabels(titles, fontsize=8)
    ax.set_xticks([])
    ax.set_title(f"Привычки — последние {_HABIT_DAYS} дней")
