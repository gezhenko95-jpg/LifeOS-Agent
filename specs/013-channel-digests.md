# Channel Digests Specification

---

# Цель

Пользователь заводит именованную тему («ESG»), вручную добавляет в неё
чужие ПУБЛИЧНЫЕ Telegram-каналы, а бот следит за новыми постами и
присылает саммари — по расписанию (`daily`/`weekly`) и/или по запросу
(`/digest ESG`). Это не каналы владельца (добавить бота админом
невозможно) — обычные внешние каналы, которые он и так читает глазами.

**Ключевое архитектурное решение — как читать чужие каналы.**
Рассматривались два способа:

1. **MTProto-юзербот** (Telethon/Pyrogram, вход под личным аккаунтом) —
   умеет и приватные каналы, но файл сессии равносилен «ещё одно
   устройство залогинено в аккаунт»: полный доступ, а не ограниченный
   токен, плюс риск ограничения самого аккаунта Telegram при нетипичном
   API-поведении.
2. **Веб-превью `https://t.me/s/<channel>`** — та же страница, что
   открывается в браузере без логина. Никакой авторизации, никакой
   сессии, никакого риска для аккаунта. Плата — только публичные каналы
   (ровно случай владельца) и неофициальный, хоть и стабильный годами,
   контракт разметки (тот же движок питает превью для эмбедов и
   поисковиков).

**Выбран вариант 2.** Разметка проверена вживую на
`https://t.me/s/telegram` (17.08.2026):
`div.tgme_widget_message[data-post="channel/12345"]` (число после `/` —
монотонно растущий id поста), текст —
`.tgme_widget_message_text.js-message_text`, дата — `time[datetime]`
внутри `.tgme_widget_message_date`.

---

# Что НЕ входит

- **Приватные/закрытые каналы** — потребовался бы юзербот, осознанно
  отклонён (см. выше).
- **`/digest_delete <name>`** — не в MVP: дайджест без каналов
  безвреден, удаление можно добавить позже по факту необходимости
  (ADR-004).
- **Inline-кнопки в `/digest_list`** (✅/🗑, как у привычек и полки) — не
  в MVP: чисто текстовый список, без нового callback-префикса и роутинга
  в `callbacks.py`.
- **Медиа из постов** — только текст. Картинки/видео не скачиваются и не
  пересылаются.
- **Пагинация вглубь истории** (`?before=<post_id>`) — дайджесту нужна
  только первая страница превью (самые новые посты).
- **Своя частота для каждого дайджеста как отдельная job** — частота
  живёт в данных, одна общая ежедневная job проходит по всем дайджестам
  (см. «Слои»).

---

# Пользовательские сценарии

- `/digest_new ESG daily` → «✅ Дайджест «ESG» создан (каждый день)» +
  подсказка, как добавить канал. Без второго аргумента — дайджест
  только по запросу.
- `/digest_add ESG @greenpeace` → бот СРАЗУ читает канал и либо
  подтверждает, либо говорит «Не нашёл канал» — ошибка всплывает в
  момент добавления, а не через сутки молчания. Watermark
  (`last_seen_post_id`) выставляется на самый свежий пост при
  добавлении, иначе первый же дайджест вывалил бы всю видимую историю.
- `/digest ESG` → саммари новых постов прямо сейчас. Новых постов нет →
  «Новых постов пока нет» (по запросу отвечаем всегда, в отличие от
  фоновой job — тот же принцип, что у кнопки «📊 Инсайты»).
- Ежедневно в `digest_hour:digest_minute` → дайджесты с
  `auto_frequency="daily"`, по воскресеньям — ещё и `"weekly"`. Нет
  новых постов — тихий пропуск, никаких «нечего показать»
  (как `send_monthly_insights_job`).
- Один из каналов удалён/стал приватным → он пропускается с
  `logger.warning`, остальные каналы дайджеста приходят как обычно, а
  watermark сломанного канала не двигается.
- Нет `openrouter_api_key` (или AI ответил ошибкой) → вместо саммари
  сырой список «• текст поста — ссылка», тихий фолбэк, как везде в
  проекте.

---

# Модель данных (`migrations/versions/014_create_digest_tables.py`)

```
digests
  id                PK
  telegram_user_id  BigInteger, indexed
  name              String(50)             -- "ESG", один токен без пробелов
  auto_frequency    String(10), nullable   -- "daily" | "weekly" | NULL (по запросу)
  created_at        DateTime(tz), server_default now()
  UniqueConstraint(telegram_user_id, name) -- uq_digest_name

digest_channels
  id                PK
  digest_id         FK -> digests.id, ON DELETE CASCADE, indexed
  channel_username  String(64)             -- без @, без t.me/
  last_seen_post_id Integer, nullable      -- watermark "что уже показано"
  added_at          DateTime(tz), server_default now()
  UniqueConstraint(digest_id, channel_username) -- uq_digest_channel
```

`last_seen_post_id` — на ПАРЕ (дайджест, канал), не глобально на канал:
один и тот же канал в двух дайджестах с разной частотой независимо
отслеживает, что уже показано в каждом.

Каскад задан сразу в миграции (в отличие от `habit_logs`, которым его
пришлось добавлять миграцией 007 постфактум после живого бага).

---

# Слои

## `app/digest/scraper.py`

`ChannelPost` (frozen dataclass: `post_id`, `text`, `url`,
`published_at`), `ChannelScrapeError`, `ChannelScraper.fetch_new_posts(
channel_username, after_post_id=None) -> list[ChannelPost]` — GET
`https://t.me/s/<channel>` с браузерным User-Agent, разбор через
`BeautifulSoup(html, "html.parser")` (без `lxml` — незачем тащить
компилируемый C-парсер ради пары страниц в день, ADR-004). Посты
отдаются от старых к новым; `after_post_id is None` — отдаём всё
(первое добавление канала). Не-200, сетевая ошибка, страница без
сообщений → `ChannelScrapeError`. Пост без текста (одни медиа)
пропускается молча — один такой пост не повод объявлять канал
непрочитанным.

Таймаут 15с, без ретраев (как `AIClient._post_json`).
`get_channel_scraper()` держит один `httpx.AsyncClient` на процесс —
тот же keep-alive-принцип, что у `AIClient` (AUDIT.md, P-4), но
отдельный клиент: другой хост, другой таймаут.

## `app/digest/repository.py`

`DigestRepository(BaseRepository[Digest])` — плюс методы для каналов
(`add_channel`, `list_channels`, `get_channel`, `remove_channel`,
`update_last_seen_post_id`). Отдельного репозитория под `DigestChannel`
нет — он всегда доступен только через родительский `Digest` (по образцу
`HabitRepository`, где так же живёт `HabitLog`).

## `app/digest/service.py::DigestService`

`create_digest` (валидация: непустое имя, один токен, ≤50 символов,
частота из `{None, "daily", "weekly"}`, без дубликата у пользователя),
`list_digests`, `list_channels`, `add_channel` (владение через
`owned_or_none`, нормализация `@`/`t.me/`/`https://`, пробный fetch до
сохранения, watermark сразу на свежий пост), `remove_channel`,
`build_digest_text(telegram_user_id, digest_name, ai_client=None)`.

`build_digest_text` возвращает `None`, если новых постов нет. Watermark
двигается СРАЗУ при сборе постов, даже если сообщение потом не уйдёт —
иначе те же посты придут повторно следующим дайджестом. AI-саммари — по
образцу `weekly_digest.py::_generate_insight`, но как основной контент,
а не «инсайт поверх»; вход обрезается до 6000 символов, чтобы случайно
активный канал не разгонял счёт токенов.

## `app/telegram/handlers.py`

Первые в проекте команды с аргументами (`context.args: list[str]`):

```
/digest_new <name> [daily|weekly]   — создать (частота опциональна)
/digest_add <name> <channel>        — добавить канал
/digest_remove <name> <channel>     — убрать канал
/digest_list                        — дайджесты + каналы + частоты
/digest <name>                      — саммари прямо сейчас
```

Каждая команда — тонкий враппер: разобрать `context.args`, на неверное
количество ответить подсказкой синтаксиса (не исключением), остальное —
в `DigestService`. Имена дайджестов — один токен, чтобы разбор `args`
оставался однозначным.

## `app/telegram/jobs.py::send_digests_job` + `bot.py::_register_digests`

Одна общая ежедневная job на ВСЕ дайджесты владельца, а не по job на
дайджест (динамическая регистрация при каждом `/digest_new` — лишняя
сложность ради того же результата, ADR-004). Внутри: `daily` — каждый
прогон, `weekly` — только если сегодня воскресенье
(`jobs.SUNDAY_WEEKDAY`, тот же источник числа, что у
`bot._SUNDAY` для еженедельного дайджеста), `NULL` — пропуск.

## `Settings` (`app/core/config.py`)

```python
digest_enabled: bool = True
digest_hour: int = 9
digest_minute: int = 30
```

Плюс зависимость `beautifulsoup4>=4.12.0` в `pyproject.toml`.

---

# Definition of Done

- `ChannelScraper`: разбор реальной разметки, фильтр по `after_post_id`,
  пост без текста, страница без сообщений, не-200, сетевая ошибка —
  `tests/digest/test_scraper.py`.
- `DigestRepository`: CRUD дайджестов и каналов, изоляция по
  пользователю, обновление watermark, каскадное удаление каналов вместе
  с дайджестом — `tests/digest/test_repository.py`.
- `DigestService`: валидация имени/частоты/дубликата, нормализация имени
  канала, watermark при добавлении, чужой/несуществующий дайджест,
  сборка текста с AI / без AI / при ошибке AI, продвижение watermark,
  устойчивость к сломанному каналу — `tests/digest/test_service.py`.
- Команды: разбор `context.args`, подсказка синтаксиса, ответы на все
  ветки — `tests/telegram/test_digest_commands.py`.
- Миграция 014 проверена на scratch-копии БД на сервере (полная цепочка
  `upgrade head` → `\d` → `downgrade` → `DROP DATABASE`) ДО выкатки на
  реальную `lifeos`.
- Живая проверка после деплоя: `/digest_new ESG`, `/digest_add ESG
  <публичный канал>`, `/digest ESG`.
