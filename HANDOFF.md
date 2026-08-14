# LifeOS Agent — Handoff (2026-08-14, вечер)

Вставьте этот файл целиком в начало нового чата с Claude, чтобы продолжить
работу без потери контекста. Он длиннее прошлой версии — за один день
проект вырос сильно (5 новых фич + переезд на постоянный сервер).

---

## Философия проекта (что это и зачем)

**LifeOS Agent** — персональный AI Chief of Staff в Telegram, single-user
(только для владельца, не multi-tenant). Не чат-бот и не менеджер задач —
цель — снять с человека когнитивную нагрузку: бот сам держит контекст
(задачи/привычки/цели/память/дневник), проактивно напоминает и спрашивает,
а не только отвечает на команды. Подробно — `PROJECT.md`.

Ключевые принципы (закреплены как ADR в `DECISIONS.md`):
- **ADR-004: простой код лучше LLM.** AI используется только там, где
  задачу реально нельзя решить обычным кодом (понимание естественного
  языка, анализ картинки). Статистика/агрегации/бизнес-логика — всегда
  простой Python, никогда не через LLM.
- **ADR-001: модульный монолит.** Не микросервисы.
- **ADR-002: LLM никогда не трогает БД напрямую** — только через
  сервисный слой.
- **ADR-005: один сервис — одна ответственность.**
- **Spec-first (ADR-003)**: `specs/NNN-name.md` + `flows/NNN-name.md` до
  кода, реализация только после утверждения. Для фичи крупнее одной
  правки: спека → реализация → `pytest`/`ruff`/`black` → деплой → живая
  проверка на реальных данных владельца → коммит. Крупные фичи бить на
  части с отдельными коммитами.
- **Тестовые данные владельца**: если для живой проверки нужно
  создать/изменить что-то в реальной БД — обязательно убирать за собой
  после проверки.
- Пользователь просит быть короче в чате — меньше объяснений, больше
  действий.

---

## Доступы, пароли, ссылки (нужны почти в каждой сессии)

### Репозиторий
- GitHub: [gezhenko95-jpg/LifeOS-Agent](https://github.com/gezhenko95-jpg/LifeOS-Agent),
  ветка `main`. Локально:
  `C:\Users\Honor-16-z1\Desktop\Автоматизация жизни\LifeOS-Agent`, код в
  `lifeos-agent/`.

### Продакшн-сервер (Hostkey, Нидерланды) — ГЛАВНЫЙ, бот тут работает 24/7
- IP: `148.135.208.126`, домен: **`lifeos-agent.ru`**
- SSH: `ssh lifeos-eu` (алиас уже в `~/.ssh/config` на этой машине,
  ключ `~/.ssh/lifeos_main`). Вход **только по ключу** — пароль
  (был `pSz08%19EZ` при переустановке) отключён намеренно
  (`PasswordAuthentication no`).
- Проект на сервере: `/opt/lifeos/` (Ubuntu 22.04, Docker+Compose
  предустановлены хостером). `.env` там же, не в git.
- Панель Hostkey: пользователь логинится сам (тот же email, что и
  остальное). ID сервера в панели — `8015`.
- **Caddy** — реверс-прокси + автоматический HTTPS (Let's Encrypt),
  конфиг `/etc/caddy/Caddyfile` на сервере, проксирует `lifeos-agent.ru`
  → `localhost:8000` (контейнер `api`).

### Домен и DNS (SmartApe)
- Аккаунт SmartApe: `gezhenko95@gmail.com`, панель `cp.smartape.ru`.
- Домен `lifeos-agent.ru` куплен там же, действует до 2027-08-14.
- **DNS-записи домена редактируются НЕ в основной панели SmartApe**, а в
  отдельной панели DNS-хостинга:
  **https://dns-01.smartape.ru:1501**, логин `user1764200`, пароль
  `zxp19NsecLMN`. Там же добавлять/менять A-записи, если сервер сменится.
- NS-серверы домена: `ns1.smartape.ru` / `ns2.smartape.ru` — не трогать.

### Старый пробный VPS (SmartApe, Москва) — ЗАБРОШЕН, не использовать
- IP `188.127.224.144`, алиас `lifeos-vps` в `~/.ssh/config` — оставлен
  для истории, сервер бесполезен: **с российских VPS заблокирован
  api.telegram.org на уровне ТСПУ** (см. раздел "Грабли"). Пользователь
  должен был отменить эту услугу в панели SmartApe (пробный период, не
  оплачивался) — если ещё не отменил, стоит проверить/напомнить.

### Google Drive (Media Inbox, Фаза 2)
- `credentials.json` + `token.json` — на сервере в `/opt/lifeos/`, в
  git не попадают (`.gitignore`). `token.json` смонтирован в контейнер
  `bot` только для чтения (`docker-compose.yml`).
- Google Cloud проект: `LifeOS Agent` (id `lifeos-agent-505510`), OAuth
  client type Desktop app, scope `drive.file` (минимальный — видит
  только то, что сам создал).
- Если токен протухнет/понадобится переавторизация — локальный скрипт
  `scripts/drive_auth.py` (запускать НЕ в контейнере, открывает браузер).

### Ключевые секреты в `.env` на сервере (`/opt/lifeos/.env`, не в git)
`telegram_bot_token`, `owner_telegram_user_id` (=414825951),
`openrouter_api_key` (модель `openai/gpt-4o-mini`, embeddings
`openai/text-embedding-3-small`), `public_ui_url=https://lifeos-agent.ru/ui`,
`drive_token_file=token.json`. Полный список полей — `app/core/config.py`.

### Полезные ссылки
- OpenRouter (AI-провайдер — чат, vision, embeddings): https://openrouter.ai
- Hostkey (текущий сервер): https://hostkey.ru
- SmartApe (домен + DNS): https://www.smartape.ru
- Google Cloud Console (Drive OAuth): https://console.cloud.google.com

---

## Что уже сделано (полный список, всё проверено вживую)

### Базовое ядро (было до этой большой сессии)
Tasks, Memory/Journal, Habits, Goals, Conversation Engine (rule-based +
AI-фолбэк), REST API, `/ui`, постоянное меню и inline-кнопки, recurring
tasks, weekly digest с графиками (matplotlib), нэджи, проактивные
вопросы 3×/день, дневной ритм на 5 слотов (см. `flows/009-daily-rhythm.md`):
08:00 брифинг+график / 10:30 сон-или-gap-вопрос / 14:00 чек-ин+привычки /
19:00 итоги+иногда gap-вопрос / 21:00 AI-вопрос для дневника. Дневник без
трения (кнопка «📝 Дневник»).

### Добавлено в этой сессии (одним днём, по порядку)
1. **Personal Insights** (`app/insights/`) — поведенческие находки за 60
   дней: продуктивный день недели, связь дневник↔привычки, дисциплина
   дедлайнов, рекорд серии привычки. Детерминированный код (ADR-004,
   без AI). Кнопка «📊 Инсайты» + фоновая ежемесячная рассылка.
2. **Watchlist Фаза 1** (`app/watchlist/`) — «посмотреть/прочитать
   позже», добавление свободным текстом («книга X», «посмотреть фильм
   Y», «добавь сериал Z» — много вариантов триггеров, см.
   `app/conversation/parser.py::_WATCHLIST_TRIGGERS`), кнопка «🎬
   Посмотреть», AI-рекомендация («🎲 Порекомендуй»).
3. **Media Inbox / Watchlist Фаза 2** (`app/drive/`, `app/media_inbox/`)
   — фото боту → AI-vision классифицирует (эскиз/фильм/книга/другое) →
   грузит на Google Drive в `LifeOS/{Эскизы|Кино и книги|Разное}` →
   фильм/книга с читаемым названием ещё и попадает в Watchlist. После
   успешной загрузки исходное фото **удаляется из чата** (не копится в
   кеше Telegram, но только при успехе — если Drive не сохранил, фото
   остаётся).
4. **Семантический поиск по памяти** (`app/memory/embeddings.py`) —
   embeddings через OpenRouter, фоновая доливка (job каждые 5 мин),
   `ConversationEngine._recall`: сначала точный поиск, если пусто и есть
   AI — поиск по смыслу (косинусное сходство, без pgvector — Python).
5. **LIST_WATCHLIST intent** — «список книг»/«покажи фильмы»/«полка»/
   «что посмотреть» теперь показывают список (раньше уходило в
   ADD_TASK или перехватывалось общим «покажи» → задачи).
6. **`/ui` дашборд** — новая секция «📚🎬 Полка» (книги/фильмы по
   статусам to_watch/done раздельно), «Итоги недели» (задач выполнено),
   полоска-индикатор силы серии у привычек. Новый REST
   `app/api/watchlist.py`, `GET /tasks/stats`.
7. **Кнопка «🌐 Сайт»** — открывает `/ui` (через inline-URL-кнопку,
   ReplyKeyboard сама так не умеет).
8. **Переезд на постоянный сервер** — см. ниже отдельным разделом,
   самая крупная часть сессии.

### Найденные и починенные баги
1. AI не знал текущую дату → чинили раньше (промпт с датой).
2. Таймзона контейнеров UTC вместо MSK → чинили раньше (`tzdata`+`TZ`).
3. **Дневной чек-ин (14:00) не открывал `pending_prompt`** — свободный
   ответ на «как дела» создавал задачу вместо записи в дневник. Починено
   (открывает `category="journal"`, как утро/вечер).
4. **`_remove_keyword` оставлял запятую** после вырезанного триггер-слова
   («посмотреть, 21 и больше» → «, 21 и больше»). Починено (`.strip("
   ,:—-")`).
5. **JSON-колонка `MemoryEntry.embedding`**: Python `None` по умолчанию
   пишется как JSON `null`, а не SQL `NULL` → `IS NULL`/`IS NOT NULL`
   молча ломались. Фикс — `JSON(none_as_null=True)`.
6. **uvicorn за Caddy генерировал редиректы с `http://`** вместо
   `https://` (не знал про `X-Forwarded-Proto`). Фикс — флаги
   `--proxy-headers --forwarded-allow-ips=*`.
7. **Postgres-пароль разошёлся с `.env`** после случайного пересоздания
   контейнера `db` (именованный volume пережил пересоздание, но пароль
   роли `postgres` применяется только при первой инициализации пустого
   volume — если пароль до этого отличался, `POSTGRES_PASSWORD` в
   `docker-compose.yml` его не меняет). Чинится вручную:
   `ALTER USER postgres WITH PASSWORD '...';` внутри контейнера `db`.

---

## Переезд на постоянный сервер — что произошло и почему так

**Проблема**: Telegram-бот на VPS в России переставал отвечать —
`api.telegram.org` зависал/таймаутил. Причина — **массовая блокировка
Telegram API на уровне ТСПУ для российских дата-центров** (актуально с
марта 2026, подтверждено и живым тестом, и веб-поиском: провайдеры РФ
дропают пакеты к api.telegram.org на уровне сети, это не проблема кода
или конкретного хостера).

**Решение**: перенести сервер физически за пределы РФ, но платить и
регистрироваться без иностранных карт/документов — такие хостеры есть
(REG.RU, Fornex, Hostkey и т.п., оплата рублями, локация в Европе).
Западные облака (Oracle/AWS/Azure/GCP) — не вариант, они полностью
прекратили работу с Россией из-за санкций ещё в 2022-м, регистрация
физически не пройдёт.

**Путь, который прошли** (для истории, не повторять): пробовали
SmartApe (Москва) → уткнулись в блокировку Telegram → рассматривали
Oracle Cloud Free Tier (заблокирован санкциями для RU) → нашли Hostkey
(Нидерланды, рубли, без иностранных документов) → взяли тариф `nano`
(2 vCPU/2 ГБ/60 ГБ, Amsterdam, ~560₽/мес почасово) → на новом сервере
Telegram сразу заработал.

**Итоговая инфраструктура**: Hostkey VPS (Нидерланды) + домен на
SmartApe + DNS указывает на Hostkey IP + Caddy на сервере для HTTPS.
Домен и DNS-хостинг **остались на SmartApe** — они не привязаны к
серверу, просто A-запись указывает на новый IP.

---

## Технические нюансы и грабли

1. **Windows + Bash-инструмент**: `cd` в кириллический путь иногда
   спонтанно фейлится (`No such file or directory`) даже если путь
   верный — просто повторить команду без `cd`, рабочая директория уже
   правильная (баг самого тула, не путей).
2. **SSH на новый VPS**: если провайдер даёт форму со вставкой
   SSH-ключа — вставлять **вручную одной строкой**, не копипастой из
   markdown-блока в чате (визуальный перенос строки в узком textarea
   иногда превращается в реальный `\n`, ключ ломается). Если ключ не
   сработал сразу — проверить консоль/VNC в панели хостера, часто там
   же лежит и реальный root-пароль (искать во вкладке
   «Конфигурация»/«Общие настройки», не в дропдауне «...»).
3. **Postgres в Docker**: `POSTGRES_PASSWORD` из `docker-compose.yml`
   применяется **только при первой инициализации** volume с пустой БД.
   Если volume пережил пересоздание контейнера с БОЛЕЕ ранним паролем —
   новый пароль в compose-файле ничего не даст, нужно
   `ALTER USER postgres WITH PASSWORD ...` вручную.
4. **`echo "x" >> .env`** — если в файле нет финального переноса строки,
   значение приклеится к предыдущей строке без разделителя. Проверять
   `cat .env` после правки, а не только код возврата команды.
5. **JSON-колонки в SQLAlchemy**: всегда `JSON(none_as_null=True)`, если
   значение может быть `None` и по нему потом фильтруют `IS NULL`.
6. **uvicorn за реверс-прокси**: всегда `--proxy-headers
   --forwarded-allow-ips=*`, иначе редиректы/схема будут неправильными.
7. **Docker Desktop (локально на Windows)** иногда падает (500 на API) —
   чинится только ручным перезапуском пользователем. Сейчас не
   актуально — локальные контейнеры остановлены (`docker compose down`),
   прод только на сервере. Волюм с локальными данными (`lifeos-agent_
   lifeos_db_data`) не удалён, на случай если понадобится локальная
   разработка.
8. Порядок деплоя: код на сервер → `alembic upgrade head` (если новая
   миграция) → `docker compose up -d --build`.
9. Алембик: id ревизии ≤32 символов (`varchar(32)` в БД) — даже если имя
   файла миграции длиннее, сам `revision =` в коде укорачивать.

### Как задеплоить изменения на прод (шпаргалка)

```bash
# с локальной машины, из lifeos-agent/
tar --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' \
    --exclude='*.pyc' --exclude='.ruff_cache' --exclude='credentials.json' \
    --exclude='token.json' --exclude='.env' -czf - . \
  | ssh lifeos-eu "cat > /tmp/lifeos.tar.gz && tar xzf /tmp/lifeos.tar.gz -C /opt/lifeos && rm /tmp/lifeos.tar.gz"

ssh lifeos-eu "cd /opt/lifeos && docker exec lifeos-api-1 alembic upgrade head"  # если есть новая миграция
ssh lifeos-eu "cd /opt/lifeos && docker compose up -d --build"
ssh lifeos-eu "docker compose -f /opt/lifeos/docker-compose.yml ps"
ssh lifeos-eu "docker logs lifeos-bot-1 --tail 20"
curl -sI https://lifeos-agent.ru/ui | head -5   # проверка HTTPS
```

---

## Архитектура (не изменилась, для справки)

Слои: `API/Telegram → Service → Repository → DB`. `ConversationEngine`
Telegram-агностичен. Каждый домен (`app/tasks/`, `app/habits/`,
`app/watchlist/` и т.д.) — свои `models.py`/`repository.py`/
`service.py`/`schemas.py`; REST-роутеры **отдельно**, в `app/api/`
(даже для watchlist — изначально по ошибке положил в `app/watchlist/
api.py`, поправил на `app/api/watchlist.py` для консистентности).

```bash
cd lifeos-agent
python -m pytest -q
python -m ruff check app tests migrations scripts
python -m black --check app tests migrations scripts
```
483 теста, всё зелёное на момент записи этого файла.

---

## Что осталось / идеи на будущее

Обсуждали с пользователем 14.08 вечером, в порядке приоритета не
зафиксированном — решать в начале новой сессии:

1. **Голосовой ввод** — Telegram voice message → распознавание речи →
   текст в `ConversationEngine` как обычное сообщение. Нужно проверить,
   даёт ли OpenRouter доступ к Whisper/STT (`/audio/transcriptions`,
   OpenAI-совместимый) тем же ключом — не проверяли живым вызовом, в
   отличие от embeddings в этой сессии. Если да — реализация похожа на
   Media Inbox (скачать файл, отправить в AI, вернуть текст).
2. **Вечерний дайджест из Telegram-каналов, на которые подписан
   пользователь** (идея пользователя) — например, дайджест новостей из
   новостных каналов, отдельно дайджест по ESG из ESG-каналов. **Важная
   техническая сложность**: Bot API (то, на чём построен весь проект)
   **не видит** подписки обычного пользователя — это может только
   "юзербот" через MTProto (Telethon/Pyrogram), логинящийся под личным
   номером телефона владельца, с отдельной сессией (эквивалент полного
   доступа к аккаунту — новый тип секрета, отдельная архитектура,
   помимо Bot API). Стоит обсудить с пользователем сокращённый MVP:
   юзербот слушает только явно перечисленные каналы (не все подписки
   разом) — сильно снижает риск/сложность.
3. **Рецепты по фото продуктов** — фото → AI определяет продукты →
   прикидывает калории + предлагает рецепт. Хорошо ложится на уже
   существующий пайплайн Media Inbox (`app/media_inbox/classify.py`) —
   просто новая категория классификации + свой follow-up промпт вместо
   загрузки на Drive.
4. **Персональные "режимы фокуса"** (идея пользователя) — пользователь
   включает тумблеры («тренировки», «привычки» и т.д.), и бот меняет
   свои проактивные сообщения под выбранный фокус (например, в режиме
   "тренировки" бот ведёт себя как тренер-мотиватор). Архитектурно —
   новая таблица настроек пользователя + прокидывание активного фокуса
   в промпты `briefing.py`/`nudges.py`/`evening_reflection.py` и т.п.
   Крупная структурная фича, не маленький тикет.
5. Из старого списка ещё не сделано: Weekly Review как отдельный
   диалог (не просто дайджест), Календарь (реальные встречи, не только
   due_date задач).
6. Мелкое: убедиться, что пробный VPS SmartApe (Москва) реально отменён
   в панели пользователем.

---

## Структура репозитория (актуализировано)

```
LifeOS-Agent/
├── AGENTS.md, ARCHITECTURE.md, DECISIONS.md, MVP.md, PROJECT.md,
│   ROADMAP.md, SYSTEM.md, HANDOFF.md (этот файл)
├── specs/000-011 + README             — 009 personal-insights, 010
│                                         media-inbox, 011 semantic-search
├── flows/001-011 + README             — 010 watchlist, 011 personal-insights
└── lifeos-agent/
    ├── app/
    │   ├── ai/client.py                — OpenRouter: chat/vision/embeddings
    │   ├── api/                        — REST: tasks/memory/habits/goals/
    │   │                                  watchlist/health
    │   ├── conversation/                — parser, date_parser, engine,
    │   │                                  ai_fallback, intent
    │   ├── drive/client.py              — Google Drive обёртка (NEW)
    │   ├── media_inbox/                 — classify.py, service.py (NEW)
    │   ├── insights/                    — Personal Insights (NEW)
    │   ├── watchlist/                   — models/repository/service/schemas (NEW)
    │   ├── goals/ habits/ memory/ tasks/ — models/repository/service/schemas
    │   ├── proactive/                   — models/repository/service/questions/ai_extract
    │   ├── scheduler/                   — briefing, weekly_digest, nudges, charts,
    │   │                                  evening_checkin, evening_reflection
    │   ├── telegram/                    — bot, handlers, jobs, keyboards, callbacks, runner
    │   ├── web/static/index.html        — /ui (+ секция "Полка", weekly stats)
    │   ├── core/config.py               — Settings
    │   └── main.py
    ├── migrations/versions/001..011     — 010 watchlist_items, 011 embedding
    ├── scripts/drive_auth.py            — разовая OAuth-авторизация Drive (NEW)
    ├── tests/                           — 483 теста
    ├── docker-compose.yml, Dockerfile   — TZ=Europe/Moscow, tzdata, proxy-headers
    └── pyproject.toml                   — + matplotlib, google-api-python-client,
                                            google-auth-oauthlib
```

На сервере (`/opt/lifeos/`) — то же самое + `/etc/caddy/Caddyfile`
рядом (не в репозитории, конфиг сервера).
