# LifeOS Agent — Handoff (2026-08-14)

Вставьте этот файл целиком в начало нового чата с Claude, чтобы продолжить
работу без потери контекста.

---

## Что это

Персональный AI Chief of Staff в Telegram (single-user, см. `PROJECT.md`).
Репозиторий: `C:\Users\Honor-16-z1\Desktop\Автоматизация жизни\LifeOS-Agent`,
код в `lifeos-agent/` (FastAPI + PostgreSQL + python-telegram-bot).

Git: приватный репо на GitHub — [gezhenko95-jpg/LifeOS-Agent](https://github.com/gezhenko95-jpg/LifeOS-Agent),
ветка `main`, remote настроен, коммитим по фиче. 333 теста, `ruff`/`black` чисто.

```bash
cd lifeos-agent && python -m pytest -q && python -m ruff check app tests migrations && python -m black --check app tests migrations
```

---

## Что уже работает (всё проверено вживую в реальном Telegram, не только тестами)

**Базовое (было на прошлой сессии):** Tasks, Memory, Habits, Goals,
Conversation Engine (rule-based + AI-фолбэк), REST API, `/ui`, постоянное
меню и inline-кнопки.

**Добавлено в этой сессии:**
- **AI-инсайт** в утреннем брифинге (короткая фраза от AI поверх шаблона).
- **`Intent.QUERY_TASKS_BY_DATE`** — «что на завтра» фильтрует задачи по
  дате, закрывает acceptance-тест `MVP.md`.
- **Проактивные вопросы 3×/день** (`app/proactive/`) — бот сам спрашивает
  про цели/привычки/проекты/предпочтения, ответ через AI создаёт
  структурные записи. `MUSING_QUESTIONS` — иногда доп. вопрос "для
  затравки" (экзистенциальный/факт).
- **Recall** — «напомни, что я говорил про X» ищет по памяти.
- **Recurring tasks** — «каждый понедельник ...», «каждый день ...»,
  автосоздание следующей при завершении.
- **Weekly digest** (воскресенье) + **настоящие графики** (matplotlib:
  задачи по неделям + тепловая карта привычек) — картинкой в Telegram.
- **Нэджи** — дедлайн цели скоро/обрыв стрика привычки; празднование
  вехи стрика (7/30/100 дней).
- **Быстрые кнопки** после создания задачи (❗ Важно / 📅 Завтра),
  индикатор «печатает…».
- **Дневной ритм переосмыслен** (5 слотов, без увеличения числа
  сообщений — см. `flows/009-daily-rhythm.md`):
  - 08:00 брифинг + график
  - 10:30 вопрос про сон / gap-вопрос
  - 14:00 «как дела» + табличка привычек (тап — отметить)
  - 19:00 итоги дня + иногда gap-вопрос
  - 21:00 AI-вопрос для дневника (не банальный)
- **Дневник без трения** — кнопка «📝 Дневник» в меню, следующее
  сообщение уходит в дневник без префикса `дневник:` (категория
  `journal` в `pending_prompts`, без AI-разбора).
- **Два реальных бага найдены и починены**:
  1. AI не знал текущую дату → придумывал даты в прошлом. Исправлено —
     дата теперь в каждом system-промпте.
  2. **Таймзона контейнеров была UTC, а не Москва** — все 5 сообщений
     приходили на 3 часа позже. Исправлено (`tzdata` + `TZ=Europe/Moscow`
     в Dockerfile/docker-compose.yml) — с сегодняшнего вечера расписание
     верное, с завтра — полностью по расписанию.

### Деплой

`docker compose up -d --build` в `lifeos-agent/`. Три контейнера:
`db`, `api`, `bot`. Docker Desktop иногда падает (движок отдаёт 500) —
если `docker ps` не отвечает, попросить пользователя перезапустить
Docker Desktop вручную (Quit → запустить снова), само не оживает.

```bash
docker ps                              # db/api/bot должны быть Up
docker logs lifeos-agent-bot-1 --tail 20
docker exec lifeos-agent-bot-1 date    # должен показывать MSK, не UTC
```

`.env` (не в git): `owner_telegram_user_id`, `telegram_bot_token`,
`openrouter_api_key` — все заполнены и рабочие (модель `openai/gpt-4o-mini`).

---

## Архитектура и правила

- **Spec-first**: `specs/NNN-name.md` + `flows/NNN-name.md` до кода. См.
  `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`.
- Слои: `API/Telegram → Service → Repository → DB`. `ConversationEngine`
  Telegram-агностичен (никаких `InlineKeyboardMarkup` и т.п. внутри).
- ADR-004: простой код вместо AI, где возможно.
- Для каждой фичи крупнее одной правки: `EnterPlanMode` → план →
  реализация → `pytest`/`ruff`/`black` → `docker compose up -d --build`
  → живая проверка на реальных данных владельца внутри контейнера →
  коммит. Крупные фичи бить на части с отдельными коммитами, не одним
  большим PR.
- **Тестовые данные владельца**: если для живой проверки нужно
  создать/изменить что-то в реальной БД — обязательно убирать за собой
  после проверки (уже несколько раз забывал — проверять `tasks`/`goals`/
  `memory_entries` на мусор перед коммитом).

---

## Известные грабли

1. **Docker Desktop engine иногда падает** (500 на API) — процессы живы,
   но контейнеры не поднимаются; чинится только ручным перезапуском
   Docker Desktop пользователем.
2. **Контейнеры без `tzdata` молча работают в UTC**, даже если задать
   `TZ` — теперь исправлено, но если будет новый сервис/контейнер —
   не забыть про `tzdata` + `TZ=Europe/Moscow`.
3. Порядок при миграциях: `alembic upgrade head` до `docker compose up
   -d --build`.
4. Windows `curl.exe` манглит кириллицу в `-d '...'` — `--data-binary @file.json`.
5. Пользователь просил быть короче в чате — меньше объяснений, больше
   действий, не пересказывать то, что уже понятно из контекста.

---

## Что осталось / идеи на будущее

Всё из `MVP.md` реализовано. Дальше — по желанию пользователя, не
срочно:
- Daily/Weekly Review, Calendar, Reports/Analytics (`ROADMAP.md` Phase 4-5).
- Текстовые мини-графики (progress-бары/эмодзи-heatmap) — обсуждали,
  не делали, ушли сразу к matplotlib.
- Деплой на постоянный сервер (обсуждали VPS ~150-350₽/мес, SmartApe
  HDD S1 240₽/мес — пользователь пока отложил, "потом").
- Возможные мелкие улучшения: подтверждение перед удалением, `/stats`
  команда по запросу (не только в дайджесте).

---

## Структура репозитория

```
LifeOS-Agent/
├── AGENTS.md, ARCHITECTURE.md, DECISIONS.md, MVP.md, PROJECT.md,
│   ROADMAP.md, SYSTEM.md, HANDOFF.md
├── specs/000-008 + README             — спеки (proactive-engagement,
│                                         weekly-digest, nudges — новые)
├── flows/001-009 + README             — сценарии (009-daily-rhythm — новый)
└── lifeos-agent/
    ├── app/
    │   ├── ai/client.py                — OpenRouter-клиент
    │   ├── api/                        — REST (tasks/memory/habits/goals/health)
    │   ├── conversation/                — parser, date_parser, engine, ai_fallback, intent
    │   ├── goals/ habits/ memory/ tasks/ — models/repository/service/schemas
    │   ├── proactive/                   — NEW: models/repository/service/questions/ai_extract
    │   ├── scheduler/                   — briefing, weekly_digest, nudges, charts,
    │   │                                   evening_checkin, evening_reflection (все NEW/расширены)
    │   ├── telegram/                    — bot, handlers, jobs, keyboards, callbacks, runner
    │   ├── web/static/index.html        — /ui
    │   ├── core/config.py               — Settings
    │   └── main.py
    ├── migrations/versions/001..009     — 009 = recurrence+completed_at на tasks
    ├── tests/                           — 333 теста
    ├── docker-compose.yml, Dockerfile   — TZ=Europe/Moscow, tzdata
    └── pyproject.toml                   — + matplotlib
```
