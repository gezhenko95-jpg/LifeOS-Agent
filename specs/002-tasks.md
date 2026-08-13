# Tasks Service Specification

---

# Цель

Tasks Service отвечает за хранение и управление задачами пользователя.

Это единственный сервис, который имеет право читать и изменять таблицу `tasks`.

---

# Бизнес-требования

- пользователь создает задачу обычным сообщением в Telegram;
- задача может иметь срок (due_date) или не иметь;
- пользователь может посмотреть список активных задач;
- пользователь может отметить задачу выполненной по названию (без id);
- пользователь может удалить задачу по названию.

---

# Пользовательские сценарии

См. `flows/002-add-task.md` и `flows/003-manage-tasks.md`.

---

# Модель данных

Используется существующая модель `app/tasks/models.py::Task`:

| Поле | Тип | Описание |
|---|---|---|
| id | int | первичный ключ |
| telegram_user_id | bigint | владелец задачи |
| title | str(255) | название |
| due_date | datetime, nullable | срок выполнения |
| status | str(50) | `active` / `completed` / `cancelled` |
| priority | str(20) | `low` / `normal` / `high`, default `normal` |
| created_at | datetime | дата создания |
| reminded_at | datetime, nullable | когда отправлено напоминание, `NULL` — ещё не отправлено |
| recurrence | str(20), nullable | `daily` / `weekly` / `monthly` / `NULL` (не повторяется), см. Recurring Tasks ниже |
| completed_at | datetime, nullable | момент завершения задачи, `NULL` — ещё не завершена (migration `009_add_recurrence_completed_at`) |

## Приоритет (Planner, см. ROADMAP.md Phase 1)

Отдельного Planner-сервиса нет — приоритет и сортировка дня реализованы
как часть Tasks Service:

- `list_active_tasks` сортирует задачи: `high` → `normal` → `low`,
  внутри одного приоритета — по порядку создания.
- Rule-based парсер (`app/conversation/parser.py`) распознаёт слова
  «важно»/«срочно» в сообщении → `priority="high"`, слово вырезается
  из названия так же, как дата.
- Утренний брифинг (`app/scheduler/briefing.py`) ничего не знает про
  приоритет напрямую — он получает уже отсортированный список задач
  от `TaskService`, поэтому важные задачи на сегодня естественным
  образом становятся «главной задачей дня».

---

## Напоминания (Notifications)

`app/conversation/date_parser.py` понимает не только целые дни, но и:

- относительное время: «через 10 минут», «через 2 часа» — от момента сообщения;
- время суток: «в 18:30» — сегодня, если время ещё не наступило, иначе завтра.

Каждый паттерн проверяется независимо и возвращается первым совпадением —
«завтра в 15:00» распознается только как «завтра» (09:00 по умолчанию),
комбинация день+время не разбирается (упрощение, а не баг).

Джоба `app/telegram/jobs.py::send_task_reminders_job` (см.
`app/telegram/bot.py::_register_task_reminders`) раз в
`task_reminders_interval_seconds` (по умолчанию 60) секунд вызывает
`TaskService.list_due_reminders()` — активные задачи с `due_date <= сейчас`
и `reminded_at IS NULL`, — шлёт `⏰ Напоминание: «...»` и вызывает
`mark_reminded`. Без фильтра по пользователю — проект single-user
(PROJECT.md).

---

## Recurring Tasks

Задача может повторяться: `daily` / `weekly` / `monthly` (поле
`recurrence`). При завершении такой задачи (через чат или REST)
автоматически создаётся следующее вхождение — новая активная задача с
тем же названием/приоритетом/`recurrence`.

**Распознавание в чате** (`app/conversation/date_parser.py::extract_recurrence`,
вызывается в `parser.py` перед `extract_due_date` в ADD_TASK-ветке):

| Фраза | recurrence |
|---|---|
| «каждый день», «ежедневно» | `daily` |
| «каждую неделю», «еженедельно» | `weekly` |
| «каждый месяц», «ежемесячно» | `monthly` |
| «каждый/каждую <день недели>» (например «каждый понедельник») | `weekly`, с конкретным днём (фраза подменяется на «в <день недели>», чтобы её нашёл уже существующий `extract_due_date`) |

**Дата первого вхождения**: если распознан день недели — берётся он
(через `extract_due_date`). Если конкретной даты нет (`daily`/`weekly`
без дня/`monthly`) — `TaskService.create_task` сам вычисляет ближайшее
повторение от текущего момента (`_advance_date(now, recurrence)`) —
задача без даты не должна оставаться "вне расписания".

**Следующее вхождение** (`TaskService._maybe_create_next_occurrence`,
вызывается из `complete_task_by_title` и из `update_task` при переходе
`active → completed`): дата следующего вхождения считается от
**исходного `due_date` завершённой задачи**, а не от момента
завершения — так серия не "плывёт", если пользователь отметил задачу
выполненной с опозданием. `monthly` учитывает разную длину месяцев
(31 января + месяц → 28/29 февраля, через `calendar.monthrange`).

Ответ бота: при создании — `🔁` после названия; при завершении —
дополнительная строка «Создал следующую — она повторится
автоматически.».

---

# API

Слой `app/api/tasks.py` — только вызовы сервиса, без бизнес-логики.

- `POST /tasks` — создать задачу (`TaskCreate`: telegram_user_id, title, due_date?, priority?, recurrence?)
- `GET /tasks?telegram_user_id=...` — список активных задач пользователя
- `PATCH /tasks/{id}` — обновить (например, статус, recurrence) — переход в `completed` тоже создаёт следующее вхождение, если задача повторяющаяся
- `DELETE /tasks/{id}` — удалить задачу

---

# Сервис (`app/tasks/service.py`)

- `create_task(telegram_user_id, title, due_date=None, priority="normal", recurrence=None) -> Task`
- `list_active_tasks(telegram_user_id) -> list[Task]` — отсортирован по приоритету
- `complete_task_by_title(telegram_user_id, title_query) -> Task | None` — нечеткий поиск подстроки среди активных задач пользователя; для повторяющейся задачи создаёт следующее вхождение
- `update_task(task_id, ..., recurrence=None) -> Task | None` — переход `active → completed` тоже создаёт следующее вхождение
- `delete_task_by_title(telegram_user_id, title_query) -> Task | None`
- `list_due_reminders() -> list[Task]` — активные задачи с наступившим сроком, без напоминания
- `mark_reminded(task_id) -> Task | None`
- `count_tasks_completed_since(telegram_user_id, since) -> int` — для еженедельного дайджеста (`specs/007-weekly-digest.md`)

Правило: сервис не знает про Telegram и про формат сообщений — только про задачи.

---

# Репозиторий (`app/tasks/repository.py`)

Только работа с БД через `AsyncSession`:

- `add(task: Task) -> Task`
- `get_by_id(task_id) -> Task | None`
- `list_by_user(telegram_user_id, status=None) -> list[Task]`
- `save(task: Task) -> Task`
- `delete(task: Task) -> None`
- `list_due_unreminded(now) -> list[Task]`
- `count_completed_since(telegram_user_id, since) -> int`

Никакой бизнес-логики (поиск по подстроке, форматирование ответа — не здесь).

---

# Definition of Done

Tasks Service считается готовым, если:

- задача создается и сохраняется в БД;
- задача находится по подстроке названия для complete/delete;
- список задач возвращает только активные;
- повторяющаяся задача при завершении создаёт следующее вхождение
  (и через чат, и через REST `PATCH`), дата считается от исходного
  `due_date`, с корректным клампом конца месяца для `monthly`;
- покрыт unit-тестами (service с замоканным repository) и интеграционным тестом API;
- REST API отвечает на все 4 операции.
