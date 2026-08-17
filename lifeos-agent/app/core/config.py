"""
Конфигурация приложения LifeOS Agent
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LifeOS Agent"
    app_version: str = "0.1.0"
    environment: str = "development"

    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lifeos"

    # Логировать каждый SQL с параметрами (см. app/db/session.py). Выключено
    # по умолчанию: параметры — это в том числе тексты дневниковых записей,
    # а логи контейнера не приватное место (см. AUDIT.md, C-5).
    sql_echo: bool = False

    # Токен доступа к REST API (заголовок X-API-Token, см. app/api/deps.py).
    # REST API отдаёт задачи/память/цели по telegram_user_id из query-
    # параметра — без токена этого достаточно, чтобы прочитать чужой
    # дневник, зная только Telegram ID (см. AUDIT.md, C-2).
    #
    # Пусто = API ЗАКРЫТ ПОЛНОСТЬЮ (401 на всё, кроме /health). Именно так,
    # а не "пусто = открыт": забытая настройка должна ломать доступ, а не
    # молча снимать защиту.
    api_token: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Владелец системы (проект single-user, см. PROJECT.md).
    # 0 = утренний брифинг не отправляется (Telegram ID не задан).
    owner_telegram_user_id: int = 0

    # Утренний брифинг (см. flows/001-morning-briefing.md, flows/009-daily-rhythm.md):
    # задачи/привычки/цели/AI-инсайт + график.
    morning_briefing_enabled: bool = True
    morning_briefing_hour: int = 8
    morning_briefing_minute: int = 0

    # Вечерняя рефлексия (см. flows/005-evening-reflection.md,
    # flows/009-daily-rhythm.md): один AI-сгенерированный вдумчивый
    # вопрос для дневника вместо статичного текста.
    evening_reflection_enabled: bool = True
    evening_reflection_hour: int = 21
    evening_reflection_minute: int = 0

    # Напоминания о задачах (специфичный due_date, а не ежедневное сообщение).
    task_reminders_enabled: bool = True
    task_reminders_interval_seconds: int = 60

    # Напоминания о привычках: у каждой своё время (habits.reminder_time,
    # миграция 015), поэтому джоба крутится с тем же шагом, что и
    # напоминания о задачах, и сама отбирает, кому пора. Привычки,
    # отмеченные сегодня, пропускаются.
    habit_reminders_enabled: bool = True
    habit_reminders_interval_seconds: int = 60

    # Три касания дня (см. flows/009-daily-rhythm.md — имена настроек не
    # переименовывали при переосмыслении содержания, чтобы не задеть уже
    # настроенный .env): утро (10:30) — вопрос про сон или gap-вопрос про
    # профиль; день (14:00) — "как дела" + табличка привычек; вечер
    # (19:00) — итоги дня + иногда gap-вопрос. Gap-вопросы реально
    # работают только если задан openrouter_api_key (без AI ответ
    # пользователя не разобрать) — см. app/telegram/jobs.py.
    proactive_prompts_enabled: bool = True
    proactive_prompt_morning_hour: int = 10
    proactive_prompt_morning_minute: int = 30
    proactive_prompt_midday_hour: int = 14
    proactive_prompt_midday_minute: int = 0
    proactive_prompt_evening_hour: int = 19
    proactive_prompt_evening_minute: int = 0

    # Еженедельный дайджест по воскресеньям (см. flows/007-weekly-digest.md).
    weekly_digest_enabled: bool = True
    weekly_digest_hour: int = 20
    weekly_digest_minute: int = 0

    # Дайджесты Telegram-каналов (см. specs/013-channel-digests.md). Одна
    # ежедневная job на ВСЕ дайджесты владельца: "daily" обрабатываются
    # каждый прогон, "weekly" — только по воскресеньям, без частоты —
    # только по команде /digest <name>.
    digest_enabled: bool = True
    digest_hour: int = 9
    digest_minute: int = 30

    # Нэджи по целям/привычкам, раз в день (см. app/scheduler/nudges.py).
    nudges_enabled: bool = True
    nudges_hour: int = 9
    nudges_minute: int = 0

    # Personal Insights раз в месяц, 1-е число (см.
    # specs/009-personal-insights.md) — поведенческие закономерности за
    # 60 дней. Тихий пропуск, если находок нет (в отличие от кнопки
    # "📊 Инсайты" в меню, которая отвечает по запросу в любой момент).
    monthly_insights_enabled: bool = True
    monthly_insights_hour: int = 12
    monthly_insights_minute: int = 0

    # AI Service (OpenRouter) — фолбэк для Conversation Engine,
    # см. specs/003-conversation.md. Пусто = фолбэк выключен.
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openrouter_transcription_model: str = "openai/whisper-large-v3"

    # Голосовой ввод (см. specs/012-voice-input.md).
    #
    # ВЫКЛЮЧЕН по умолчанию (17.08.2026). Причина не техническая: из всех
    # AI-фич голос — единственная, которая стоит заметных денег
    # (~$0.9–1.8 на активного пользователя в месяц против центов у всего
    # остального, расчёт в MULTIUSER.md), а решение по монетизации ещё не
    # принято. Код целиком сохранён и рабочий: при voice_input_enabled=true
    # в .env хендлер регистрируется обратно, менять ничего не нужно.
    # Пока выключено — бот на голосовые не отвечает вообще (хендлер не
    # зарегистрирован), и нигде о них не упоминает.
    #
    # Прежде чем включать обратно: сначала счётчик минут на пользователя
    # и лимит, иначе расход виден только в счёте OpenRouter.
    voice_input_enabled: bool = False
    # Голосовые длиннее лимита не расшифровываем — дороже и дольше.
    voice_max_duration_seconds: int = 300

    # Семантический поиск по памяти (см. specs/011-semantic-memory-
    # search.md) — фоновая доливка embedding для новых записей.
    memory_embeddings_enabled: bool = True
    memory_embedding_batch_size: int = 20
    memory_embedding_interval_seconds: int = 300

    # TMDb — обложки и описания для полки (см. app/watchlist/tmdb.py).
    # Пусто = обогащение выключено, записи сохраняются текстом, как
    # раньше. Ключ бесплатный, берётся в личном кабинете themoviedb.org.
    tmdb_api_key: str = ""

    # Google Drive (Фаза 2 Media Inbox, см. specs/010-media-inbox.md).
    # token.json — разовая локальная авторизация (scripts/drive_auth.py),
    # монтируется в контейнер только для чтения. Файла нет = фича
    # выключена (см. app/drive/client.py::get_drive_client).
    drive_token_file: str = "token.json"

    # Сколько дампов БД держать на Google Drive (см. app/backup/service.py,
    # scripts/backup_db.sh). Локально на сервере хранится неделя — Диск
    # нужен как раз на случай, когда сервера уже нет.
    backup_keep: int = 14

    # Публичный адрес /ui (см. app/telegram/handlers.py::_send_site_link,
    # кнопка "🌐 Сайт" в меню) — пусто, пока не задеплоено на постоянный
    # сервер с доменом.
    public_ui_url: str = ""

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """Получение настроек"""
    return Settings()
