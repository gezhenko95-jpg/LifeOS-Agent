"""
Rule-based разбор намерения пользователя (без LLM, см. specs/003-conversation.md).
"""

import re
from typing import Optional

from app.conversation.amount_parser import extract_amount
from app.conversation.date_parser import extract_due_date, extract_recurrence
from app.conversation.intent import Intent, ParsedIntent

_HELP_KEYWORDS = ("/help", "помощь", "что ты умеешь")
# Все три — якорем на начало сообщения (см. _COMPLETE_KEYWORDS выше,
# AUDIT.md B-6): без якоря «нужна помощь с отчётом» ловилась как HELP,
# хотя это описание задачи, а не просьба о справке боту.
# Проверяются РАНЬШЕ общего _LIST_KEYWORDS (там голое "покажи" перехватило
# бы "покажи книги" как список задач) — см. живой баг с "список книг".
_LIST_WATCHLIST_KEYWORDS = (
    "список книг",
    "список фильмов",
    "список сериалов",
    "мои книги",
    "мои фильмы",
    "покажи книги",
    "покажи фильмы",
    "покажи полку",
    "что посмотреть",
    "что почитать",
    "полка",
)
_LIST_KEYWORDS = ("/tasks", "список задач", "мои задачи")
# "покажи" — командное слово, проверяется отдельно, ЯКОРЕМ на начало
# сообщения (см. _LIST_TASKS_START_KEYWORDS ниже, AUDIT.md B-6): голое
# "покажи" где угодно в фразе цепляло LIST_TASKS даже у «покажи
# презентацию клиенту» — там это часть задачи, а не команда боту.
_LIST_TASKS_START_KEYWORDS = ("покажи",)
# Вопрос про конкретный день («что на завтра») — не путать с ADD_TASK: дата
# в тексте есть, но это вопрос, а не новое дело. Без даты в тексте — просто
# LIST_TASKS (см. QUERY_BY_DATE-ветку в parse_intent).
_QUERY_BY_DATE_KEYWORDS = (
    "что на",
    "что у меня на",
    "что было на",
    "что запланировано",
    "какие задачи",
    "какие дела",
    "что я собирался",
    "что я планировал",
)
# Порядок не важен для распознавания intent (см. _contains_any), но для
# извлечения query (см. _extract_recall_query) вырезаются ВСЕ найденные
# фразы разом — иначе в "напомни, что я говорил про X" после удаления
# только "напомни" в query остаётся филлер "что я говорил про".
_RECALL_KEYWORDS = (
    "напомни",
    "вспомни",
    "что я говорил про",
    "что я говорил о",
    "что я говорил",
    "что ты знаешь про",
    "что ты знаешь о",
)
_RECALL_CONNECTOR_PATTERN = re.compile(r"^[,\s]*(?:про|о|об)\b", re.IGNORECASE)
# Фразы, которые ОДНОЗНАЧНО означают поиск по памяти — в отличие от
# голого «напомни», которое одинаково начинает и «напомни, что я говорил
# про отпуск», и «напомни в 19:00 позвонить маме» (см. _try_reminder_task).
_EXPLICIT_RECALL_PHRASES = (
    "что я говорил",
    "что ты знаешь",
    "вспомни",
)
_COMPLETE_KEYWORDS = ("выполнил", "сделал", "готово", "закрой")
_DELETE_KEYWORDS = ("удали", "убери", "отмени")
# Финансы (specs/017-finance.md) — якорем на начало сообщения, тот же
# приём и то же обоснование, что у COMPLETE/DELETE выше (AUDIT.md B-6):
# "потратил"/"получил" почти всегда открывают фразу о трате/доходе, а не
# упоминаются посреди другого предложения.
_EXPENSE_KEYWORDS = (
    "потратил",
    "потратила",
    "купил",
    "купила",
    "заплатил",
    "заплатила",
    "оплатил",
    "оплатила",
)
_INCOME_KEYWORDS = (
    "получил",
    "получила",
    "зарплата",
    "заработал",
    "заработала",
    "доход",
)
# Первое совпавшее слово внутри остатка текста (после вырезания триггера
# и суммы) определяет категорию — см. app/finance/models.py::CATEGORIES.
# Нет совпадения — категория "other", не отказ сохранить трату
# (specs/017-finance.md).
_FINANCE_CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("аренд", "rent"),  # аренда/аренду/арендную (не полное слово — падежи)
    ("ипотек", "rent"),
    ("коммунал", "utilities"),
    ("свет", "utilities"),
    ("вод", "utilities"),  # вода/воду — без окончания, тот же довод
    ("подписк", "subscriptions"),
    ("кредит", "credit"),
    ("рассрочк", "credit"),
    ("продукт", "groceries"),
    ("магазин", "groceries"),
    ("такси", "transport"),
    ("метро", "transport"),
    ("бензин", "transport"),
    ("транспорт", "transport"),
    ("кафе", "eating_out"),
    ("ресторан", "eating_out"),
    ("кофе", "eating_out"),
    ("аптек", "health"),
    ("врач", "health"),
    ("лекарств", "health"),
    ("кино", "entertainment"),
    ("подарок", "entertainment"),
    ("одежд", "shopping"),
)
# COMPLETE/DELETE — командные слова, срабатывающие ЯКОРЕМ на начало
# сообщения (см. AUDIT.md B-6: «команда почти всегда в начале») — без
# якоря «не могу решить, сделал ли я уже отчёт» превращалось бы в
# отметку задачи выполненной на слове «сделал» посреди фразы.
_HIGH_PRIORITY_KEYWORDS = ("важно", "срочно")
_LIST_HABITS_KEYWORDS = ("привычки",)
# С пробелом — чтобы отличать команду («привычка чтение») от разговорного
# упоминания слова «привычка» внутри обычной фразы.
_HABIT_DONE_KEYWORD = "привычка "
# Только в начале сообщения — иначе "купить дневник" стало бы записью
# в дневник вместо задачи.
_JOURNAL_KEYWORDS = ("дневник", "рефлексия", "итоги дня")
# Специфичные фразы — раньше общих ("посмотреть фильм" раньше просто
# "посмотреть"), иначе у "посмотреть фильм X" отрежется только
# "посмотреть", а "фильм" останется частью названия и media_type будет
# определён неверно (см. specs/010-media-inbox.md).
# Голые существительные ("книга X", "фильм X") — самая естественная форма
# команды, без глагола; проверяются позже глагольных фраз, чтобы не
# перехватить у них title раньше времени. Расплата — ложные срабатывания
# на случайное упоминание слова "книга"/"фильм" в обычной фразе (тот же
# компромисс, что у COMPLETE_TASK на "готово"/"сделал" — ADR-004).
_WATCHLIST_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("посмотреть сериал", "movie"),
    ("посмотреть фильм", "movie"),
    ("прочитать книгу", "book"),
    ("добавь фильм", "movie"),
    ("добавь сериал", "movie"),
    ("добавь книгу", "book"),
    ("хочу посмотреть", "movie"),
    ("хочу прочитать", "book"),
    ("фильм", "movie"),
    ("сериал", "movie"),
    ("книгу", "book"),
    ("книга", "book"),
    ("посмотреть", "other"),
    ("прочитать", "book"),
)


def parse_intent(text: str) -> ParsedIntent:
    stripped = text.strip()
    lowered = stripped.lower()

    if _starts_with_any(lowered, _HELP_KEYWORDS):
        return ParsedIntent(intent=Intent.HELP)

    if _contains_any(lowered, _LIST_WATCHLIST_KEYWORDS):
        return ParsedIntent(intent=Intent.LIST_WATCHLIST)

    if _contains_any(lowered, _LIST_KEYWORDS) or _starts_with_any(
        lowered, _LIST_TASKS_START_KEYWORDS
    ):
        return ParsedIntent(intent=Intent.LIST_TASKS)

    if _contains_any(lowered, _QUERY_BY_DATE_KEYWORDS):
        due_date, _ = extract_due_date(stripped)
        if due_date is not None:
            return ParsedIntent(intent=Intent.QUERY_TASKS_BY_DATE, due_date=due_date)
        return ParsedIntent(intent=Intent.LIST_TASKS)

    if _contains_any(lowered, _RECALL_KEYWORDS):
        reminder = _try_reminder_task(stripped, lowered)
        if reminder is not None:
            return reminder
        query = _extract_recall_query(stripped)
        return ParsedIntent(intent=Intent.RECALL, title=query or None)

    if _contains_any(lowered, _LIST_HABITS_KEYWORDS):
        return ParsedIntent(intent=Intent.LIST_HABITS)

    if _HABIT_DONE_KEYWORD in lowered:
        return ParsedIntent(
            intent=Intent.HABIT_DONE,
            title=_remove_keyword(stripped, "привычка"),
        )

    keyword = _starts_with_any(lowered, _COMPLETE_KEYWORDS)
    if keyword:
        return ParsedIntent(
            intent=Intent.COMPLETE_TASK, title=_remove_keyword(stripped, keyword)
        )

    keyword = _starts_with_any(lowered, _DELETE_KEYWORDS)
    if keyword:
        return ParsedIntent(
            intent=Intent.DELETE_TASK, title=_remove_keyword(stripped, keyword)
        )

    # Финансы — ДО watchlist, а не после: "потратил 500 на фильм в кино"
    # иначе перехватывался бы бесякорным триггером watchlist ("фильм" —
    # голое существительное, ищется где угодно в фразе, см.
    # _WATCHLIST_TRIGGERS) вместо того, чтобы стать тратой. Якорь на
    # начало сообщения ("потратил"/"купил"/...) — более сильный сигнал,
    # чем совпадение голого существительного где-то в середине (тот же
    # довод, что и у COMPLETE/DELETE, AUDIT.md B-6). Расплата: "купил
    # книгу для дочки" без суммы теперь тоже ADD_EXPENSE (переспросит
    # сумму), а не ADD_WATCHLIST_ITEM — это осознанно принято, "купил"
    # само по себе ближе к тратe, чем к "хочу прочитать".
    keyword = _starts_with_any(lowered, _INCOME_KEYWORDS)
    if keyword:
        without_keyword = _remove_keyword(stripped, keyword)
        amount, remaining = extract_amount(without_keyword)
        return ParsedIntent(
            intent=Intent.ADD_INCOME, amount=amount, title=remaining or None
        )

    keyword = _starts_with_any(lowered, _EXPENSE_KEYWORDS)
    if keyword:
        without_keyword = _remove_keyword(stripped, keyword)
        amount, remaining = extract_amount(without_keyword)
        category = _match_finance_category(remaining.lower())
        return ParsedIntent(
            intent=Intent.ADD_EXPENSE,
            amount=amount,
            finance_category=category,
            title=remaining or None,
        )

    journal_content = _extract_journal_entry(stripped, lowered)
    if journal_content is not None:
        return ParsedIntent(intent=Intent.JOURNAL_ENTRY, title=journal_content or None)

    watchlist_match = _match_watchlist_trigger(lowered)
    if watchlist_match:
        keyword, media_type = watchlist_match
        return ParsedIntent(
            intent=Intent.ADD_WATCHLIST_ITEM,
            title=_remove_keyword(stripped, keyword),
            media_type=media_type,
        )

    return parse_add_task(stripped)


def parse_add_task(text: str) -> ParsedIntent:
    """Разобрать текст как ADD_TASK напрямую, минуя весь остальной
    waterfall parse_intent (HELP/LIST/COMPLETE/DELETE/JOURNAL/...).

    Нужно для ответа на кнопку "➕ Добавить" (задача, см. handlers.py
    `_consume_pending_input`, TASK_ADD): пользователь уже явно нажал
    "добавить задачу", и его следующий текст обязан стать заголовком
    задачи (с датой/приоритетом/повтором внутри, как обычно), а не
    заново классифицироваться с нуля — иначе текст вроде "готово к
    отправке письмо" ловится _COMPLETE_KEYWORDS ("готово" первым
    словом) как COMPLETE_TASK, задача не находится, и вместо создания
    новой пользователь получает "не нашёл задачу" — ввод после кнопки
    молча теряется."""
    priority, without_priority = _extract_priority(text)
    recurrence, without_recurrence = extract_recurrence(without_priority)
    due_date, remaining = extract_due_date(without_recurrence)
    return ParsedIntent(
        intent=Intent.ADD_TASK,
        title=remaining.strip(),
        due_date=due_date,
        priority=priority,
        recurrence=recurrence,
    )


def _contains_any(lowered: str, keywords: tuple[str, ...]) -> Optional[str]:
    """Первое совпавшее ключевое слово ЦЕЛИКОМ (границы слова, не любая
    подстрока) — «отмени» матчит «отмени встречу», но не «отменить»
    (см. AUDIT.md, B-6). Не защищает от слова, оказавшегося не к месту
    ПОСЕРЕДИНЕ фразы (для этого — см. _starts_with_any ниже, для
    командных слов, которые почти всегда идут первыми).

    Лукахед/лукбехайнд вместо \\b: у `\\b` нет границы перед словом,
    которое начинается с небуквенного символа («/tasks» — `\\b/tasks\\b`
    не матчит вообще ничего, `/` сам не словообразующий, см. re.search
    с `\\b` вживую)."""
    for keyword in keywords:
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", lowered):
            return keyword
    return None


def _starts_with_any(lowered: str, keywords: tuple[str, ...]) -> Optional[str]:
    """Первое ключевое слово, с которого НАЧИНАЕТСЯ сообщение (после
    ведущих пробелов и вежливого филлера вроде «пожалуйста», см.
    _strip_filler — иначе «пожалуйста, покажи задачи» переставало бы
    матчить LIST_TASKS), границы слова соблюдены. Для командных слов
    («покажи», «удали», «выполнил» и т.п.) — команда боту почти всегда
    идёт в начале сообщения, а не посреди описания чего-то другого
    (см. AUDIT.md, B-6)."""
    stripped = _strip_filler(lowered.lstrip())
    for keyword in keywords:
        if re.match(rf"{re.escape(keyword)}\b", stripped):
            return keyword
    return None


def _remove_keyword(text: str, keyword: str) -> str:
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    cleaned = pattern.sub("", text, count=1)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # ", 21 и больше" — если после вырезанного слова в тексте была запятая/
    # тире («посмотреть, 21 и больше»), она иначе так и остаётся приклеенной
    # к началу названия (см. живой баг с watchlist-записью).
    return cleaned.strip(" ,:—-")


# Слова, которые обращены к боту, а не к делу: «напомни МНЕ позвонить» —
# «мне» в названии задачи не нужно («мне запустить стиралку» — реальный
# результат до этой правки). Вырезаются только в начале, после команды.
_FILLER_PATTERN = re.compile(
    r"^(?:мне|меня|мне\s+пожалуйста|пожалуйста|плиз|пж)\b[\s,]*", re.IGNORECASE
)


def _strip_filler(text: str) -> str:
    return _FILLER_PATTERN.sub("", text).strip(" ,:—-")


def _try_reminder_task(stripped: str, lowered: str) -> Optional[ParsedIntent]:
    """«напомни в 19:00 позвонить маме» — это ЗАДАЧА, а не поиск в памяти.

    Слово «напомни» одинаково начинает и просьбу вспомнить («напомни, что
    я говорил про отпуск»), и просьбу напомнить о деле в будущем. Раньше
    оно всегда означало RECALL, поэтому любое напоминание со временем
    молча уходило в поиск по памяти и не создавало вообще ничего —
    реальная жалоба владельца (см. AUDIT.md).

    Различаем по двум признакам:
    1. Явные фразы поиска («что я говорил про…») — всегда RECALL, даже
       если в тексте попалось что-то похожее на время.
    2. Иначе: есть время/дата в тексте → это напоминание о деле; нет →
       RECALL, как раньше.

    None означает «это не напоминание, разбирай как RECALL».
    """
    if _contains_any(lowered, _EXPLICIT_RECALL_PHRASES):
        return None

    without_keyword = _strip_filler(_remove_keyword(stripped, "напомни"))
    if not without_keyword:
        return None

    priority, without_priority = _extract_priority(without_keyword)
    recurrence, without_recurrence = extract_recurrence(without_priority)
    due_date, remaining = extract_due_date(without_recurrence)

    title = remaining.strip(" ,:—-")
    if due_date is None or not title:
        return None

    return ParsedIntent(
        intent=Intent.ADD_TASK,
        title=title,
        due_date=due_date,
        priority=priority,
        recurrence=recurrence,
    )


def _extract_recall_query(stripped: str) -> str:
    """Вырезать все триггерные фразы (не только первую совпавшую — в
    "напомни, что я говорил про X" их две), затем висящий предлог
    "про/о/об" в начале и лишние пробелы/пунктуацию."""
    text = stripped
    for phrase in _RECALL_KEYWORDS:
        text = re.sub(re.escape(phrase), "", text, count=1, flags=re.IGNORECASE)
    text = _RECALL_CONNECTOR_PATTERN.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,:")


def _extract_journal_entry(stripped: str, lowered: str) -> Optional[str]:
    """Вернуть текст записи, если сообщение начинается с триггерного слова.

    None — триггерного слова нет вообще (не JOURNAL_ENTRY);
    "" — триггерное слово есть, но текста после него нет.
    """
    for keyword in _JOURNAL_KEYWORDS:
        if lowered.startswith(keyword):
            return stripped[len(keyword) :].lstrip(":").strip()
    return None


def _match_watchlist_trigger(lowered: str) -> Optional[tuple[str, str]]:
    for phrase, media_type in _WATCHLIST_TRIGGERS:
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered):
            return phrase, media_type
    return None


def _match_finance_category(lowered_remaining: str) -> str:
    """Первое совпавшее слово в остатке текста (без триггера/суммы) →
    категория; нет совпадения → "other" (см. app/finance/models.py)."""
    for keyword, category in _FINANCE_CATEGORY_KEYWORDS:
        if keyword in lowered_remaining:
            return category
    return "other"


def _extract_priority(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for keyword in _HIGH_PRIORITY_KEYWORDS:
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", lowered):
            return "high", _remove_keyword(text, keyword)
    return "normal", text
