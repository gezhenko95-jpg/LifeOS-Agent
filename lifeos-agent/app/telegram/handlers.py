"""
Хендлеры Telegram-бота.

Свободный текст и одиночные команды («выполнил молоко», «привычка
чтение», добавление задачи) идут через ConversationEngine (Telegram-
агностичный, см. app/conversation/engine.py). Списки (`/tasks`,
`/habits`, `/goals` и их текстовые синонимы) отправляются напрямую с
inline-кнопками (app/telegram/keyboards.py) — ConversationEngine не
должен знать про Telegram-специфичные типы.
"""

import asyncio
import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.ai.client import AIServiceError, get_ai_client
from app.conversation.birthday_parser import extract_birthday
from app.conversation.intent import Intent, ParsedIntent
from app.conversation.parser import (
    parse_add_task,
    parse_finance_expense,
    parse_finance_income,
    parse_intent,
)
from app.core.config import get_settings
from app.core.container import build_contact_service, build_digest_service, build_engine
from app.db.session import AsyncSessionLocal
from app.digest.scraper import ChannelScrapeError
from app.drive.client import get_drive_client
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.insights.formatting import build_insights_text
from app.insights.service import InsightsService
from app.media_inbox.service import MediaInboxService
from app.memory.models import MemoryType
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService
from app.telegram.keyboards import (
    MENU_CONTACTS,
    MENU_DIGEST,
    MENU_FINANCE,
    MENU_GOALS,
    MENU_HABITS,
    MENU_HELP,
    MENU_INSIGHTS,
    MENU_JOURNAL,
    MENU_MOOD,
    MENU_SITE,
    MENU_TASKS,
    MENU_WATCHLIST,
    build_contacts_menu,
    build_digest_detail_message,
    build_digest_menu_message,
    build_finance_menu,
    build_goals_menu,
    build_goals_message,
    build_habits_menu,
    build_habits_message,
    build_journal_entries_message,
    build_journal_menu,
    build_main_menu,
    build_mood_menu,
    build_open_site_keyboard,
    build_task_quick_actions_keyboard,
    build_tasks_menu,
    build_tasks_message,
    build_watchlist_menu,
    build_watchlist_message,
    schedule_label,
)
from app.telegram.pending_input import (
    CONTACT_ADD,
    DIGEST_CHANNEL,
    DIGEST_NEW,
    FINANCE_EXPENSE_ADD,
    FINANCE_INCOME_ADD,
    GOAL_ADD,
    HABIT_ADD,
    JOURNAL_SEARCH,
    TASK_ADD,
    WATCHLIST_ADD,
    clear_pending,
    pop_pending,
)
from app.watchlist.books import get_books_client
from app.watchlist.models import MEDIA_TYPE_EMOJI
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService
from app.watchlist.tmdb import get_tmdb_client

logger = logging.getLogger(__name__)

JOURNAL_PROMPT = "Что запишем в дневник? Пиши как есть — сохраню без изменений."

_START_TEXT = (
    "Привет! Я LifeOS — помогаю не забывать задачи.\n"
    "Просто напишите, что нужно сделать, например «Завтра купить молоко», "
    "или воспользуйтесь меню снизу.\n"
    "Команда /help — что я умею.\n\n"
    "Ваш Telegram ID: {telegram_user_id}\n"
    "Впишите его в .env как owner_telegram_user_id, чтобы получать "
    "утренний брифинг."
)

# Постоянное меню (ReplyKeyboardMarkup, см. keyboards.py) — нажатие
# отправляет этот же текст обычным сообщением, поэтому просто матчим его
# точным сравнением до разбора естественного языка.
#
# Кнопка домена всегда открывает ЭКРАН РАЗДЕЛА — одинаково для всех
# шести доменов, никаких исключений. Экран строится чистой функцией из
# keyboards.py, данные ему не нужны — кроме дайджестов, где сам список
# тем и есть содержимое экрана (см. _send_digest_menu).
_MENU_SECTIONS = {
    MENU_TASKS: build_tasks_menu,
    MENU_HABITS: build_habits_menu,
    MENU_GOALS: build_goals_menu,
    MENU_JOURNAL: build_journal_menu,
    MENU_WATCHLIST: build_watchlist_menu,
    MENU_FINANCE: build_finance_menu,
    MENU_CONTACTS: build_contacts_menu,
    MENU_MOOD: build_mood_menu,
}

# Кнопки-утилиты: своего домена и списка у них нет, экран из одного
# пункта был бы лишним щелчком — они остаются прямым действием.
_MENU_UTILITIES = {
    MENU_DIGEST: "digest",
    MENU_INSIGHTS: "insights",
    MENU_SITE: "site",
    MENU_HELP: "help",
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    text = _START_TEXT.format(telegram_user_id=update.effective_user.id)
    await update.message.reply_text(text, reply_markup=build_main_menu())


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переотправить постоянное меню.

    ReplyKeyboardMarkup живёт на клиенте, пока его не заменят новым —
    поэтому кнопка, добавленная в build_main_menu после последнего
    /start, у пользователя просто не появляется (так и не появилась
    «🌐 Сайт»). Раньше единственным способом обновить меню был /start,
    который вдобавок показывает приветствие для первой настройки.
    """
    if update.message is None:
        return
    await update.message.reply_text("Меню обновлено.", reply_markup=build_main_menu())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_via_engine(update, context, "/help")


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_tasks_keyboard(update)


async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_habits_keyboard(update)


async def goals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_goals_keyboard(update)


async def handle_photo_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Фаза 2 Media Inbox (см. specs/010-media-inbox.md) — эскизы и
    скриншоты фильмов/книг автоматически раскладываются по Google Drive.
    Если Drive не настроен (нет token.json) — явно говорим об этом, а не
    молчим: пользователь мог не понять, что фото вообще не обработалось.

    После успешной загрузки оригинал фото удаляется из чата (файл уже
    на Диске, дублировать его в кеше Telegram незачем) — только при
    успехе, иначе фото потеряется, если Drive не смог его сохранить."""
    if update.message is None or not update.message.photo:
        return
    if update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    # Построение клиента читает token.json с диска — блокирующая операция,
    # как и сами вызовы Drive API (см. MediaInboxService._upload_to_drive).
    drive_client = await asyncio.to_thread(get_drive_client)
    if drive_client is None:
        await update.message.reply_text(
            "Media Inbox ещё не настроен (нет token.json на сервере)."
        )
        return

    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.UPLOAD_PHOTO
    )

    photo = update.message.photo[-1]  # последний элемент — самое большое разрешение
    file = await context.bot.get_file(photo.file_id)
    content = bytes(await file.download_as_bytearray())
    filename = f"{photo.file_unique_id}.jpg"

    async with AsyncSessionLocal() as session:
        service = MediaInboxService(
            drive_client,
            WatchlistService(WatchlistRepository(session)),
            get_ai_client(),
        )
        saved, reply = await service.handle_photo(
            telegram_user_id, filename, content, "image/jpeg"
        )

    if saved:
        try:
            await update.message.delete()
        except Exception:
            # Не критично — файл уже на Диске, просто оригинал останется
            # в чате (например, если сообщение старше 48 часов).
            logger.warning("Не удалось удалить фото-сообщение после загрузки")
        await context.bot.send_message(chat_id=telegram_user_id, text=reply)
    else:
        await update.message.reply_text(reply)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Полный порядок разбора одного текстового сообщения (см.
    AUDIT.md, A-6 — раньше нигде не был описан одним куском):

    1. `_MENU_ACTIONS` — точное совпадение с текстом кнопки постоянного
       меню. Обслуживает в т.ч. действия, которых нет в `Intent` вообще
       (goals, insights, add_task-подсказка, дневник, сайт). Голосовые
       сообщения (`handle_voice_message`) через этот шаг не проходят —
       распознанный текст физически не может буквально совпасть с
       текстом кнопки.
    2. `parse_intent(text)` (см. `_route_parsed_text` ниже — общий хвост
       и для текста, и для голоса после транскрипции) — ЕСЛИ результат
       `LIST_TASKS`/`LIST_HABITS`/`LIST_WATCHLIST`, ответ уходит напрямую
       с inline-клавиатурой (`keyboards.py`) — это единственные три
       intent'а, для которых `ConversationEngine` (Telegram-агностичный)
       не может построить кнопки сам, только текстовый фолбэк.
    3. Иначе — `ConversationEngine.handle_message` (см. `engine.py`):
       перехват дневникового pending → тот же `parse_intent` (уже
       посчитан здесь на шаге 2, вторым разбором внутри движка не
       делается, см. AUDIT.md A-5) → попытка понять как ответ на
       проактивный вопрос → AI-фолбэк → диспетчеризация по intent.

    Известный (узкий) edge-case: шаг 2 идёт РАНЬШЕ шага 3 — если открыт
    дневниковый pending и ответ пользователя случайно совпадает с
    LIST-триггером («привычки», «покажи задачи»), уйдёт клавиатура
    вместо записи в дневник. Не переупорядочиваем ради этого (нужен
    отдельный поход в БД за pending-состоянием до решения о маршруте на
    КАЖДОЕ сообщение) — задокументировано, не спрятано.
    """
    if update.message is None or update.message.text is None:
        return

    text = update.message.text

    section = _MENU_SECTIONS.get(text)
    utility = _MENU_UTILITIES.get(text)
    if section is not None or utility is not None:
        # Ушли в другой раздел — ожидание ввода от кнопки («➕ Добавить»,
        # «➕ Канал», …) больше не актуально. Без этого оно осталось бы
        # висеть ловушкой и проглотило бы следующее сообщение вообще из
        # другой темы (см. app/telegram/pending_input.py).
        clear_pending(context.user_data)

    if section is not None:
        await _send_section(update, section())
        return
    if utility == "digest":
        await _send_digest_menu(update)
        return
    if utility == "insights":
        await _send_insights(update)
        return
    if utility == "site":
        await _send_site_link(update)
        return
    if utility == "help":
        await _reply_via_engine(update, context, "/help")
        return

    await _route_parsed_text(update, context, text)


async def _route_parsed_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    """Общий хвост для текстовых (после проверки `_MENU_ACTIONS`) и
    голосовых (`handle_voice_message`, после транскрипции) сообщений —
    решает, не LIST_TASKS/LIST_HABITS/LIST_WATCHLIST ли это (нужна
    Telegram-специфичная inline-клавиатура, движок сам её не построит),
    иначе отдаёт в движок. Было продублировано дословно между
    handle_text_message и handle_voice_message — вынесено в одно место.

    Первым делом — ожидание ввода от кнопки раздела (см.
    app/telegram/pending_input.py): если пользователь только что нажал
    «➕ Добавить»/«➕ Канал»/«🔍 По теме», это сообщение целиком и есть
    ответ, разбирать его как обычную фразу не нужно. Проверка живёт
    ЗДЕСЬ, а не в handle_text_message, чтобы голосом можно было ответить
    ровно так же, как текстом."""
    if await _consume_pending_input(update, context, text):
        return

    parsed = parse_intent(text)
    if parsed.intent is Intent.LIST_TASKS:
        await _send_tasks_keyboard(update)
        return
    if parsed.intent is Intent.LIST_HABITS:
        await _send_habits_keyboard(update)
        return
    if parsed.intent is Intent.LIST_WATCHLIST:
        await _send_watchlist_keyboard(update)
        return

    await _reply_via_engine(update, context, text, parsed=parsed)


async def _consume_pending_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> bool:
    """True — сообщение было ответом на кнопку и уже обработано.

    Ожидание одноразовое: `pop_pending` снимает его сразу, даже если
    обработка ниже закончится ошибкой — иначе неудачная попытка («канал
    не найден») оставила бы ловушку висеть, и следующая обычная фраза
    снова ушла бы в добавление канала."""
    if update.message is None or update.effective_user is None:
        return False

    pending = pop_pending(context.user_data)
    if pending is None:
        return False

    telegram_user_id = update.effective_user.id

    if pending.kind == TASK_ADD:
        # Задача — единственный вид, где текст после кнопки всё равно
        # разбирается движком: в нём может быть срок («завтра в 19:00»),
        # приоритет и повтор. Но intent обязан быть ADD_TASK всегда —
        # без parse_add_task общий parse_intent (внутри движка) мог бы
        # перехватить, например, "готово к отправке письмо" как
        # COMPLETE_TASK ("готово" — триггер), и ввод после кнопки молча
        # терялся бы (см. HANDOFF/code-review). parse_add_task — тот же
        # разбор даты/приоритета/повтора, что и обычный ADD_TASK-хвост
        # parse_intent, второй парсер дат не заводится.
        await _reply_via_engine(update, context, text, parsed=parse_add_task(text))
        return True
    if pending.kind == HABIT_ADD:
        await _create_habit_from_text(update, telegram_user_id, text)
        return True
    if pending.kind == GOAL_ADD:
        await _create_goal_from_text(update, telegram_user_id, text)
        return True
    if pending.kind == WATCHLIST_ADD:
        await _add_watchlist_item_from_text(update, telegram_user_id, text)
        return True
    if pending.kind == JOURNAL_SEARCH:
        await _search_journal(update, telegram_user_id, text)
        return True
    if pending.kind == DIGEST_NEW:
        await _create_digest_from_text(update, telegram_user_id, text)
        return True
    if pending.kind == DIGEST_CHANNEL and pending.digest_id is not None:
        await _add_digest_channel_from_text(
            update, context, telegram_user_id, pending.digest_id, text
        )
        return True
    if pending.kind == FINANCE_EXPENSE_ADD:
        await _reply_via_engine(
            update, context, text, parsed=parse_finance_expense(text)
        )
        return True
    if pending.kind == FINANCE_INCOME_ADD:
        await _reply_via_engine(
            update, context, text, parsed=parse_finance_income(text)
        )
        return True
    if pending.kind == CONTACT_ADD:
        await _create_contact_from_text(update, telegram_user_id, text)
        return True
    return False


async def _create_habit_from_text(
    update: Update, telegram_user_id: int, text: str
) -> None:
    """«➕ Добавить» в привычках: название целиком, без разбора — кнопка
    уже сказала, что это привычка, а слово «привычка» в начале фразы (как
    требует текстовый путь) здесь только мешало бы."""
    if update.message is None:
        return

    async with AsyncSessionLocal() as session:
        service = HabitService(HabitRepository(session))
        try:
            habit = await service.create_habit(telegram_user_id, text.strip())
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

    await update.message.reply_text(f"🔁 Новая привычка: «{habit.title}»")


async def _create_goal_from_text(
    update: Update, telegram_user_id: int, text: str
) -> None:
    """«➕ Добавить» в целях. Срок цели не спрашиваем: он необязателен, а
    лишний шаг диалога ради него отпугивает больше, чем помогает — дату
    всегда можно поставить позже."""
    if update.message is None:
        return

    async with AsyncSessionLocal() as session:
        service = GoalService(GoalRepository(session))
        try:
            goal = await service.create_goal(telegram_user_id, text.strip())
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

    await update.message.reply_text(f"🎯 Новая цель: «{goal.title}»")


async def _create_contact_from_text(
    update: Update, telegram_user_id: int, text: str
) -> None:
    """«➕ Добавить» в «📇 Люди» — имя обязательно, дата рождения
    («дд.мм», без года, см. birthday_parser.py) — необязательный кусок
    того же сообщения в любом месте текста. Остаток после вырезанной
    даты становится именем целиком, без разбора триггерных слов (кнопка
    уже сказала, что это контакт, см. _create_habit_from_text — тот же
    приём)."""
    if update.message is None:
        return

    month, day, name = extract_birthday(text.strip())

    async with AsyncSessionLocal() as session:
        service = build_contact_service(session)
        try:
            contact = await service.add_contact(
                telegram_user_id, name, birthday_month=month, birthday_day=day
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

    birthday_note = (
        f" · 🎂 {contact.birthday_day:02d}.{contact.birthday_month:02d}"
        if contact.birthday_month and contact.birthday_day
        else ""
    )
    await update.message.reply_text(
        f"📇 Новый контакт: «{contact.name}»{birthday_note}"
    )


async def _add_watchlist_item_from_text(
    update: Update, telegram_user_id: int, text: str
) -> None:
    """«➕ Добавить» на полку. Префикс «фильм»/«книга» необязателен —
    кнопка уже сказала, куда мы добавляем, поэтому голое «Дюна» тоже
    работает (тип тогда «другое»). Если префикс всё же написан — он
    разберётся штатным парсером, и тип сохранится правильный."""
    if update.message is None:
        return

    parsed = parse_intent(text)
    if parsed.intent is Intent.ADD_WATCHLIST_ITEM and parsed.title:
        title = parsed.title
        media_type = parsed.media_type or "other"
    else:
        title = text.strip()
        media_type = "other"

    async with AsyncSessionLocal() as session:
        service = WatchlistService(WatchlistRepository(session))
        try:
            item = await service.create_item(
                telegram_user_id,
                title,
                media_type,
                tmdb_client=get_tmdb_client(),
                books_client=get_books_client(),
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

    await _reply_with_media_card(update, item, "Добавил на полку")


async def _reply_with_media_card(update: Update, item, prefix: str) -> None:
    """Ответ о добавленной записи полки. Есть обложка — шлём картинкой с
    подписью: карточка фильма читается с одного взгляда, а голое название
    ничем не отличается от обычной задачи. Нет обложки (книга, ничего не
    нашлось, выключенный TMDb) — прежний текстовый ответ."""
    if update.message is None:
        return

    emoji = MEDIA_TYPE_EMOJI.get(item.media_type, "🎯")
    year = f" ({item.release_year})" if item.release_year else ""
    caption = f"{emoji} {prefix}: «{item.title}»{year}"
    if item.overview:
        caption += "\n\n" + item.overview

    if not item.poster_url:
        await update.message.reply_text(caption)
        return

    try:
        await update.message.reply_photo(item.poster_url, caption=caption)
    except TelegramError as exc:
        # Постер — украшение: если Telegram не смог его забрать по ссылке,
        # сообщение всё равно должно дойти.
        logger.warning("Обложка не отправилась: %s", exc)
        await update.message.reply_text(caption)


async def _search_journal(update: Update, telegram_user_id: int, query: str) -> None:
    """«🔍 По теме» — буквальный поиск по дневнику (тот же ILIKE в БД, что
    у «напомни про …»), результат — тот же список записей с кнопками, что
    и «📖 Записи»."""
    if update.message is None:
        return

    async with AsyncSessionLocal() as session:
        service = MemoryService(MemoryRepository(session))
        entries = await service.search(telegram_user_id, query, type=MemoryType.JOURNAL)

    text, markup = build_journal_entries_message(
        entries, header=f"🔍 Дневник по «{query}»"
    )
    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _create_digest_from_text(
    update: Update, telegram_user_id: int, text: str
) -> None:
    """«➕ Новый дайджест» — то же, что /digest_new, но введённое одной
    строкой: «ESG» или «ESG daily»."""
    if update.message is None:
        return

    parts = text.split()
    if not 1 <= len(parts) <= 2:
        await update.message.reply_text(
            "Нужно имя одним словом и (по желанию) частота: «ESG» или «ESG daily»."
        )
        return

    name = parts[0]
    frequency = parts[1].lower() if len(parts) == 2 else None

    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        try:
            digest = await service.create_digest(telegram_user_id, name, frequency)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        digests = await service.list_digests(telegram_user_id)

    await update.message.reply_text(
        f"✅ Дайджест «{digest.name}» создан ({schedule_label(digest.auto_frequency)}). "
        "Теперь добавьте в него каналы."
    )
    menu_text, markup = build_digest_menu_message(digests)
    await update.message.reply_text(
        menu_text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _add_digest_channel_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    digest_id: int,
    text: str,
) -> None:
    """«➕ Канал» — проверка канала идёт по сети (см. DigestService.
    add_channel), поэтому «печатает…», как и везде, где ответ не мгновенный."""
    if update.message is None:
        return

    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.TYPING
    )

    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        digest = await service.get_digest(telegram_user_id, digest_id)
        if digest is None:
            await update.message.reply_text("Этого дайджеста больше нет.")
            return
        try:
            added = await service.add_channel(
                telegram_user_id, digest.name, text.strip()
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        except ChannelScrapeError as exc:
            logger.warning("Канал не добавлен в дайджест: %s", exc)
            await update.message.reply_text(
                f"Не нашёл канал «{text.strip()}» — он существует и публичный?"
            )
            return
        channels = await service.list_channels(digest.id)

    await update.message.reply_text(
        f"✅ @{added.channel_username} добавлен в «{digest.name}». "
        "Дальше присылаю только новые посты."
    )
    detail_text, markup = build_digest_detail_message(digest, channels)
    await update.message.reply_text(
        detail_text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def handle_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Голосовое → текст (OpenRouter STT, см. specs/012-voice-input.md)
    → тот же путь, что у обычного текстового сообщения (_route_parsed_text,
    без _MENU_ACTIONS — голос не совпадает с текстом кнопки буквально).

    Конвертация формата не нужна: Telegram отдаёт voice в OGG (Opus
    внутри), а `ogg` — среди официально поддерживаемых форматов и у
    OpenRouter, и у самого OpenAI whisper."""
    if update.message is None or update.message.voice is None:
        return
    if update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    ai_client = get_ai_client()
    if ai_client is None:
        await update.message.reply_text(
            "Голосовой ввод ещё не настроен (нет ключа OpenRouter)."
        )
        return

    voice = update.message.voice
    max_seconds = get_settings().voice_max_duration_seconds
    if voice.duration > max_seconds:
        await update.message.reply_text(
            f"Голосовое длиннее {max_seconds // 60} мин — пришлите текстом."
        )
        return

    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.TYPING
    )
    file = await context.bot.get_file(voice.file_id)
    content = bytes(await file.download_as_bytearray())

    try:
        text = (await ai_client.transcribe(content)).strip()
    except AIServiceError as exc:
        logger.warning("Транскрипция голосового не удалась: %s", exc)
        await update.message.reply_text(
            "Не получилось распознать голосовое — попробуйте текстом?"
        )
        return

    if not text:
        await update.message.reply_text(
            "Не расслышал — тишина или не разобрал ни слова."
        )
        return

    # Показываем распознанное ДО ответа движка — иначе ошибку STT
    # (перепутанное слово в названии задачи) невозможно заметить
    # постфактум.
    await update.message.reply_text(f"🎤 «{text}»")
    await _route_parsed_text(update, context, text)


async def _send_tasks_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = TaskService(TaskRepository(session))
        tasks = await service.list_active_tasks(telegram_user_id)
        text, markup = build_tasks_message(tasks)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_habits_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = HabitService(HabitRepository(session))
        habits = await service.list_active_habits(telegram_user_id)
        streaks = await service.get_streaks_bulk(
            telegram_user_id, [h.id for h in habits]
        )
        text, markup = build_habits_message(habits, streaks)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_goals_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = GoalService(GoalRepository(session))
        goals = await service.list_active_goals(telegram_user_id)
        text, markup = build_goals_message(goals)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_section(
    update: Update, screen: tuple[str, "InlineKeyboardMarkup"]
) -> None:
    """Экран раздела (полка/дневник) — чистая презентация, за данными
    ходить не нужно, поэтому один общий отправитель на все такие экраны."""
    if update.message is None:
        return
    text, markup = screen
    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_digest_menu(update: Update) -> None:
    """Экран «📰 Дайджест» — в отличие от полки и дневника, сам список
    дайджестов и есть содержимое экрана, поэтому нужен поход в БД."""
    if update.message is None or update.effective_user is None:
        return

    async with AsyncSessionLocal() as session:
        digests = await build_digest_service(session).list_digests(
            update.effective_user.id
        )

    text, markup = build_digest_menu_message(digests)
    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_watchlist_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = WatchlistService(WatchlistRepository(session))
        items = await service.list_active_items(telegram_user_id)
        text, markup = build_watchlist_message(items)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


# --- Дайджесты Telegram-каналов (см. specs/013-channel-digests.md) ---
#
# Первые команды проекта с аргументами: python-telegram-bot кладёт слова
# после команды в context.args (list[str]). Каждая команда — тонкий
# враппер: разобрать args, на неверный синтаксис ответить подсказкой (не
# исключением), остальное — в DigestService.

_DIGEST_NEW_USAGE = "Как это работает: /digest_new <имя> [daily|weekly]"
_DIGEST_ADD_USAGE = "Как это работает: /digest_add <имя> <канал>"
_DIGEST_REMOVE_USAGE = "Как это работает: /digest_remove <имя> <канал>"
_DIGEST_NOW_USAGE = "Как это работает: /digest <имя>"
_DIGEST_EMPTY = "Пока ни одного дайджеста. Создайте: /digest_new ESG"


async def digest_new_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    args = context.args or []
    if not 1 <= len(args) <= 2:
        await update.message.reply_text(_DIGEST_NEW_USAGE)
        return

    name = args[0]
    frequency = args[1].lower() if len(args) == 2 else None

    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        try:
            digest = await service.create_digest(
                update.effective_user.id, name, frequency
            )
        except ValueError as exc:
            await update.message.reply_text(f"{exc}\n{_DIGEST_NEW_USAGE}")
            return

    schedule = schedule_label(digest.auto_frequency)
    await update.message.reply_text(
        f"✅ Дайджест «{digest.name}» создан ({schedule}).\n"
        f"Добавьте каналы: /digest_add {digest.name} <канал>"
    )


async def digest_add_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(_DIGEST_ADD_USAGE)
        return

    name, channel = args
    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        try:
            added = await service.add_channel(update.effective_user.id, name, channel)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        except ChannelScrapeError as exc:
            logger.warning("Канал не добавлен в дайджест: %s", exc)
            await update.message.reply_text(
                f"Не нашёл канал «{channel}» — он существует и публичный?"
            )
            return

    await update.message.reply_text(
        f"✅ @{added.channel_username} добавлен в «{name}». "
        "Дальше присылаю только новые посты."
    )


async def digest_remove_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(_DIGEST_REMOVE_USAGE)
        return

    name, channel = args
    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        try:
            removed = await service.remove_channel(
                update.effective_user.id, name, channel
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

    if removed:
        await update.message.reply_text(f"🗑 Канал убран из «{name}».")
    else:
        await update.message.reply_text(f"Такого канала в «{name}» и не было.")


async def digest_list_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        digests = await service.list_digests(telegram_user_id)
        channels = {
            digest.id: await service.list_channels(digest.id) for digest in digests
        }

    if not digests:
        await update.message.reply_text(_DIGEST_EMPTY)
        return

    lines: list[str] = []
    for digest in digests:
        schedule = schedule_label(digest.auto_frequency)
        lines.append(f"📰 {digest.name} — {schedule}")
        items = channels.get(digest.id, [])
        if items:
            lines.extend(f"   • @{channel.channel_username}" for channel in items)
        else:
            lines.append("   (каналов пока нет)")
    await update.message.reply_text("\n".join(lines))


async def digest_now_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Дайджест по запросу, вне расписания. Читает каналы по сети и
    (если есть ключ) идёт в AI — секунды, поэтому «печатает…», как в
    _reply_via_engine."""
    if update.message is None or update.effective_user is None:
        return
    args = context.args or []
    if len(args) != 1:
        await update.message.reply_text(_DIGEST_NOW_USAGE)
        return

    telegram_user_id = update.effective_user.id
    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.TYPING
    )

    async with AsyncSessionLocal() as session:
        service = build_digest_service(session)
        try:
            text = await service.build_digest_text(
                telegram_user_id, args[0], ai_client=get_ai_client()
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

    # В отличие от фоновой job (тихий пропуск), по запросу отвечаем
    # всегда — пользователь сам спросил (тот же принцип, что у «📊 Инсайты»).
    await update.message.reply_text(text or "Новых постов пока нет.")


async def _send_site_link(update: Update) -> None:
    """Кнопка «🌐 Сайт» — ReplyKeyboardMarkup не умеет открывать ссылки
    напрямую, поэтому в ответ шлём сообщение с inline-кнопкой
    (InlineKeyboardButton(url=...), см. keyboards.py). Пусто в настройках
    — значит /ui ещё не задеплоен на публичный адрес, говорим прямо."""
    if update.message is None:
        return
    url = get_settings().public_ui_url
    if not url:
        await update.message.reply_text("Сайт ещё не настроен (нет публичного адреса).")
        return
    await update.message.reply_text(
        "Полный интерфейс:", reply_markup=build_open_site_keyboard(url)
    )


async def _send_insights(update: Update) -> None:
    """Кнопка «📊 Инсайты» — Personal Insights по запросу (см.
    specs/009-personal-insights.md). В отличие от фоновой месячной
    рассылки (app/telegram/jobs.py::send_monthly_insights_job), здесь
    отвечаем всегда, даже если находок нет — пользователь сам спросил."""
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = InsightsService(
            TaskService(TaskRepository(session)),
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
        )
        findings = await service.build_findings(telegram_user_id)

    await update.message.reply_text(build_insights_text(findings))


async def _reply_via_engine(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    parsed: ParsedIntent | None = None,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    telegram_user_id = update.effective_user.id

    # AI-вызовы (fallback-разбор, ответ на проактивный вопрос) занимают
    # секунду-две — "печатает…" даёт понять, что бот не завис.
    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.TYPING
    )

    async with AsyncSessionLocal() as session:
        engine = build_engine(session, ai_client=get_ai_client())
        result = await engine.handle_message(telegram_user_id, text, parsed)

    # created_task приходит от движка напрямую (см. EngineResult,
    # app/conversation/engine.py) — раньше здесь распознавали "задача
    # создана" regex'ом по тексту ответа и заново шли в БД за задачей
    # через find_active_by_title (AUDIT.md, A-4).
    markup = (
        build_task_quick_actions_keyboard(result.created_task)
        if result.created_task is not None
        else None
    )

    # Если inline-кнопок нет, место под клавиатуру свободно — освежаем
    # постоянное меню. Telegram не принимает inline- и reply-клавиатуру в
    # одном сообщении, поэтому только в этой ветке. Пользователь разницы
    # не видит (меню заменяется таким же), зато новые кнопки появляются
    # сами, без /start и /menu.
    if result.watchlist_item is not None and result.watchlist_item.poster_url:
        await _reply_with_media_card(update, result.watchlist_item, "Добавил в список")
        return

    await update.message.reply_text(
        result.text, reply_markup=markup or build_main_menu()
    )
