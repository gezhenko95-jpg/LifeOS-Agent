"""
Фоновые задачи Telegram-бота (Scheduler), см. flows/001-morning-briefing.md.
"""

import logging
import random
from datetime import date
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.ai.client import AIClient, get_ai_client
from app.core.config import get_settings
from app.core.container import (
    build_assistant_service,
    build_contact_service,
    build_digest_service,
    build_finance_service,
    build_focus_service,
    build_mood_service,
    build_prompt_service,
    build_task_service,
)
from app.db.session import AsyncSessionLocal
from app.digest.service import DAILY, WEEKLY
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.insights.formatting import build_insights_text
from app.insights.service import InsightsService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.mood.service import MoodService
from app.proactive.repository import PendingPromptRepository
from app.scheduler.briefing import build_morning_briefing
from app.scheduler.charts import gather_chart_data, render_chart
from app.scheduler.evening_checkin import build_evening_checkin_text
from app.scheduler.evening_reflection import build_evening_reflection_prompt
from app.scheduler.finance_report import build_finance_report
from app.scheduler.nudges import build_nudges
from app.scheduler.persona_nudges import find_nudge_candidate, generate_nudge_text
from app.scheduler.weekly_digest import build_weekly_digest
from app.tasks.service import TaskService
from app.telegram.keyboards import build_habits_message, build_mood_prompt_keyboard

logger = logging.getLogger(__name__)

# Лимит Telegram на подпись к фото — если текст дайджеста вдруг длиннее,
# шлём фото без подписи и текст отдельным сообщением, а не падаем на API.
_PHOTO_CAPTION_LIMIT = 1024

_MIDDAY_TEXT = "Как проходит твой день? 🌤 Отметь, что уже успел:"
_MIDDAY_TEXT_NO_HABITS = "Как проходит твой день? 🌤"

# Вечерний итоговый слот 19:00: доля сообщений, к которым снизу
# добавляется gap-вопрос про профиль (только если гэп реально есть).
_EVENING_GAP_CHANCE = 0.5

# 0=понедельник..6=воскресенье, как date.weekday() и как days= у PTB
# run_daily. Живёт здесь, а не в bot.py: им пользуются и еженедельный
# дайджест (через bot._SUNDAY), и send_digests_job (частота "weekly"),
# а bot.py и так импортирует jobs.py — обратный импорт был бы циклом.
SUNDAY_WEEKDAY = 6


async def _maybe_append_persona_nudge(
    session: AsyncSession,
    ai_client: AIClient | None,
    telegram_user_id: int,
    habit_service: HabitService,
    task_service: TaskService,
    text: str,
) -> str:
    """Незапланированное сообщение персонажа (specs/027-butler-personas-
    phase2.md, п.2) — довесок к дневному/вечернему чек-ину, не отдельная
    джоба (см. app/scheduler/persona_nudges.py). Тихо возвращает text
    без изменений, если сегодня нет повода, AI недоступен, AI не
    ответил, или этот же повод уже отправляли на предыдущем сегодняшнем
    слоте."""
    if ai_client is None:
        return text

    assistant_service = build_assistant_service(session)
    already_sent_key = await assistant_service.get_today_nudge_trigger(telegram_user_id)
    candidate = await find_nudge_candidate(
        telegram_user_id,
        habit_service,
        task_service,
        exclude_trigger_key=already_sent_key,
    )
    if candidate is None:
        return text

    trigger_key, situation = candidate
    persona = await assistant_service.get_persona(telegram_user_id)
    nudge_text = await generate_nudge_text(ai_client, situation, persona)
    if not nudge_text:
        return text

    await assistant_service.record_nudge_sent(telegram_user_id, trigger_key)
    return f"{text}\n\n{nudge_text}"


async def send_morning_briefing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Утренний слот (см. flows/009-daily-rhythm.md). С specs/016-
    engagement-hooks.md дописывает снизу утренний рефлексивный вопрос
    (раньше — отдельная джоба send_morning_reflection_job в отдельном
    слоте 10:30) тем же паттерном, что уже использует вечерний чек-ин
    для gap-вопроса: меньше отдельных push-сообщений в день, у которых
    нет действия/награды за прочтение — было замечено, что только
    дайджесты каналов реально читаются регулярно, остальное "иногда
    читаю, но не действую"."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — утренний брифинг не отправлен"
        )
        return

    ai_client = get_ai_client(settings)

    async with AsyncSessionLocal() as session:
        task_service = build_task_service(session)
        memory_service = MemoryService(MemoryRepository(session))
        habit_service = HabitService(HabitRepository(session))
        goal_service = GoalService(GoalRepository(session))
        persona = await build_assistant_service(session).get_persona(telegram_user_id)
        text = await build_morning_briefing(
            telegram_user_id,
            task_service,
            memory_service,
            habit_service,
            goal_service,
            ai_client=ai_client,
            persona=persona,
        )
        chart = await _try_build_chart(telegram_user_id, task_service, habit_service)

        prompt_service = build_prompt_service(session)
        question = await prompt_service.pick_morning_reflection(
            telegram_user_id, allow_gap=ai_client is not None
        )
        if question:
            text = f"{text}\n\n{question}"

    await _send_text_or_photo(context, telegram_user_id, text, chart)


async def send_evening_reflection_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вечерний слот 21:00 (см. flows/009-daily-rhythm.md) — глубокий
    AI-вопрос для дневника (заменяет прежний статичный текст с просьбой
    напечатать "дневник: ..."). Открывает category="journal" — ответ
    ловится ConversationEngine._try_capture_journal без префикса.

    Под тем же сообщением — 5 кнопок настроения (specs/019-mood-tracker.md):
    отдельного push-слота под них не заводим (specs/016-engagement-hooks.md
    — лишний слот без действия хуже, чем отсутствие метрики), тап
    обрабатывается в app/telegram/callbacks.py::_handle_mood_action и
    редактирует ЭТО ЖЕ сообщение, не мешая дневниковому pending выше."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — вечерняя рефлексия не отправлена"
        )
        return

    async with AsyncSessionLocal() as session:
        persona = await build_assistant_service(session).get_persona(telegram_user_id)
        question = await build_evening_reflection_prompt(
            get_ai_client(settings), persona=persona
        )
        await PendingPromptRepository(session).upsert(
            telegram_user_id, "journal", question
        )

    await context.bot.send_message(
        chat_id=telegram_user_id,
        text=question,
        reply_markup=build_mood_prompt_keyboard(),
    )


async def send_midday_checkin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Дневной слот 14:00 (см. flows/009-daily-rhythm.md) — «как дела» +
    табличка привычек прямо под сообщением (переиспользует
    build_habits_message — то же, что и по команде /habits), чтобы
    отметить выполненное можно было в один тап, без печати.

    Открывает category="journal" (как утренняя/вечерняя рефлексия) —
    иначе свободный текстовый ответ на "как дела" уходит в обычный
    разбор намерения ConversationEngine и по умолчанию создаёт задачу
    (баг: ответ на этот чек-ин распознавался как ADD_TASK)."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    ai_client = get_ai_client(settings)

    async with AsyncSessionLocal() as session:
        habit_service = HabitService(HabitRepository(session))
        task_service = build_task_service(session)
        habits = await habit_service.list_active_habits(telegram_user_id)
        if not habits:
            await PendingPromptRepository(session).upsert(
                telegram_user_id, "journal", _MIDDAY_TEXT_NO_HABITS
            )
            text = await _maybe_append_persona_nudge(
                session,
                ai_client,
                telegram_user_id,
                habit_service,
                task_service,
                _MIDDAY_TEXT_NO_HABITS,
            )
            await context.bot.send_message(chat_id=telegram_user_id, text=text)
            return
        streaks = await habit_service.get_streaks_bulk(
            telegram_user_id, [h.id for h in habits]
        )
        habits_text, markup = build_habits_message(habits, streaks)
        await PendingPromptRepository(session).upsert(
            telegram_user_id, "journal", _MIDDAY_TEXT
        )
        # Раньше текст со списком привычек (в котором и есть номера "1",
        # "2", на которые ссылаются кнопки под сообщением) выбрасывался —
        # уходил только общий вопрос "Как проходит твой день?" + кнопки с
        # голыми номерами без подписей, на что именно они отвечают.
        text = await _maybe_append_persona_nudge(
            session,
            ai_client,
            telegram_user_id,
            habit_service,
            task_service,
            f"{_MIDDAY_TEXT}\n\n{habits_text}",
        )

    # Список добавлен HTML — parse_mode нужен, иначе <b>1</b> уедет как
    # текст.
    await context.bot.send_message(
        chat_id=telegram_user_id,
        text=text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )


async def send_evening_checkin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вечерний итоговый слот 19:00 (см. flows/009-daily-rhythm.md) —
    что сделано сегодня (задачи/привычки) + иногда, если есть реальный
    гэп в профиле, gap-вопрос про цель/привычку/проект снизу. Вопрос —
    необязательное дополнение здесь, не главное содержание сообщения."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    ai_client = get_ai_client(settings)

    async with AsyncSessionLocal() as session:
        task_service = build_task_service(session)
        habit_service = HabitService(HabitRepository(session))
        text = await build_evening_checkin_text(
            telegram_user_id, task_service, habit_service
        )

        if ai_client is not None and random.random() < _EVENING_GAP_CHANCE:
            service = build_prompt_service(session)
            gap_question = await service.pick_gap_question_if_any(telegram_user_id)
            if gap_question:
                text = f"{text}\n\n{gap_question}"

        text = await _maybe_append_persona_nudge(
            session, ai_client, telegram_user_id, habit_service, task_service, text
        )

    await context.bot.send_message(
        chat_id=telegram_user_id, text=text, parse_mode=ParseMode.HTML
    )


async def send_weekly_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — еженедельный дайджест не отправлен"
        )
        return

    async with AsyncSessionLocal() as session:
        task_service = build_task_service(session)
        habit_service = HabitService(HabitRepository(session))
        persona = await build_assistant_service(session).get_persona(telegram_user_id)
        text = await build_weekly_digest(
            telegram_user_id,
            task_service,
            habit_service,
            GoalService(GoalRepository(session)),
            ai_client=get_ai_client(settings),
            persona=persona,
            focus_service=build_focus_service(session),
        )
        chart = await _try_build_chart(
            telegram_user_id, task_service, habit_service, build_mood_service(session)
        )

    await _send_text_or_photo(context, telegram_user_id, text, chart)


async def send_finance_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Финансовый отчёт по воскресеньям (см. specs/017-finance.md) —
    отдельная джоба, НЕ часть app/digest/ (решено владельцем заранее,
    см. HANDOFF)."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — финансовый отчёт не отправлен"
        )
        return

    async with AsyncSessionLocal() as session:
        finance_service = build_finance_service(session)
        persona = await build_assistant_service(session).get_persona(telegram_user_id)
        text = await build_finance_report(
            telegram_user_id,
            finance_service,
            ai_client=get_ai_client(settings),
            persona=persona,
        )

    await context.bot.send_message(
        chat_id=telegram_user_id, text=text, parse_mode=ParseMode.HTML
    )


async def send_digests_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Дайджесты Telegram-каналов (см. specs/013-channel-digests.md).

    Одна общая job на ВСЕ дайджесты владельца, а не по job на дайджест:
    динамическая регистрация/снятие job при каждом /digest_new — лишняя
    сложность ради того же результата (ADR-004). Частота живёт в данных:
    "daily" — каждый прогон, "weekly" — только по воскресеньям, NULL —
    только по команде /digest <name>.

    Дайджест без новых постов пропускается тихо (build_digest_text
    вернул None) — фоновая рассылка не должна слать "нечего показать",
    это шум (как send_monthly_insights_job).
    """
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    is_sunday = date.today().weekday() == SUNDAY_WEEKDAY
    ai_client = get_ai_client(settings)

    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        digests = await service.list_digests(telegram_user_id)

        # (id, text) — не просто text: кнопке "⭐ Сохранить" ниже нужен id
        # темы в callback_data (см. specs/016-engagement-hooks.md).
        to_send: list[tuple[int, str]] = []
        for digest in digests:
            if digest.auto_frequency == DAILY or (
                digest.auto_frequency == WEEKLY and is_sunday
            ):
                text = await service.build_digest_text(
                    telegram_user_id, digest.name, ai_client=ai_client
                )
                if text:
                    to_send.append((digest.id, text))

    for digest_id, text in to_send:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⭐ Сохранить", callback_data=f"d|f|{digest_id}")]]
        )
        await context.bot.send_message(
            chat_id=telegram_user_id, text=text, reply_markup=markup
        )


async def _try_build_chart(
    telegram_user_id: int,
    task_service: TaskService,
    habit_service: HabitService,
    mood_service: MoodService | None = None,
):
    """Картинка — бонус, а не критичная часть сообщения; сбой рендера
    (например, из-за шрифтов) не должен срывать отправку текста (тот же
    принцип, что и у AI-инсайтов везде в проекте)."""
    try:
        chart_data = await gather_chart_data(
            telegram_user_id, task_service, habit_service, mood_service
        )
        return render_chart(chart_data)
    except Exception:
        logger.exception("Не удалось построить график")
        return None


async def _send_text_or_photo(
    context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int, text: str, chart
) -> None:
    if chart is None:
        await context.bot.send_message(
            chat_id=telegram_user_id, text=text, parse_mode=ParseMode.HTML
        )
        return

    if len(text) <= _PHOTO_CAPTION_LIMIT:
        await context.bot.send_photo(
            chat_id=telegram_user_id,
            photo=chart,
            caption=text,
            parse_mode=ParseMode.HTML,
        )
    else:
        await context.bot.send_photo(chat_id=telegram_user_id, photo=chart)
        await context.bot.send_message(
            chat_id=telegram_user_id, text=text, parse_mode=ParseMode.HTML
        )


async def send_monthly_insights_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Personal Insights раз в месяц, 1-е число (см.
    specs/009-personal-insights.md, flows/010-personal-insights.md).
    PTB JobQueue не умеет "раз в месяц" из коробки — регистрируется как
    ежедневная job (см. app/telegram/bot.py), а фильтр по дню — здесь.
    Тихий пропуск, если находок нет — фоновая рассылка не должна слать
    "недостаточно данных", это шум (в отличие от кнопки "📊 Инсайты" по
    запросу, см. app/telegram/handlers.py::_send_insights)."""
    if date.today().day != 1:
        return

    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        service = InsightsService(
            build_task_service(session),
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
        )
        findings = await service.build_findings(telegram_user_id)

    if not findings:
        return

    await context.bot.send_message(
        chat_id=telegram_user_id, text=build_insights_text(findings)
    )


async def send_nudges_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Нэджи по целям/привычкам/контактам (см. app/scheduler/nudges.py).
    Если нечего сказать — build_nudges вернёт пустой список и ничего не
    отправляется (как send_task_reminders_job, когда нечего напомнить)."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        lines = await build_nudges(
            telegram_user_id,
            GoalService(GoalRepository(session)),
            HabitService(HabitRepository(session)),
            build_contact_service(session),
        )

    if not lines:
        return

    await context.bot.send_message(chat_id=telegram_user_id, text="\n\n".join(lines))


async def embed_pending_memories_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фоновая доливка embedding для записей памяти без него — семантический
    поиск (см. specs/011-semantic-memory-search.md). Не привязана к
    telegram_user_id — single-user проект (PROJECT.md), как и напоминания
    о задачах. Без ключа AI просто ничего не делает (тихий пропуск)."""
    settings = get_settings()
    ai_client = get_ai_client(settings)
    if ai_client is None:
        return

    async with AsyncSessionLocal() as session:
        service = MemoryService(MemoryRepository(session))
        embedded = await service.backfill_embeddings(
            ai_client, batch_size=settings.memory_embedding_batch_size
        )

    if embedded:
        logger.info("Проэмбеддено %d записей памяти", embedded)


async def send_habit_reminders_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Напоминание о привычке в заданное ею время (см. миграцию 015).

    Отличие от напоминаний о задачах: у задачи момент один и навсегда, у
    привычки время ежедневное, поэтому «уже напомнили» хранится днём
    (`last_reminded_on`), а не флагом. Привычки, отмеченные сегодня,
    сервис отсеивает сам — напоминать о сделанном значит приучить
    игнорировать напоминания.

    Кнопка «✅ Отметить» идёт сразу под сообщением: напоминание, после
    которого надо идти в меню, срабатывает вдвое реже.
    """
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        habit_service = HabitService(HabitRepository(session))
        for habit in await habit_service.list_due_reminders():
            if habit.telegram_user_id != telegram_user_id:
                continue
            text = f"🔁 Напоминание: «{escape(habit.title, quote=False)}»"
            if habit.description:
                text += f"\n<i>{escape(habit.description, quote=False)}</i>"
            await context.bot.send_message(
                chat_id=telegram_user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Отметить", callback_data=f"h|d|{habit.id}"
                            )
                        ]
                    ]
                ),
            )
            await habit_service.mark_reminded(habit)


async def send_task_reminders_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        task_service = build_task_service(session)
        due_tasks = await task_service.list_due_reminders()
        for task in due_tasks:
            if task.telegram_user_id != telegram_user_id:
                continue
            await context.bot.send_message(
                chat_id=telegram_user_id, text=f"⏰ Напоминание: «{task.title}»"
            )
            await task_service.mark_reminded(telegram_user_id, task.id)


async def send_focus_notifications_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Опрос БД на "пора" (specs/026-focus-sessions.md) — тот же приём,
    что у напоминаний задач/привычек выше, не job_queue.run_once: API и
    бот в этом проекте разные процессы (отдельные контейнеры
    docker-compose), in-memory таймер бота не виден из API и не
    переживает рестарт бота (деплой перезапускает контейнер на каждую
    правку). Один тик — сразу оба перехода (работа→перерыв,
    перерыв→конец), не два отдельных вызова."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        service = build_focus_service(session)

        for focus in await service.list_due_work_end():
            if focus.telegram_user_id != telegram_user_id:
                continue
            updated = await service.mark_work_notified(focus)
            await context.bot.send_message(
                chat_id=telegram_user_id,
                text=(
                    f"⏱ Работа окончена! Перерыв {updated.break_minutes} мин — "
                    "потом ещё одно сообщение, когда закончится."
                ),
            )

        for focus in await service.list_due_break_end():
            if focus.telegram_user_id != telegram_user_id:
                continue
            await service.mark_break_notified(focus)
            await context.bot.send_message(
                chat_id=telegram_user_id,
                text="✅ Перерыв закончен, сессия завершена. Отличная работа!",
            )
