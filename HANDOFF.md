# LifeOS Agent — Handoff (2026-08-17)

Вставьте этот файл целиком в начало нового чата с Claude, чтобы продолжить
работу без потери контекста. Прошлый HANDOFF (16.08, вечер) остаётся ниже
как история — этот раздел описывает, что изменилось с тех пор: закрыт
архитектурный блок AUDIT.md целиком (A-1…A-6), добавлен голосовой ввод, и
спроектирован (но НЕ реализован) дайджест Telegram-каналов — план
приведён ниже целиком, можно сразу отдавать в работу.

---

## Что сделать в начале новой сессии

**Реализовать «Дайджест Telegram-каналов»** — план ниже уже одобрен
(Explore+Plan пройдены в прошлой сессии, переделывать не нужно), осталось
только закодить по нему. Ключевые решения внутри плана: скрейпинг
`t.me/s/<channel>` вместо MTProto-юзербота (осознанно, из-за риска для
личного Telegram-аккаунта — см. план), частота и авто, и по запросу,
AI-саммари с тихим фолбэком на сырой список.

После реализации — как обычно: `python -m pytest -q` /
`ruff check` / `black --check` в `lifeos-agent/`, ветка → PR/мёрж в
`main` → `git push` → `bash lifeos-agent/scripts/deploy.sh` →
`--check` для сверки → живая проверка (`/digest_new ESG`, `/digest_add`,
`/digest ESG`). Миграция новая (`014_create_digest_tables.py`) — сначала
scratch-проверка на сервере (см. ниже, «Технические нюансы»), это первая
миграция с новым доменом с нуля со времён аудита.

---

## План «Дайджест Telegram-каналов» (спроектирован 17.08, не реализован)

### Контекст

Пользователь хочет присылаемый ботом дайджест по темам — пример из
разговора: создать «дайджест ESG», вручную добавить туда чужие
публичные Telegram-каналы по теме, бот следит за новыми постами и
присылает саммари. Это НЕ каналы, которыми пользователь управляет
(нельзя добавить бота админом) — обычные внешние публичные каналы.

**Ключевое архитектурное решение:** рассматривались два способа читать
чужие каналы —

1. **MTProto-юзербот** (Telethon/Pyrogram, вход под личным Telegram-
   аккаунтом пользователя) — умеет читать и приватные каналы, но несёт
   реальный риск: файл сессии равносилен «ещё одно устройство залогинено
   в аккаунт» (полный доступ, не ограниченный токен), плюс риск
   ограничения/бана самого личного аккаунта Telegram при нетипичном API-
   поведении. У пользователя есть отдельный запасной аккаунт под это, но
   всё равно риск.
2. **Скрейпинг публичного веб-превью `https://t.me/s/<channel>`** — та
   же страница, что видна в браузере без логина при пересылке ссылки на
   канал. Никакой авторизации, никакой сессии, никакого риска для
   аккаунта. Ограничение — только публичные каналы (ровно случай
   пользователя), и это не официальный API-контракт (хоть и стабильный
   годами — тот же движок питает превью для эмбедов/поисковиков).

**Выбрано: вариант 2 (скрейпинг).** Проверено вживую (curl на
`https://t.me/s/telegram`) — структура страницы:
- каждый пост — `<div class="tgme_widget_message ..." data-post="channelname/12345">`
  (число после `/` — числовой id поста, растёт монотонно);
- текст поста — `.tgme_widget_message_text.js-message_text` (может
  содержать вложенные теги — ссылки, `<br>`, эмодзи-`<i>`);
- дата — `<time datetime="2026-04-09T07:01:44+00:00" class="time">`
  внутри `.tgme_widget_message_date`;
- пагинация вглубь истории — `?before=<post_id>` (для дайджеста не
  нужна: смотрим только новые посты сверху первой страницы).

Остальные решения из разговора:
- **Частота**: и авто (per-дайджест daily/weekly), и по запросу —
  одновременно, не взаимоисключающе.
- **Формат**: AI-саммари (тот же `AIClient.complete()`, что и в
  `weekly_digest`/`briefing`), с тихим фолбэком на сырой список постов,
  если AI недоступен/ошибся — тот же принцип "тихий фолбэк", что везде
  в проекте.

Разведка (2 агента, прошлая сессия) подтвердила образцы для копирования:
- `app/watchlist/` — эталон структуры простого домена (`BaseRepository`,
  `owned_or_none`, сервис с опциональным `ai_client`).
- `app/scheduler/weekly_digest.py` — эталон "собрать текст + опциональный
  AI-инсайт поверх, тихий фолбэк при ошибке AI".
- `app/telegram/bot.py::_register_*` — эталон регистрации job.
- **В проекте НЕТ ни одной команды с аргументами** (`context.args`
  нигде не используется) — это будет новый паттерн, вводим впервые.
- **В `pyproject.toml` нет HTML-парсера** — новая зависимость,
  `beautifulsoup4` (со встроенным `html.parser`, без `lxml` — не нужен
  компилируемый C-парсер ради нескольких страниц в день).
- Следующий номер миграции — **014** (последняя — `013_create_checkins_table.py`).

### Модель данных (миграция `014_create_digest_tables.py`)

```
digests
  id            PK
  telegram_user_id  BigInteger, indexed
  name          String(50)              -- "ESG", без пробелов (см. ниже)
  auto_frequency String(10), nullable   -- "daily" | "weekly" | NULL (только по запросу)
  created_at    DateTime(timezone=True), server_default now()
  UniqueConstraint(telegram_user_id, name)

digest_channels
  id            PK
  digest_id     FK -> digests.id, ondelete=CASCADE, indexed  (как habit_logs, миграция 007)
  channel_username  String(64)          -- без @, без t.me/
  last_seen_post_id Integer, nullable   -- watermark для "что нового"
  added_at      DateTime(timezone=True), server_default now()
  UniqueConstraint(digest_id, channel_username)
```

`last_seen_post_id` — на паре (digest, channel), не глобально на канал:
один и тот же канал в двух дайджестах с разной частотой независимо
отслеживает "что уже показано" в каждом.

### Слои (по образцу `app/watchlist/`)

**`app/digest/models.py`** — `Digest`, `DigestChannel` — SQLAlchemy-модели
по схеме выше.

**`app/digest/scraper.py`**:
```python
@dataclass(frozen=True)
class ChannelPost:
    post_id: int
    text: str
    url: str
    published_at: datetime

class ChannelScrapeError(Exception):
    """Канал не найден/приватный/страница не распозналась."""

class ChannelScraper:
    def __init__(self, http: httpx.AsyncClient) -> None: ...

    async def fetch_new_posts(
        self, channel_username: str, after_post_id: int | None
    ) -> list[ChannelPost]:
        """GET https://t.me/s/{channel_username}, без ?before= (нужна
        только первая страница — самые новые посты). User-Agent браузера
        (проверено вживую — без него тоже может работать, но UA снижает
        риск блокировки). BeautifulSoup(html, "html.parser") —
        div.tgme_widget_message[data-post] → post_id из хвоста
        "channel/12345", .tgme_widget_message_text.get_text(" ", strip=True),
        time[datetime] → published_at. Отдаёт только post_id > after_post_id
        (или все, если after_post_id is None — первое добавление канала).
        Пустая HTML-страница/отсутствие сообщений/не-200 → ChannelScrapeError
        (используется в DigestService.add_channel для немедленной
        проверки, что канал существует, до сохранения)."""
```
Один `httpx.AsyncClient` передаётся снаружи (не создаём новый на каждый
вызов — тот же принцип keep-alive, что у `AIClient`, но отдельный
клиент, не переиспользуем `AIClient._http`, т.к. это разные хосты).
Таймаут ~15с, без ретраев (как у `AIClient._post_json`).

**`app/digest/repository.py`**:
```python
class DigestRepository(BaseRepository[Digest]):
    model = Digest

    async def list_by_user(self, telegram_user_id: int) -> list[Digest]: ...
    async def get_by_name(self, telegram_user_id: int, name: str) -> Digest | None: ...

    async def add_channel(self, digest_id: int, channel_username: str) -> DigestChannel: ...
    async def list_channels(self, digest_id: int) -> list[DigestChannel]: ...
    async def get_channel(self, digest_id: int, channel_username: str) -> DigestChannel | None: ...
    async def remove_channel(self, channel: DigestChannel) -> None: ...
    async def update_last_seen_post_id(self, channel: DigestChannel, post_id: int) -> None: ...
```
По образцу `HabitRepository` (сама содержит методы и для `Habit`, и для
`HabitLog` — не заводим отдельный `BaseRepository` под `DigestChannel`,
он всегда доступен только через родительский `Digest`).

**`app/digest/service.py::DigestService`**:
```python
class DigestService:
    def __init__(self, repository: DigestRepository, scraper: ChannelScraper) -> None: ...

    async def create_digest(self, telegram_user_id, name, auto_frequency=None) -> Digest:
        """ValueError на пустое/с пробелами имя, на auto_frequency не из
        {None, "daily", "weekly"}, на дубликат имени у пользователя."""

    async def list_digests(self, telegram_user_id) -> list[Digest]: ...

    async def add_channel(self, telegram_user_id, digest_name, channel_username) -> DigestChannel:
        """owned_or_none по имени дайджеста → ValueError, если дайджеста
        нет/чужой. Нормализация channel_username (срезать ведущий @,
        t.me/, https://). Перед сохранением — ОДИН fetch через scraper
        (без after_post_id — просто списком), чтобы сразу сказать
        пользователю "канал не найден", а не откладывать до следующего
        дайджеста. last_seen_post_id сразу выставляется в id самого
        свежего поста при добавлении — иначе первый дайджест после
        добавления канала вывалит ВСЮ историю канала разом."""

    async def remove_channel(self, telegram_user_id, digest_name, channel_username) -> bool: ...

    async def build_digest_text(
        self, telegram_user_id, digest_name, ai_client: AIClient | None = None
    ) -> str | None:
        """Для каждого канала в дайджесте — fetch_new_posts(after=last_seen),
        обновить last_seen_post_id на максимальный новый post_id (ДАЖЕ
        если решим не отправлять — иначе те же посты попадут в следующий
        дайджест повторно). Собрать все новые посты по всем каналам.
        Пусто — вернуть None (вызывающий код не отправляет пустое
        сообщение, как send_monthly_insights_job). С постами — либо
        AI-саммари (см. ниже), либо (без AI/ошибка AI) сырой список
        "• {текст короткий} — {url}" по образцу build_weekly_digest."""
```

AI-саммари — по образцу `weekly_digest.py::_generate_insight`, но
основной контент, не "инсайт поверх": системный промпт просит короткое
саммари новых постов (не более ~150 слов, по-русски, буллетами по
темам), user-message — конкатенация текстов постов (обрезать общий
объём, например до 6000 символов, чтобы не разогнать счёт токенов на
случайно активный канал). `AIServiceError` → `logger.warning` +
фолбэк на сырой список (не пропуск дайджеста целиком).

**`app/telegram/handlers.py`** — новые команды (первый прецедент
`context.args` в проекте):
```
/digest_new <name> [daily|weekly]   — создать, частота опциональна (по умолчанию — только по запросу)
/digest_add <name> <channel>        — добавить канал (без @/t.me/, сервис нормализует)
/digest_remove <name> <channel>     — убрать канал
/digest_list                        — список дайджестов + каналов + частоты
/digest <name>                      — прислать саммари прямо сейчас, вне расписания
```
`context.args: list[str]` — `python-telegram-bot` кладёт слова после
команды сюда. Каждая команда — тонкий враппер, парсит `context.args`,
на неверное количество/имя — короткая подсказка синтаксиса (не
исключение). Имена дайджестов — один токен без пробелов (валидируется
в `DigestService.create_digest`), чтобы `context.args`-парсинг
оставался однозначным.

`/digest_delete <name>` (удалить дайджест целиком) — **не в MVP**,
осознанно: пустой дайджест без каналов безвреден, можно добавить позже
по факту необходимости (ADR-004).

Inline-кнопки (✅/🗑 как у привычек/watchlist) для `/digest_list` — **не
в MVP**: чисто текстовый список, без нового callback-префикса и
роутинга в `callbacks.py`.

Регистрация в `app/telegram/bot.py`:
```python
application.add_handler(CommandHandler("digest_new", digest_new_command, filters=owner))
application.add_handler(CommandHandler("digest_add", digest_add_command, filters=owner))
application.add_handler(CommandHandler("digest_remove", digest_remove_command, filters=owner))
application.add_handler(CommandHandler("digest_list", digest_list_command, filters=owner))
application.add_handler(CommandHandler("digest", digest_now_command, filters=owner))
```

**`app/conversation/engine.py::_HELP_TEXT`** — добавить строку про новые
команды, тем же стилем, что уже есть для `/tasks, /habits, /goals` в
конце текста.

**`app/telegram/jobs.py::send_digests_job` + `app/telegram/bot.py::_register_digests`**

По образцу `send_weekly_digest_job`. Один общий job, не по одному на
дайджест (динамическая APScheduler-регистрация per-дайджест — лишняя
сложность, ADR-004): раз в день в фиксированное время
(`digest_hour`/`digest_minute` в `Settings`, тот же паттерн, что у
`weekly_digest_hour`/`weekly_digest_minute`) проходит по ВСЕМ дайджестам
владельца:
- `auto_frequency == "daily"` → всегда обрабатывать;
- `auto_frequency == "weekly"` → только если сегодня воскресенье (тот
  же `_SUNDAY = (6,)`, что уже есть в `bot.py` для `weekly_digest` —
  переиспользовать константу, не дублировать);
- `auto_frequency is None` → пропустить (только по запросу).

Тихий пропуск дайджеста без новых постов (`build_digest_text` вернул
`None`) — не шлём "нечего показать", как `send_monthly_insights_job`.

**`Settings`** (`app/core/config.py`):
```python
digest_enabled: bool = True
digest_hour: int = 9
digest_minute: int = 30
```
Плюс новая зависимость в `pyproject.toml`: `"beautifulsoup4>=4.12.0"`.

### Тесты

- `tests/digest/test_scraper.py` — `ChannelScraper.fetch_new_posts` на
  фиксированном HTML-фрагменте (сохранить как строку-константу в тесте
  по образцу реальной разметки `tgme_widget_message`/`data-post`/
  `tgme_widget_message_text`/`time[datetime]` из этого плана), мок
  `httpx.AsyncClient.get` (тот же паттерн `patch("httpx.AsyncClient.get", ...)`,
  что в `tests/ai/test_client.py` для `.post`). Кейсы: несколько постов,
  фильтр по `after_post_id`, пустая страница/не-200 → `ChannelScrapeError`.
- `tests/digest/test_repository.py` — по образцу `tests/watchlist/test_repository.py`
  (in-memory SQLite), включая cascade-удаление `digest_channels` при
  удалении `digests` (по образцу `tests/habits/test_delete_cascade.py`).
- `tests/digest/test_service.py` — по образцу `tests/watchlist/test_service.py`:
  `AsyncMock` на `repository` и `scraper`, отдельно кейсы AI/без AI/AI-ошибка
  для `build_digest_text` (по образцу тестов `pick_recommendation` в
  `tests/watchlist/test_service.py`), валидация имени/частоты в
  `create_digest`, `add_channel` обновляет `last_seen_post_id` сразу при
  добавлении (не начинает с `None`).
- `tests/telegram/test_digest_commands.py` — по образцу
  `tests/telegram/test_voice.py` (`MagicMock`/`AsyncMock` на
  `update`/`context`, без реального Telegram): разбор `context.args` на
  каждую команду, короткая подсказка при неверном синтаксисе.

### Спека — `specs/013-channel-digests.md`

По образцу `specs/010-media-inbox.md`/`specs/012-voice-input.md` (Цель /
Что НЕ входит / Пользовательские сценарии / Модель данных / Слои /
Definition of Done). В "Что НЕ входит": приватные/закрытые каналы (нужен
был бы юзербот — осознанно отклонён, см. выше), `/digest_delete`,
inline-кнопки в `/digest_list` (оба — не в MVP), скачивание медиа из
постов (только текст).

---

## Что сделано в этой сессии (17.08)

### 1. Закрыт архитектурный блок AUDIT.md целиком (A-1…A-6)

Ветка `arch/a2-a5-a6-audit`, смёржена и задеплоена. Разведка (2 агента)
показала, что A-2 — НЕ живой баг: проверено каждое место, где несколько
сервисов делят одну сессию — мутация объекта и `save()`/`add()` для него
всегда идут подряд, без `await` между ними, ни разу не найден паттерн
«чужой `save()` случайно закоммитил незавершённую мутацию». Полноценный
unit-of-work рефакторинг признан несоразмерным риску — вместо этого
явный инвариант-докстринг в `app/core/repository.py::BaseRepository`.

A-5 (двойной `parse_intent` на одно сообщение) — `ConversationEngine.handle_message`
теперь принимает опциональный `parsed: ParsedIntent | None`,
`handlers.py::handle_text_message` передаёт уже посчитанный intent,
второй разбор внутри движка не делается.

A-6 (три параллельных механизма разбора без единого описания) — весь
порядок описан одним докстрингом на `handle_text_message`
(`_MENU_ACTIONS` → `parse_intent`-перехват LIST_*-клавиатур →
`ConversationEngine`), включая честно названный узкий edge-case
(LIST-триггер может перехватить сообщение раньше проверки дневникового
pending внутри движка — не переупорядочено ради этого, задокументировано).

652 теста (было 643 после предыдущей сессии).

### 2. Голосовой ввод (Telegram voice → OpenRouter STT)

Ветка `feature/voice-input`, смёржена и задеплоена. Голосовое сообщение
распознаётся в текст и обрабатывается тем же путём, что и обычное
текстовое — отдельного "голосового" intent'а нет.

- `app/ai/client.py::AIClient.transcribe()` — OpenRouter
  `/api/v1/audio/transcriptions` (запущен 22.07.2026), тот же ключ, что
  у `complete()`/`embed()` — отдельный OpenAI-аккаунт не нужен. Base64
  JSON через уже существующий `_post_json`. Отдельный таймаут 60с
  (`_post_json` теперь принимает опциональный `timeout`, передаётся в
  httpx ТОЛЬКО если явно задан — httpx трактует явный `timeout=None` как
  "без таймаута вообще", а не "как у клиента").
- `Settings`: `openrouter_transcription_model` (`openai/whisper-large-v3`
  по умолчанию — лучше `whisper-1` на русском), `voice_max_duration_seconds`
  (300, длиннее — не расшифровываем).
- `handlers.py::handle_voice_message` — по образцу `handle_photo_message`:
  скачивание файла, двухуровневая обработка отказа (фича не настроена /
  голос не распознан), эхо распознанного текста ПЕРЕД ответом движка.
- Вынесен общий `_route_parsed_text` — было продублировано между текстом
  и голосом.
- `bot.py` — `MessageHandler(filters.VOICE & owner, ...)`.
- **Конвертация формата не нужна**: Telegram отдаёт голосовые в OGG, а
  `ogg` — в списке официально поддерживаемых форматов и у OpenRouter, и
  у OpenAI whisper.
- **Локальный Whisper отклонён** — прод-сервер (Hostkey) 2 vCPU/1.8 ГБ
  RAM, уже занято ~230 МБ под bot+api+db, ~1.2 ГБ доступно. Модель
  `small` (нужна для приемлемого русского) требует ~1-2 ГБ только под
  себя — риск деградации остального бота.
- `specs/012-voice-input.md`.

668 тестов (было 652). Задеплоено, бот стартовал чисто (логи проверены),
но живая проверка реальным голосовым сообщением от владельца пока не
подтверждена в чате — стоит уточнить, сработало ли.

---

## Что сделать в начале новой сессии

1. Прочитать `AUDIT.md` в корне репозитория — там весь технический долг
   по приоритету, статус отмечен прямо в файле (что закрыто, что нет).
2. **Архитектурный блок аудита не начат** — это, скорее всего, и есть
   тема новой сессии (A-1…A-4: слой авторизации, фабрика сервисов,
   `EngineResult` вместо парсинга ответа регуляркой, дедупликация
   репозиториев). Там же — производительность P-3 (pgvector) и мелочи
   B-6/B-7/B-8 (границы слов в парсере).
3. Проверить `bash lifeos-agent/scripts/deploy.sh --check` — сверяет
   прод/гит/локаль одной командой, не заходя на сервер.

---

## Философия проекта — без изменений

Персональный AI Chief of Staff в Telegram, single-user. ADR-004 (простой
код лучше LLM), ADR-001 (модульный монолит), ADR-002 (LLM не трогает БД
напрямую), ADR-003 (spec-first), ADR-005 (одна ответственность на
сервис) — всё как в `DECISIONS.md`, не пересматривалось.

**Добавилась одна практика, закрепившаяся за эту сессию**: каждая
миграция БД перед выкаткой на прод проверяется на одноразовой
scratch-копии на сервере (`CREATE DATABASE migration_test`, полная
цепочка `alembic upgrade head`, проверка структуры через `\d`, потом
`downgrade`, потом `DROP DATABASE`) — **до**, а не вместо проверки на
реальной `lifeos`. Три миграции в этой сессии (012 индексы, 013
checkins) прошли этот цикл. Стоит продолжать так же для любой будущей
миграции.

---

## Доступы — то же самое, но с одним важным изменением

Все доступы из прошлого HANDOFF (сервер `lifeos-eu`, домен
`lifeos-agent.ru`, DNS-панель SmartApe, Google Drive) остаются
актуальными без изменений — см. раздел "Доступы, пароли, ссылки" ниже.

**Изменилось:**
- Пароль Postgres на проде **сменён** (был `postgres`, стал
  случайным, лежит в `/opt/lifeos/.env` как `POSTGRES_PASSWORD`).
- Появился `api_token` в `/opt/lifeos/.env` — без него весь REST API
  отвечает 401/503 (кроме `/health`). Тот же токен нужно вписать в
  поле "Токен API" на `/ui` (спойлер "Настройки доступа" вверху
  страницы) — иначе сайт не покажет данные.
- **БД теперь бэкапится ежедневно** на Google Drive
  (`LifeOS/Бэкапы`), автоматически, без участия человека — см. раздел
  ниже.

---

## Что сделано в этой сессии (по порядку)

### 1. Полный аудит + все критические дыры закрыты

Файл `AUDIT.md` в корне репозитория — читайте его, не пересказ здесь.
Кратко, что было и что стало:

- **Postgres и API были доступны из интернета** (Docker пишет правила
  в обход `ufw`) — порты привязаны к `127.0.0.1`, пароль БД сменён.
- **REST API не имел аутентификации** — дневник владельца читался
  публично одним curl-запросом по известному Telegram ID. Добавлен
  `X-API-Token` (`app/api/deps.py`), пустой токен **закрывает** API, а
  не открывает — забытая настройка не должна снимать защиту.
- **Токен бота и SQL с личными данными утекали в логи контейнера** —
  `sql_echo` теперь выключен по умолчанию, `httpx`-логи бота приглушены.
  Токен бота был **перевыпущен** в @BotFather (старый успел засветиться).
- **Бот отвечал кому угодно** — добавлен `filters.User(owner)` на все
  хендлеры + проверка владельца в callback-обработчике (там же был
  IDOR: id брался прямо из `callback_data` без проверки, чей это id).
- Плюс: устойчивость к кривому `callback_data` (`add_error_handler`,
  `parse_callback` больше не роняет хендлер), CORS сужен, `/docs`
  выключен на проде.

### 2. Ежедневные бэкапы БД

`scripts/backup_db.sh` (крон на хосте, 03:00 Amsterdam) →
`pg_dump` → gzip → `app/backup/service.py` (в контейнере бота, у него
есть токен Drive) → `LifeOS/Бэкапы` на Google Drive. Ротация: 7 дней
локально на сервере, 14 копий на Диске. Идемпотентно — повторный
прогон в тот же день не плодит дубли на Диске.

**Проверено восстановлением**, не просто «файл появился»: дамп
разворачивался в отдельную scratch-БД, число строк сверено по всем
таблицам.

### 3. Деплой теперь идёт из гита, а не из рабочей папки

Раньше `tar` паковал файлы прямо с ноутбука — гит в цепочке не
участвовал, три копии кода (ноутбук/GitHub/сервер) могли разъехаться
незаметно. Теперь:

```bash
lifeos-agent/scripts/deploy.sh          # деплой: archive HEAD -> rsync -> миграции -> рестарт
lifeos-agent/scripts/deploy.sh --check  # сверить прод/гит/локаль без деплоя
```

Три проверки перед выкаткой (любая роняет деплой): рабочая папка
чистая, `HEAD` запушен в `origin/main`, тесты зелёные. Прод пишет свой
коммит в `DEPLOYED_COMMIT`, который отдаётся в `/health` —
`curl https://lifeos-agent.ru/health` показывает `commit` без захода на
сервер.

**Используйте только этот скрипт для деплоя.** Старый способ (`tar` +
ручной `docker compose up -d --build` через ssh) больше не должен
применяться — он и есть тот источник рассинхрона, который чинили.

### 4. Живые баги, найденные лично вами на реальном использовании

Это не абстрактный код-ревью — каждый пункт всплыл из скриншотов бота
в реальном диалоге:

- **`/help` и напоминания проваливались в дневник**, если рядом был
  открыт вопрос "что снилось?" — перехват дневника случался раньше
  разбора команд. Починено дважды (сначала только `/`, потом до конца
  — любое слово-команда в начале сообщения).
- **Окно "свежести" pending-вопроса было 30 минут** — ответ на
  утренний вопрос, пришедший через 2ч26м, улетал в обычный разбор и
  создавал бессмысленную задачу. Слоты дня разнесены на 3.5-5 часов и
  каждый следующий перезаписывает вопрос сам — окно увеличено до 6
  часов, реальная его роль — не путать случайную команду через
  несколько ДНЕЙ с ответом на забытый вопрос.
- **Время съезжало на 3 часа** — `asyncpg` отдаёт `due_date` в UTC, а
  показывался он как есть. Задача создавалась верно, врал только
  текст — это хуже тихой ошибки, потому что подрывает доверие к боту.
  Добавлен перевод в местное время перед любым показом
  (`app/tasks/formatting.py::to_local`).
- **«напомни» всегда означало поиск по памяти** — самый тяжёлый баг:
  `напомни в 19:00 позвонить маме` не создавало вообще ничего, бот
  молча искал в памяти. Теперь при наличии времени/даты это задача.
- Не разбирались форматы времени: `в 19 00`, `в 9 утра`, `через пару
  часов`, `через полчаса`. День и время не совмещались (`завтра в
  19:00` давало сегодня в 19:00). Всё это починено, дата-парсер
  переписан на раздельный разбор дня и времени.
- Слово-обращение оставалось в названии: `напомни МНЕ...` → задача
  «мне запустить стиралку». Обращения (мне/пожалуйста/плиз) теперь
  снимаются вместе с командой.
- **Кнопка «🌐 Сайт» не появлялась** — ReplyKeyboardMarkup живёт на
  клиенте, пока его не заменят, а меню отправлялось только на
  `/start`. Добавлена `/menu`, и меню переотправляется с каждым
  ответом бота без inline-кнопок — новые кнопки появляются сами.

### 5. Производительность (AUDIT.md P-1, P-2, P-4, P-6 — закрыты)

- N+1 по стрикам привычек (каждый показ списка = запрос на каждую
  привычку) — заменено на один запрос `IN(...)` + пакетные методы
  (`app/habits/streaks.py`, `HabitService.*_bulk`).
- Поиск по памяти/задачам/привычкам грузил всё в Python — заменено на
  `ILIKE` в БД с ручным экранированием `%`/`_`.
- Новое TCP+TLS соединение на каждый вызов OpenRouter — один
  `httpx.AsyncClient` на процесс, `get_ai_client()` кэширует один
  `AIClient`.
- Недостающие индексы: `tasks(telegram_user_id, status)`, частичные
  индексы под джобы напоминаний и доливки embedding.

Попутная находка: SQLite в тестах не умеет регистронезависимо сравнивать
кириллицу (встроенный `lower()` там ASCII-only), а весь проект на
русском. Проверено вживую на боевом Postgres, что там всё работает
(`SELECT 'Молоко' ILIKE '%молоко%'` → true) — баг был только в тестовой
среде. `tests/support.py::sqlite_engine()` регистрирует Unicode-aware
`lower()` на тестовый движок.

**Не начато**: P-3 (семантический поиск не масштабируется без
pgvector — не срочно, актуально после ~1000 записей памяти), B-6/B-7/B-8
(границы слов в парсере, мелочи разбора дат).

### 6. Редизайн бота

- **Списки** (задачи/привычки/цели/полка) — содержимое переехало из
  подписей кнопок (обрезались по 45 символов) в текст сообщения.
  Полное название, срок словами, цветной кружок срочности
  (🔴 просрочено/🟠 сегодня/🟡 завтра/⚪ позже), кнопки — короткие и
  нумерованные.
- **Брифинг и итоги дня** — дата словами в шапке, блок «Главное на
  сегодня», разделы «Дальше»/«Просрочено (N)», полоски прогресса,
  живая финальная фраза вместо сухих цифр.
- **Ответы на команды** — короче и с интонацией («✅ «X» — сделано!»
  вместо «Готово: «X» отмечена выполненной.»).

Первая строка ответа о созданной задаче **намеренно** осталась в
прежнем виде — по ней `handlers.py` регуляркой узнаёт «задача создана»
и цепляет быстрые кнопки. Хрупкая связка, помечена в коде и в
`AUDIT.md` (A-4) как кандидат на структурированный результат вместо
строки — не трогать формулировку первой строки без этого рефакторинга.

### 7. Редизайн `/ui`

- Настройки под спойлер, карточки с тенями, точки срочности, те же
  человеческие даты, что у бота.
- Фон: два размытых пятна медленно дрейфуют (декоративно, отключается
  через `prefers-reduced-motion`).
- Появление карточек/строк при загрузке, вспышка при «выполнить»,
  «заливка» прогресс-баров, счётчик цифр для статистики.
- **Мини-игра «🪙 Ежедневный визит»** — новый бэкенд-домен
  `app/rewards/` (модели/репозиторий/сервис по стандартному шаблону
  проекта). Ежедневный чек-ин даёт монеты (растущий бонус за серию,
  капается на 15-м дне), ~15% дней «счастливые» (x2, детерминировано
  хешем `(user, день)`, не настоящий `random()` — иначе сумма монет
  «плавала» бы при каждой перезагрузке). Восемь достижений считаются
  на фронте из уже загруженных данных (без отдельного бэкенд-сервиса).
  Пять тем оформления открываются порогами монет, красят всю страницу
  через CSS-переменные, хранятся в `localStorage` (косметика, не
  данные). Звания (🌱→🚀→⭐→👑→🏆), конфетти на юбилеях серии.

Ключевая деталь для будущих правок `app/rewards/`: `service.py`
обращается к `coins.is_lucky_day`/`coins.total_coins` **через модуль**
(`from app.rewards import coins`), а не через `from ... import
is_lucky_day` — при прямом импорте имени тесты патчили бы две
независимые ссылки на одну функцию и получали рассинхрон между тем,
что видит `_status()`, и тем, что использует `total_coins()` внутри
себя. Если добавляете новый вызов чего-то из `coins.py` в `service.py`
— вызывайте через `coins.имя_функции(...)`, не через прямой импорт.

---

## Технические нюансы, которые стоит помнить

1. **Деплой — только `scripts/deploy.sh`**, не руками через `tar`/`ssh`
   (см. раздел 3 выше).
2. **Перед любой миграцией — scratch-проверка на сервере** (см. раздел
   "Что сделать в начале новой сессии").
3. **`app/rewards/service.py` вызывает `coins.py` через модуль**, не
   прямым импортом имени (см. раздел 7 выше) — важно при тестировании.
4. Heredoc-подстановка `\n` через Bash-инструмент на Windows иногда
   превращает escape-последовательность в настоящий перевод строки и
   рвёт Python-строковые литералы (`f"...\n..."` ломается на два
   физических файла). Если редактирование через `Edit`/`Write`
   недоступно и нужен heredoc — писать многострочный Python-скрипт во
   временный файл и запускать его, а не инлайнить в `python -c` через
   heredoc с `\n` внутри f-строк.
5. Старые грабли из прошлого HANDOFF (Bash+кириллица, SSH-ключи,
   Postgres volume-пароль, `JSON(none_as_null=True)`, uvicorn за
   прокси, алембик-ревизии ≤32 символов) остаются актуальными, см. ниже.

---

## Структура репозитория (обновлено)

```
LifeOS-Agent/
├── AUDIT.md                            — технический аудит + статус (читать в начале сессии)
├── HANDOFF.md                          — этот файл
├── AGENTS.md, ARCHITECTURE.md, DECISIONS.md, MVP.md, PROJECT.md, ROADMAP.md, SYSTEM.md
├── specs/ (000-011), flows/ (001-011)
└── lifeos-agent/
    ├── app/
    │   ├── ai/client.py                — OpenRouter, один httpx.AsyncClient на процесс
    │   ├── api/                        — REST: + rewards.py, deps.py (X-API-Token)
    │   ├── backup/                     — сервис бэкапов (NEW)
    │   ├── conversation/                — engine.py, parser.py, date_parser.py (переписан)
    │   ├── drive/client.py              — + list_files/delete_file для ротации бэкапов
    │   ├── habits/                      — + streaks.py (чистые функции, переиспользуются rewards)
    │   ├── media_inbox/, insights/, watchlist/, goals/, memory/, tasks/, proactive/
    │   ├── rewards/                     — мини-игра: models/repository/service/schemas/coins.py (NEW)
    │   ├── scheduler/                   — briefing.py/evening_checkin.py переоформлены (HTML)
    │   ├── telegram/                    — keyboards.py переписан (карточки), bot.py (+owner filter)
    │   ├── web/static/index.html        — редизайн + мини-игра
    │   ├── core/config.py               — + api_token, sql_echo, backup_keep
    │   └── main.py                      — + require_api_token, rewards router
    ├── migrations/versions/001..013     — 012 индексы, 013 checkins
    ├── scripts/
    │   ├── deploy.sh                    — деплой из гита (NEW, использовать всегда)
    │   ├── backup_db.sh                 — крон-скрипт бэкапов (NEW)
    │   ├── backup_upload.py             — заливка на Drive (NEW)
    │   └── drive_auth.py
    ├── tests/ (630)                     — + support.py (Unicode-aware SQLite), rewards/, api/test_auth.py
    ├── docker-compose.yml               — порты на 127.0.0.1, DEPLOYED_COMMIT volume
    └── pyproject.toml
```

На сервере (`/opt/lifeos/`) — то же самое + `/etc/caddy/Caddyfile`,
`/etc/cron.d/lifeos-backup`, `DEPLOYED_COMMIT`.

```bash
cd lifeos-agent
python -m pytest -q            # 630 тестов
python -m ruff check app tests migrations scripts
python -m black --check app tests migrations scripts
```

---

## Что осталось (не изменилось по содержанию, актуализирован приоритет)

**Из `AUDIT.md`, архитектурный блок — скорее всего тема следующей сессии:**
- A-1: слой авторизации — `telegram_user_id` не проверяется как
  владелец сущности в сервисных методах, работающих по `id`.
- A-3: фабрика сервисов вместо ручной сборки в семи местах.
- A-4: `EngineResult` вместо парсинга ответа регуляркой
  (`handlers.py::extract_created_task_title`).
- Дедупликация репозиториев (`BaseRepository[T]`), удаление мёртвого
  кода (`pick_and_open`, `/memory/context`).

**Из старого списка идей** (не тронуто в этой сессии):
1. Голосовой ввод (Telegram voice → STT → в `ConversationEngine`).
2. Дайджест из Telegram-каналов (требует юзербота, MTProto —
   отдельная архитектура).
3. Рецепты по фото продуктов (ложится на пайплайн Media Inbox).
4. Персональные «режимы фокуса».
5. Weekly Review как отдельный диалог, Календарь.
6. Проверить, отменён ли пробный VPS SmartApe (Москва).

---

# Прошлый HANDOFF (14.08) — сохранён как история

Всё ниже — контекст предыдущей сессии (аудит инфраструктуры не
проводился, сервер только что переехал на Hostkey). Доступы и грабли
из этого раздела остаются актуальными, если не указано иное выше.

## Философия проекта (что это и зачем)

**LifeOS Agent** — персональный AI Chief of Staff в Telegram, single-user
(только для владельца, не multi-tenant). Не чат-бот и не менеджер задач —
цель — снять с человека когнитивную нагрузку: бот сам держит контекст
(задачи/привычки/цели/память/дневник), проактивно напоминает и спрашивает,
а не только отвечает на команды. Подробно — `PROJECT.md`.

Ключевые принципы (закреплены как ADR в `DECISIONS.md`):
- **ADR-004: простой код лучше LLM.**
- **ADR-001: модульный монолит.** Не микросервисы.
- **ADR-002: LLM никогда не трогает БД напрямую** — только через
  сервисный слой.
- **ADR-005: один сервис — одна ответственность.**
- **Spec-first (ADR-003)**: `specs/NNN-name.md` + `flows/NNN-name.md` до
  кода.

## Доступы, пароли, ссылки

### Репозиторий
[gezhenko95-jpg/LifeOS-Agent](https://github.com/gezhenko95-jpg/LifeOS-Agent),
ветка `main`. Локально:
`C:\Users\Honor-16-z1\Desktop\Автоматизация жизни\LifeOS-Agent`, код в
`lifeos-agent/`.

### Продакшн-сервер (Hostkey, Нидерланды)
- IP: `148.135.208.126`, домен: `lifeos-agent.ru`
- SSH: `ssh lifeos-eu` (алиас в `~/.ssh/config`, ключ
  `~/.ssh/lifeos_main`). Вход только по ключу.
- Проект на сервере: `/opt/lifeos/`.
- Caddy — реверс-прокси + HTTPS, `/etc/caddy/Caddyfile`, проксирует
  `lifeos-agent.ru` → `localhost:8000`.

### Домен и DNS (SmartApe)
- Аккаунт: `gezhenko95@gmail.com`, панель `cp.smartape.ru`.
- Домен `lifeos-agent.ru`, до 2027-08-14.
- DNS-записи — отдельная панель: **https://dns-01.smartape.ru:1501**,
  логин `user1764200`, пароль `zxp19NsecLMN`.

### Старый VPS (SmartApe, Москва) — заброшен
IP `188.127.224.144`, алиас `lifeos-vps` — не использовать, с
российских VPS заблокирован `api.telegram.org`.

### Google Drive (Media Inbox)
`credentials.json` + `token.json` в `/opt/lifeos/`, не в git. Проект
`LifeOS Agent` (`lifeos-agent-505510`), scope `drive.file`.
Переавторизация — `scripts/drive_auth.py` (локально, не в контейнере).

### Полезные ссылки
- OpenRouter: https://openrouter.ai
- Hostkey: https://hostkey.ru
- SmartApe: https://www.smartape.ru
- Google Cloud Console: https://console.cloud.google.com

## Технические грабли (актуальны)

1. Windows + Bash-инструмент: `cd` в кириллический путь иногда
   спонтанно фейлится — повторить без `cd`.
2. SSH-ключ в веб-форме хостера — вставлять вручную одной строкой.
3. Postgres в Docker: `POSTGRES_PASSWORD` из `docker-compose.yml`
   применяется только при первой инициализации пустого volume.
4. `echo "x" >> .env` без финального переноса строки — значение
   приклеится к предыдущей строке.
5. JSON-колонки в SQLAlchemy: `JSON(none_as_null=True)`, если значение
   может быть `None` и по нему потом фильтруют `IS NULL`.
6. uvicorn за реверс-прокси: всегда `--proxy-headers
   --forwarded-allow-ips=*`.
7. Алембик: id ревизии ≤32 символов.

## Архитектура (не менялась)

Слои: `API/Telegram → Service → Repository → DB`. `ConversationEngine`
Telegram-агностичен. Каждый домен — свои
`models.py`/`repository.py`/`service.py`/`schemas.py`; REST-роутеры
отдельно, в `app/api/`.
