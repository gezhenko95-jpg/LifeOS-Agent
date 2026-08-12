# LifeOS Agent — Handoff (2026-08-12)

Вставьте этот файл целиком в начало нового чата с Claude, чтобы продолжить
работу без потери контекста.

---

## Что это

Персональный AI Chief of Staff в Telegram (проект **single-user** — см.
`PROJECT.md`). Репозиторий: `C:\Users\Honor-16-z1\Desktop\Автоматизация
жизни\LifeOS-Agent`. Приложение — в подпапке `lifeos-agent/` (FastAPI +
PostgreSQL + python-telegram-bot).

**Git только что инициализирован** (`git init` + первый коммит,
119 файлов). Ветка `master`, коммит один. **Remote не настроен** — это
только локальная копия, реального бэкапа нет. Первое, что стоит сделать —
завести GitHub/GitLab-репозиторий и `git push`.

---

## Что уже работает (проверено вживую, не только тестами)

- **Tasks** — создание из текста («Завтра купить молоко», приоритет
  «важно»/«срочно»), список/выполнение/удаление, REST `/tasks`.
- **Напоминания** — «через N минут/часов», «в HH:MM» → точное время,
  фоновая джоба каждую минуту шлёт `⏰ Напоминание`, не дублирует.
- **Memory** — факты/предпочтения/цели-текстом/проекты/journal, REST `/memory`.
- **Habits** — «привычки», «привычка чтение» (стрик), REST `/habits`.
- **Goals** — прогресс/дедлайн, REST `/goals`, кнопки ➖10%/➕10% в боте.
- **Conversation Engine** — rule-based (`app/conversation/parser.py`,
  `date_parser.py`), AI-фолбэк через OpenRouter только когда правила не
  поняли сообщение (`ai_fallback.py`) — **сейчас выключен**, `openrouter_api_key`
  пуст в `.env`.
- **Scheduler** — утренний брифинг (08:00), вечерняя рефлексия (21:00),
  напоминания о задачах (раз в минуту) — все три джобы через
  `python-telegram-bot` `JobQueue`, гейтятся `owner_telegram_user_id`.
- **Telegram UI** — постоянное меню снизу (📋 Задачи/🔁 Привычки/🎯
  Цели/❓ Помощь через `ReplyKeyboardMarkup`) + inline-кнопки под списками
  (✅/🗑, ➖10%/➕10%) через `CallbackQueryHandler` (`app/telegram/keyboards.py`,
  `callbacks.py`).
- **`/ui`** — простейший веб-дашборд (статический HTML+JS,
  `app/web/static/index.html`), тот же REST API. Пользователь предпочитает
  Telegram-кнопки, `/ui` — запасной вариант, не основной.
- **184 теста проходят**, `ruff`/`black` чисто. Полная верификация:
  ```bash
  cd lifeos-agent && python -m pytest -q && python -m ruff check app tests migrations && python -m black --check app tests migrations
  ```

### Деплой сейчас

`docker-compose up -d` в `lifeos-agent/` — три контейнера: `db` (Postgres),
`api` (FastAPI на :8000), `bot` (long polling). Все с `restart:
unless-stopped` — переживут перезапуск Docker, но **Docker Desktop нужно
включить на автозапуск при входе в Windows** (Settings → General → Start
Docker Desktop when you sign in) — контейнеры не поднимутся, если сам
Docker Desktop не запущен.

`.env` (не в git, реально заполнен на машине пользователя):
`owner_telegram_user_id=414825951`, `telegram_bot_token` установлен,
`morning_briefing_hour=8`, `evening_reflection_hour=21`,
`task_reminders_interval_seconds=60`, `openrouter_api_key=` (пусто).

Проверить статус в начале сессии:
```bash
docker ps                              # db/api/bot должны быть Up
docker logs lifeos-agent-bot-1 --tail 20
```

---

## Архитектура и правила (важно соблюдать дальше)

- **Spec-first**: новая фича → сначала `specs/NNN-name.md` (+ `flows/NNN-name.md`
  для пользовательских сценариев), потом код. См. `AGENTS.md` (конституция),
  `DECISIONS.md` (ADR), `ARCHITECTURE.md`, `SYSTEM.md`.
- Слои: `API → Service → Repository → DB`. LLM никогда не трогает БД
  напрямую. `ConversationEngine` (specs/003) Telegram-агностичен — не
  должен знать про `InlineKeyboardMarkup`/`ReplyKeyboardMarkup` (эти типы
  живут только в `app/telegram/`).
- ADR-004: простой код предпочтительнее LLM, где возможно. AI — только
  фолбэк/анализ, не основной путь.
- Файлы ≤ 250–300 строк, типизация обязательна, тесты на новую логику.
- В этой сессии для каждой фичи размером больше «одной правки» использовался
  `EnterPlanMode` → план → `ExitPlanMode` → реализация → `pytest`/`ruff`/`black`
  → `docker-compose up -d --build` → живая проверка в Telegram с
  параллельным `Monitor` на `docker logs -f lifeos-agent-bot-1`. Этот же
  цикл стоит повторять для новых фич.

---

## Известные грабли, обнаруженные в этой сессии

1. **Порядок при деплое**: сначала `alembic upgrade head`, потом
   `docker-compose up -d --build` — если наоборот, новый код на секунды
   упирается в старую схему БД (было, самовосстановилось, но лучше не
   допускать).
2. **FK без CASCADE** — уже пофикшено (`migrations/007_cascade_delete_habit_logs.py`):
   удаление привычки с логами падало. Если будут новые связи
   родитель-потомок (например, у Goals появятся milestones) — сразу
   ставить `ondelete="CASCADE"`.
3. **Windows `curl.exe` манглит кириллицу** в `-d '...'` инлайн — использовать
   `--data-binary @file.json`.
4. **Telegram-токен один раз засветился** в выводе `docker compose config`
   (стандартное поведение, не мой косяк) — виден в истории этой сессии.
   Если это беспокоит — перевыпустить токен у @BotFather (`/revoke`).
5. Superseded: `.claude/launch.json` (в `Автоматизация жизни/.claude/`, не
   в `LifeOS-Agent/.claude/`) настроен для просмотра `http://localhost:8000`
   через встроенный браузер Claude — можно удалить, если не нужно.

---

## Разрыв с MVP.md — что реально осталось (приоритеты)

`MVP.md` — эталон, что должен уметь MVP. Сверка с текущим состоянием:

1. **[ВАЖНО] Не реализовано: вопрос «Что я собирался сделать завтра?»**
   Это буквально acceptance-тест в `MVP.md` («MVP считается готовым если...
   пользователь может задать вопрос и получить правильный ответ»). Сейчас
   «покажи задачи» показывает ВСЕ активные задачи, а не отфильтрованные по
   упомянутой дате. Нужно: распознавать вопрос-с-датой («что на завтра»,
   «что было на пятницу») и фильтровать `list_active_tasks` по `due_date`
   через уже готовый `date_parser.extract_due_date`. Скорее всего — новый
   `Intent.QUERY_BY_DATE` в `app/conversation/{intent,parser}.py` +
   обработка в `engine.py`, без изменений в Tasks Service.

2. **[СРЕДНЕ] Утренний брифинг без AI-анализа.** `MVP.md`/`flows/001` хотят
   «короткий AI-анализ» в брифинге. Сейчас `app/scheduler/briefing.py` —
   чистый шаблон. `AIClient` (`app/ai/client.py`) уже есть и протестирован
   (используется в `ai_fallback.py`) — можно опционально (если
   `openrouter_api_key` задан) добавить одну короткую фразу-инсайт в конец
   брифинга, тем же клиентом. Пользователю сначала нужно решить, заводить
   ли ключ OpenRouter (сейчас пуст).

3. **[НИЗКО, вне MVP]** Daily/Weekly Review, Calendar, Reports/Analytics —
   `ROADMAP.md` Phase 4-5, не начаты. Brainstorm на будущее, не срочно.

---

## Рекомендуемый порядок следующих шагов

1. `git remote add origin ...` + `git push` — реальный бэкап (сейчас только
   локально). Решить, GitHub или GitLab, приватный репозиторий.
2. Реализовать `Intent.QUERY_BY_DATE` — закрывает буквальный acceptance-тест
   MVP.md, самый весомый оставшийся пункт.
3. Определиться с OpenRouter-ключом → если да, добавить AI-инсайт в брифинг.
4. Дальше — по желанию пользователя: Daily/Weekly Review, Calendar, Reports.
5. Регулярно: `docker-compose up -d --build` после каждого изменения кода,
   `alembic upgrade head` после каждой новой миграции, `git commit` после
   каждой фичи (сейчас коммитов нет кроме первого — стоит начать коммитить
   по шагам, а не одним большим коммитом в будущем).

---

## Структура репозитория (для навигации)

```
LifeOS-Agent/
├── AGENTS.md, ARCHITECTURE.md, DECISIONS.md, MVP.md, PROJECT.md,
│   ROADMAP.md, SYSTEM.md          — документация проекта (читать первой)
├── specs/NNN-*.md                  — спеки фич (5 файлов + README)
├── flows/NNN-*.md                  — пользовательские сценарии (5 + README)
├── designs/001-task-flow.md        — пустой, не используется
└── lifeos-agent/                   — сам Python-проект
    ├── app/
    │   ├── ai/client.py             — OpenRouter-клиент
    │   ├── api/                     — REST-роутеры (tasks/memory/habits/goals/health)
    │   ├── conversation/            — parser.py, date_parser.py, engine.py, ai_fallback.py, intent.py
    │   ├── goals/ habits/ memory/ tasks/  — по каждому: models/repository/service/schemas
    │   ├── scheduler/briefing.py     — сборка текста утреннего брифинга
    │   ├── telegram/                 — bot.py, handlers.py, jobs.py, keyboards.py, callbacks.py, runner.py
    │   ├── web/static/index.html     — /ui дашборд
    │   ├── core/config.py            — Settings (pydantic-settings, читает .env)
    │   ├── db/                       — session.py, base.py
    │   └── main.py                   — FastAPI app, роутеры, StaticFiles /ui
    ├── migrations/versions/001..007  — все миграции по порядку
    ├── tests/                        — 184 теста, зеркалит структуру app/
    ├── docker-compose.yml, Dockerfile
    ├── .env (не в git) / .env.example
    └── pyproject.toml
```
