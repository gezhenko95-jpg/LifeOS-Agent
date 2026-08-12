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

# API

Слой `app/api/tasks.py` — только вызовы сервиса, без бизнес-логики.

- `POST /tasks` — создать задачу (`TaskCreate`: telegram_user_id, title, due_date?)
- `GET /tasks?telegram_user_id=...` — список активных задач пользователя
- `PATCH /tasks/{id}` — обновить (например, статус)
- `DELETE /tasks/{id}` — удалить задачу

---

# Сервис (`app/tasks/service.py`)

- `create_task(telegram_user_id, title, due_date=None, priority="normal") -> Task`
- `list_active_tasks(telegram_user_id) -> list[Task]` — отсортирован по приоритету
- `complete_task_by_title(telegram_user_id, title_query) -> Task | None` — нечеткий поиск подстроки среди активных задач пользователя
- `delete_task_by_title(telegram_user_id, title_query) -> Task | None`
- `list_due_reminders() -> list[Task]` — активные задачи с наступившим сроком, без напоминания
- `mark_reminded(task_id) -> Task | None`

Правило: сервис не знает про Telegram и про формат сообщений — только про задачи.

---

# Репозиторий (`app/tasks/repository.py`)

Только работа с БД через `AsyncSession`:

- `add(task: Task) -> Task`
- `get_by_id(task_id) -> Task | None`
- `list_by_user(telegram_user_id, status=None) -> list[Task]`
- `delete(task: Task) -> None`

Никакой бизнес-логики (поиск по подстроке, форматирование ответа — не здесь).

---

# Definition of Done

Tasks Service считается готовым, если:

- задача создается и сохраняется в БД;
- задача находится по подстроке названия для complete/delete;
- список задач возвращает только активные;
- покрыт unit-тестами (service с замоканным repository) и интеграционным тестом API;
- REST API отвечает на все 4 операции.
