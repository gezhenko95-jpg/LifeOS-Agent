"""
Готовые привычки — каталог в коде, не в БД.

Почему не таблица: список меняется вместе с кодом (правка = деплой, а не
запись в БД), одинаков для всех пользователей и никем не редактируется
из интерфейса. Таблица здесь дала бы миграцию, репозиторий и сервис ради
константы (ADR-004: простой код лучше).

Пустой экран — главная причина, по которой привычки не заводят вообще:
человек открывает раздел, видит «пока ни одной» и закрывает. Шаблон
снимает выбор «что вообще считать привычкой»: название, зачем она и во
сколько о ней напомнить — уже проставлены, остаётся нажать.
"""

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class HabitTemplate:
    """`slug` — стабильный идентификатор для кнопок и API: по нему
    шаблон находят, поэтому переименовывать его нельзя (в отличие от
    `title`, который можно править свободно)."""

    slug: str
    emoji: str
    title: str
    description: str
    reminder_time: time | None


HABIT_TEMPLATES: tuple[HabitTemplate, ...] = (
    HabitTemplate(
        slug="workout",
        emoji="🤸",
        title="Зарядка",
        description="10–15 минут движения утром, до дел и телефона",
        reminder_time=time(8, 0),
    ),
    HabitTemplate(
        slug="water",
        emoji="💧",
        title="8 стаканов воды",
        description="Считается день, когда выпил около двух литров",
        reminder_time=time(12, 0),
    ),
    HabitTemplate(
        slug="reading",
        emoji="📖",
        title="Чтение",
        description="20 страниц или 20 минут — что раньше",
        reminder_time=time(21, 0),
    ),
    HabitTemplate(
        slug="steps",
        emoji="🚶",
        title="10 000 шагов",
        description="Прогулка считается, даже если разбита на несколько",
        reminder_time=time(19, 0),
    ),
    HabitTemplate(
        slug="sleep",
        emoji="🌙",
        title="Лечь до 23:00",
        description="Телефон в сторону за полчаса до сна",
        reminder_time=time(22, 30),
    ),
    HabitTemplate(
        slug="no_sugar",
        emoji="🍬",
        title="День без сладкого",
        description="Без десертов и сладких напитков",
        reminder_time=None,
    ),
    HabitTemplate(
        slug="english",
        emoji="🗣",
        title="Английский",
        description="15 минут: приложение, сериал в оригинале или разговор",
        reminder_time=time(20, 0),
    ),
    HabitTemplate(
        slug="plan_day",
        emoji="🗒",
        title="План на день",
        description="Утром выписать три главные задачи",
        reminder_time=time(9, 0),
    ),
)

_BY_SLUG = {template.slug: template for template in HABIT_TEMPLATES}


def get_template(slug: str) -> HabitTemplate | None:
    """None вместо исключения на неизвестный slug: он приходит из
    callback_data кнопки, которая могла остаться на экране с прошлой
    версии бота (тот же принцип, что у parse_callback)."""
    return _BY_SLUG.get(slug)
