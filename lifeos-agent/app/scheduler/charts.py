"""
Графики для еженедельного дайджеста (см. specs/007-weekly-digest.md,
specs/019-mood-tracker.md).

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
  привычка отмечена в этот день);
- точки настроения за последние 30 дней (1-5 по оси Y).
"""

import matplotlib

matplotlib.use("Agg")  # без дисплея (Docker) — обязательно до pyplot

from dataclasses import dataclass, field  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from io import BytesIO  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from app.habits.service import HabitService  # noqa: E402
from app.mood.service import MoodService  # noqa: E402
from app.tasks.service import TaskService  # noqa: E402

_WEEKS = 6
_HABIT_DAYS = 30
_MOOD_DAYS = 30
_DONE_COLOR = "#4CAF50"
_NOT_DONE_COLOR = "#e0e0e0"
_BAR_COLOR = "#4C8BF5"
_MOOD_COLOR = "#F5A623"


@dataclass
class ChartData:
    weekly_task_counts: list[tuple[str, int]]  # [(label, count), ...] старое→новое
    habit_series: list[tuple[str, list[bool]]]  # [(title, [день1..день30]), ...]
    mood_series: list[tuple[date, int]] = field(
        default_factory=list
    )  # [(день, оценка 1-5), ...], несколько записей в день — несколько точек


async def gather_chart_data(
    telegram_user_id: int,
    task_service: TaskService,
    habit_service: HabitService,
    mood_service: MoodService | None = None,
) -> ChartData:
    """`mood_service=None` тихо пропускает третий подграфик — тот же
    паттерн опциональности, что у ConversationEngine/build_nudges."""
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
        telegram_user_id, [h.id for h in habits], since_date
    )
    habit_series = []
    for habit in habits:
        completed_days = completed_by_habit.get(habit.id, set())
        days = [
            (since_date + timedelta(days=offset)) in completed_days
            for offset in range(_HABIT_DAYS)
        ]
        habit_series.append((habit.title, days))

    mood_series: list[tuple[date, int]] = []
    if mood_service is not None:
        since_mood = now - timedelta(days=_MOOD_DAYS)
        entries = await mood_service.list_since(telegram_user_id, since_mood)
        mood_series = [(entry.logged_at.date(), entry.score) for entry in entries]

    return ChartData(
        weekly_task_counts=weekly_counts,
        habit_series=habit_series,
        mood_series=mood_series,
    )


def render_chart(data: ChartData) -> BytesIO | None:
    """None — нечего показать (ни одной привычки, ни одной выполненной
    задачи за все 6 недель, ни одной отметки настроения); дайджест в
    этом случае уходит просто текстом (см.
    app/telegram/jobs.py::send_weekly_digest_job)."""
    has_habits = bool(data.habit_series)
    has_task_activity = any(count > 0 for _, count in data.weekly_task_counts)
    has_mood = bool(data.mood_series)
    if not has_habits and not has_task_activity and not has_mood:
        return None

    rows = 1 + int(has_habits) + int(has_mood)
    height = (
        3.0
        + (0.4 * len(data.habit_series) if has_habits else 0)
        + (1.6 if has_mood else 0)
    )
    fig, axes = plt.subplots(rows, 1, figsize=(7, height))
    axes = [axes] if rows == 1 else list(axes)

    _draw_weekly_bar_chart(axes[0], data.weekly_task_counts)
    next_row = 1
    if has_habits:
        _draw_habit_heatmap(axes[next_row], data.habit_series)
        next_row += 1
    if has_mood:
        _draw_mood_chart(axes[next_row], data.mood_series)

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


def _draw_mood_chart(ax, mood_series: list[tuple[date, int]]) -> None:
    """Точки, не линия: несколько отметок в один день — обычное дело
    (см. specs/019-mood-tracker.md), соединять их линией во времени
    было бы вводящим в заблуждение "трендом" там, где на самом деле
    просто два разных момента одного дня."""
    ordered = sorted(mood_series, key=lambda pair: pair[0])
    labels = [d.strftime("%d.%m") for d, _ in ordered]
    scores = [score for _, score in ordered]

    ax.scatter(range(len(scores)), scores, color=_MOOD_COLOR, s=24, zorder=3)
    # Тонкая направляющая линия помогает глазу читать порядок точек по
    # времени, не претендуя на "тренд" (она того же цвета, но полупрозрачная).
    ax.plot(range(len(scores)), scores, color=_MOOD_COLOR, alpha=0.3, linewidth=1)
    ax.set_ylim(0.5, 5.5)
    ax.set_yticks([1, 2, 3, 4, 5])
    # Подписей по X не больше 8 — иначе даты слипаются в кашу на 30 точках.
    step = max(1, len(labels) // 8)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step], fontsize=7)
    ax.set_title(f"Настроение — последние {_MOOD_DAYS} дней")
    ax.spines[["top", "right"]].set_visible(False)
