# Goals Service Specification

---

# Цель

Goals Service отвечает за структурированный трекинг долгосрочных целей:
название, целевая дата, процент выполнения, статус. Это единственный
сервис, который имеет право читать и изменять таблицу `goals`.

---

# Отличие от Memory (тип `goal`)

В Memory Service (см. `specs/001-memory.md`) уже есть тип записи `goal` —
он остаётся для случайных упоминаний целей в разговоре (текст без
структуры). Goals Service — отдельный, более точный трекер с прогрессом
и датой. Начиная с этой версии, блок "🎯 цели" в утреннем брифинге берёт
данные из Goals Service, а не из Memory — чтобы не показывать одну и ту
же цель дважды. Блок "📁 проекты" остаётся от Memory (Projects Service не
строим).

Chat-команд для Goals в этой версии нет — управление через REST API,
как и у Memory (в отличие от Habits, цели не требуют ежедневного касания).

---

# Модель данных

`app/goals/models.py::Goal`:

| Поле | Тип | Описание |
|---|---|---|
| id | int | первичный ключ |
| telegram_user_id | bigint | владелец цели |
| title | str(255) | название |
| target_date | date, nullable | целевая дата |
| progress | int, 0..100, default 0 | процент выполнения |
| status | str(20) | `active` / `completed` / `abandoned` |
| created_at | datetime | дата создания |
| updated_at | datetime, nullable | дата последнего обновления |

---

# API

Слой `app/api/goals.py` — только вызовы сервиса.

- `POST /goals` — создать цель (title, target_date?)
- `GET /goals?telegram_user_id=...` — список активных целей
- `PATCH /goals/{id}` — обновить (progress/target_date/status)
- `DELETE /goals/{id}` — удалить

---

# Сервис (`app/goals/service.py`)

- `create_goal(telegram_user_id, title, target_date=None) -> Goal`
- `list_active_goals(telegram_user_id) -> list[Goal]`
- `update_progress(goal_id, progress: int) -> Goal | None` — 0..100,
  вне диапазона → `ValueError`; `progress=100` не меняет статус
  автоматически (завершение — отдельное действие)
- `complete_goal(goal_id) -> Goal | None` — статус → `completed`
- `delete_goal(goal_id) -> Goal | None`

---

# Definition of Done

- цель создаётся, прогресс обновляется в допустимом диапазоне;
- список активных целей не включает завершённые/заброшенные;
- покрыт unit-тестами (service с замоканным repository) и интеграционным
  тестом API;
- утренний брифинг показывает цели с процентом из Goals Service.
