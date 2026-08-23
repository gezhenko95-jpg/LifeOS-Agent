from app.conversation.intent import Intent
from app.conversation.parser import (
    parse_finance_expense,
    parse_finance_income,
    parse_intent,
)


def test_add_task_with_date():
    result = parse_intent("Завтра купить молоко")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "купить молоко"
    assert result.due_date is not None


def test_add_task_without_date():
    result = parse_intent("Купить молоко")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "Купить молоко"
    assert result.due_date is None
    assert result.priority == "normal"
    assert result.recurrence is None


def test_add_task_recurring_weekday():
    result = parse_intent("Каждый понедельник оплатить интернет")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "оплатить интернет"
    assert result.recurrence == "weekly"
    assert result.due_date is not None
    assert result.due_date.weekday() == 0


def test_add_task_recurring_daily_without_explicit_date():
    result = parse_intent("Каждый день пить воду")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "пить воду"
    assert result.recurrence == "daily"
    assert result.due_date is None  # дата подставляется в TaskService


def test_add_task_recurring_monthly():
    result = parse_intent("Каждый месяц оплатить аренду")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "оплатить аренду"
    assert result.recurrence == "monthly"


def test_add_task_recurring_with_priority():
    result = parse_intent("Важно каждый день пить таблетки")

    assert result.intent is Intent.ADD_TASK
    assert result.title == "пить таблетки"
    assert result.recurrence == "daily"
    assert result.priority == "high"


def test_add_task_with_high_priority_keyword():
    result = parse_intent("Важно позвонить в банк завтра")

    assert result.intent is Intent.ADD_TASK
    assert result.priority == "high"
    assert result.title == "позвонить в банк"
    assert result.due_date is not None


def test_add_task_with_urgent_keyword():
    result = parse_intent("Срочно закрыть отчет")

    assert result.intent is Intent.ADD_TASK
    assert result.priority == "high"
    assert result.title == "закрыть отчет"


def test_list_tasks_ru():
    result = parse_intent("Покажи задачи")

    assert result.intent is Intent.LIST_TASKS


def test_list_tasks_my_tasks_phrase():
    result = parse_intent("Мои задачи на сегодня")

    assert result.intent is Intent.LIST_TASKS


def test_list_tasks_command():
    result = parse_intent("/tasks")

    assert result.intent is Intent.LIST_TASKS


def test_complete_task():
    result = parse_intent("Выполнил купить молоко")

    assert result.intent is Intent.COMPLETE_TASK
    assert result.title == "купить молоко"


def test_complete_task_alternate_keyword():
    result = parse_intent("Готово, молоко купил")

    assert result.intent is Intent.COMPLETE_TASK


def test_delete_task():
    result = parse_intent("Удали молоко")

    assert result.intent is Intent.DELETE_TASK
    assert result.title == "молоко"


def test_help_command():
    result = parse_intent("/help")

    assert result.intent is Intent.HELP


def test_help_phrase():
    result = parse_intent("Что ты умеешь?")

    assert result.intent is Intent.HELP


def test_list_habits():
    result = parse_intent("Привычки")

    assert result.intent is Intent.LIST_HABITS


def test_habit_done():
    result = parse_intent("Привычка чтение")

    assert result.intent is Intent.HABIT_DONE
    assert result.title == "чтение"


def test_habit_done_is_checked_before_complete_task():
    # "сделал" — это COMPLETE_KEYWORD, но фраза с "привычка" должна
    # распознаваться как HABIT_DONE, а не COMPLETE_TASK
    result = parse_intent("Привычка сделал зарядку")

    assert result.intent is Intent.HABIT_DONE


def test_journal_entry_with_colon():
    result = parse_intent("Дневник: сегодня был продуктивный день")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title == "сегодня был продуктивный день"


def test_journal_entry_alternate_keyword():
    result = parse_intent("Рефлексия: закончил важный проект")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title == "закончил важный проект"


def test_journal_entry_two_word_keyword():
    result = parse_intent("Итоги дня: всё получилось")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title == "всё получилось"


def test_journal_entry_empty_content():
    result = parse_intent("Дневник")

    assert result.intent is Intent.JOURNAL_ENTRY
    assert result.title is None


def test_journal_keyword_in_the_middle_is_not_journal_entry():
    # "дневник" не в начале сообщения — это обычная задача, а не рефлексия
    result = parse_intent("Купить дневник для дочери")

    assert result.intent is Intent.ADD_TASK


def test_query_tasks_by_date_tomorrow():
    result = parse_intent("Что на завтра?")

    assert result.intent is Intent.QUERY_TASKS_BY_DATE
    assert result.due_date is not None


def test_query_tasks_by_date_literal_mvp_phrase():
    # Буквальный acceptance-тест из MVP.md
    result = parse_intent("Что я собирался сделать завтра?")

    assert result.intent is Intent.QUERY_TASKS_BY_DATE
    assert result.due_date is not None


def test_query_tasks_by_date_weekday():
    # date_parser понимает предлог "в"/"во" перед днём недели (см.
    # test_date_parser.py) — не "на", поэтому здесь именно "в пятницу"
    result = parse_intent("Какие задачи в пятницу")

    assert result.intent is Intent.QUERY_TASKS_BY_DATE
    assert result.due_date is not None


def test_query_by_date_keyword_without_date_falls_back_to_list_tasks():
    result = parse_intent("Какие задачи вообще у меня есть")

    assert result.intent is Intent.LIST_TASKS


def test_recall_with_query():
    # "напомни" И "что я говорил про" — оба триггерные фразы, оба должны
    # быть вырезаны из query, не только первая найденная
    result = parse_intent("Напомни, что я говорил про отпуск")

    assert result.intent is Intent.RECALL
    assert result.title == "отпуск"


def test_recall_alternate_keyword():
    result = parse_intent("Вспомни про проект LifeOS")

    assert result.intent is Intent.RECALL
    assert result.title == "проект LifeOS"


def test_recall_no_trigger_prefix():
    result = parse_intent("Что я говорил про маму")

    assert result.intent is Intent.RECALL
    assert result.title == "маму"


def test_recall_without_query_is_still_recall():
    result = parse_intent("Вспомни")

    assert result.intent is Intent.RECALL
    assert result.title is None


# --- ADD_WATCHLIST_ITEM ------------------------------------------------


def test_watchlist_movie_specific_phrase():
    result = parse_intent("посмотреть фильм Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "movie"
    assert result.title == "Дюна"


def test_watchlist_series_phrase():
    result = parse_intent("посмотреть сериал Оффер")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "movie"
    assert result.title == "Оффер"


def test_watchlist_book_specific_phrase():
    result = parse_intent("прочитать книгу Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "book"
    assert result.title == "Дюна"


def test_watchlist_generic_want_phrase():
    result = parse_intent("хочу прочитать Мастер и Маргарита")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "book"
    assert result.title == "Мастер и Маргарита"


def test_watchlist_bare_verb_is_other():
    result = parse_intent("посмотреть Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "other"
    assert result.title == "Дюна"


def test_watchlist_strips_leftover_comma_after_keyword():
    # Живой баг: "посмотреть, 21 и больше" оставляло ", 21 и больше" —
    # запятая приклеивалась к началу названия.
    result = parse_intent("посмотреть, 21 и больше")

    assert result.title == "21 и больше"


# --- LIST_WATCHLIST -----------------------------------------------------


def test_list_watchlist_list_books_phrase():
    result = parse_intent("список книг")

    assert result.intent is Intent.LIST_WATCHLIST


def test_list_watchlist_list_movies_phrase():
    result = parse_intent("список фильмов")

    assert result.intent is Intent.LIST_WATCHLIST


def test_list_watchlist_shows_books_wins_over_generic_show():
    # Живой баг: "покажи книги" уходило в LIST_TASKS из-за общего "покажи".
    result = parse_intent("покажи книги")

    assert result.intent is Intent.LIST_WATCHLIST


def test_list_watchlist_bare_polka_keyword():
    result = parse_intent("полка")

    assert result.intent is Intent.LIST_WATCHLIST


def test_list_watchlist_what_to_watch_does_not_add_item():
    # "что посмотреть" не должно уйти в ADD_WATCHLIST_ITEM с title="что".
    result = parse_intent("что посмотреть")

    assert result.intent is Intent.LIST_WATCHLIST


def test_generic_show_still_lists_tasks():
    result = parse_intent("покажи задачи")

    assert result.intent is Intent.LIST_TASKS


def test_watchlist_empty_title():
    result = parse_intent("посмотреть фильм")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.title == ""


def test_watchlist_specific_phrase_wins_over_generic():
    # "посмотреть фильм X" не должно отрезать только "посмотреть",
    # оставляя "фильм X" в названии.
    result = parse_intent("Хочу посмотреть фильм Дюна")

    assert result.media_type == "movie"
    assert "фильм" not in result.title


def test_watchlist_bare_reading_verb_is_book():
    result = parse_intent("прочитать Дюну")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "book"
    assert result.title == "Дюну"


def test_watchlist_bare_noun_book():
    result = parse_intent("книга Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "book"
    assert result.title == "Дюна"


def test_watchlist_add_verb_book():
    result = parse_intent("добавь книгу Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "book"
    assert result.title == "Дюна"


def test_watchlist_bare_noun_movie():
    result = parse_intent("фильм Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "movie"
    assert result.title == "Дюна"


def test_watchlist_add_verb_movie():
    result = parse_intent("добавь фильм Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "movie"
    assert result.title == "Дюна"


def test_watchlist_bare_noun_series():
    result = parse_intent("сериал Оффер")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM
    assert result.media_type == "movie"
    assert result.title == "Оффер"


# --- «напомни» = задача, а не только поиск по памяти (жалоба владельца) ---


def test_remind_with_time_creates_task_not_recall():
    """Раньше ЛЮБОЕ «напомни» уходило в поиск по памяти, и напоминание
    со временем не создавало вообще ничего."""
    parsed = parse_intent("напомни в 19:00 позвонить маме")

    assert parsed.intent is Intent.ADD_TASK
    assert parsed.title == "позвонить маме"
    assert parsed.due_date.hour == 19
    assert parsed.due_date.minute == 0


def test_remind_with_hour_without_colon():
    """«в 19 00» пишут не реже, чем «в 19:00»."""
    parsed = parse_intent("напомни в 19 00 позвонить маме")

    assert parsed.intent is Intent.ADD_TASK
    assert parsed.title == "позвонить маме"
    assert (parsed.due_date.hour, parsed.due_date.minute) == (19, 0)


def test_remind_with_bare_hour():
    parsed = parse_intent("напомни в 19 позвонить маме")

    assert parsed.intent is Intent.ADD_TASK
    assert parsed.title == "позвонить маме"
    assert (parsed.due_date.hour, parsed.due_date.minute) == (19, 0)


def test_remind_with_word_number():
    parsed = parse_intent("напомни через пару часов позвонить маме")

    assert parsed.intent is Intent.ADD_TASK
    assert parsed.title == "позвонить маме"
    assert parsed.due_date is not None


def test_remind_with_relative_date():
    parsed = parse_intent("напомни завтра оплатить интернет")

    assert parsed.intent is Intent.ADD_TASK
    assert parsed.title == "оплатить интернет"


def test_explicit_recall_phrase_stays_recall():
    """«что я говорил» — однозначный поиск по памяти, время внутри фразы
    не должно превращать его в задачу."""
    parsed = parse_intent("напомни, что я говорил про встречу в 19:00")

    assert parsed.intent is Intent.RECALL


def test_remind_without_time_stays_recall():
    """Без времени «напомни про X» по-прежнему поиск — поведение, на
    которое пользователь уже привык."""
    parsed = parse_intent("напомни про отпуск")

    assert parsed.intent is Intent.RECALL
    assert parsed.title == "отпуск"


def test_vspomni_stays_recall():
    parsed = parse_intent("вспомни про Сохрани лес")

    assert parsed.intent is Intent.RECALL
    assert parsed.title == "Сохрани лес"


# --- B-6: границы слов и якорь на начало сообщения для командных слов
# (см. AUDIT.md, B-6) ---
#
# Из четырёх примеров AUDIT.md реально фиксится якорем только первый —
# в остальных трёх триггерное слово само оказывается ПЕРВЫМ словом
# фразы («сделал заметку…», «покажи презентацию…», «отдать книгу…»),
# и якорь на начало сообщения его не отсекает. Это подтверждённый
# осознанный компромисс ADR-004 (см. комментарий у _WATCHLIST_TRIGGERS
# в parser.py) — не переписываем на семантический разбор ради него.


def test_help_word_mid_sentence_no_longer_triggers_help():
    """«нужна помощь с отчётом» раньше ловилась как HELP по одному
    вхождению слова «помощь» где угодно во фразе (AUDIT.md, B-6)."""
    parsed = parse_intent("нужна помощь с отчётом")

    assert parsed.intent is not Intent.HELP
    assert parsed.intent is Intent.ADD_TASK


def test_complete_word_mid_sentence_no_longer_triggers_complete():
    """«сделал» посреди фразы (не первым словом) больше не отмечает
    случайную задачу выполненной."""
    parsed = parse_intent("не могу решить, сделал ли я уже отчёт")

    assert parsed.intent is not Intent.COMPLETE_TASK


def test_list_tasks_word_mid_sentence_no_longer_triggers_list():
    """«покажи» посреди фразы, не первым словом — не список задач."""
    parsed = parse_intent("а ты можешь мне покажи как это работает")

    assert parsed.intent is not Intent.LIST_TASKS


def test_delete_word_substring_inside_another_word_does_not_match():
    """«отмени» — подстрока «отменить», но не то же самое слово (границы
    слова, см. AUDIT.md, B-6)."""
    parsed = parse_intent("нужно отменить встречу с клиентом завтра")

    assert parsed.intent is not Intent.DELETE_TASK


def test_priority_word_substring_inside_another_word_does_not_match():
    """«важно» — подстрока «важность», границы слова не дают ложного
    приоритета."""
    parsed = parse_intent("обсудить важность проекта")

    assert parsed.priority == "normal"


def test_polite_prefix_before_command_word_still_works():
    """Якорь на начало сообщения не должен ломать вежливые формы —
    филлер («пожалуйста») уже снимается для команд-напоминаний
    (_strip_filler), теперь так же и для якоримых командных слов."""
    parsed = parse_intent("пожалуйста, покажи задачи")

    assert parsed.intent is Intent.LIST_TASKS


def test_command_word_at_start_still_works():
    """Регрессия: якорь не должен ломать штатный случай — команда,
    стоящая в начале, как и раньше."""
    assert parse_intent("Удали молоко").intent is Intent.DELETE_TASK
    assert parse_intent("Выполнил молоко").intent is Intent.COMPLETE_TASK
    assert parse_intent("Покажи задачи").intent is Intent.LIST_TASKS


# --- Финансы (specs/017-finance.md) ---


def test_add_expense_basic():
    result = parse_intent("потратил 1200 на продукты")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.amount == 1200
    assert result.finance_category == "groceries"


def test_add_expense_alternate_keyword():
    result = parse_intent("купил 500 на такси")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.amount == 500
    assert result.finance_category == "transport"


def test_add_expense_unknown_category_falls_back_to_other():
    result = parse_intent("потратил 300 на непонятно что")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.finance_category == "other"


def test_add_expense_without_amount():
    result = parse_intent("потратил на продукты")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.amount is None


def test_add_expense_mandatory_category():
    result = parse_intent("оплатил аренду 30000")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.finance_category == "rent"
    assert result.amount == 30000


def test_add_income_basic():
    result = parse_intent("получил зарплату 80000")

    assert result.intent is Intent.ADD_INCOME
    assert result.amount == 80000


def test_add_income_alternate_keyword():
    result = parse_intent("доход 5000")

    assert result.intent is Intent.ADD_INCOME
    assert result.amount == 5000


def test_expense_keyword_takes_priority_over_bare_watchlist_noun():
    """Осознанный приоритет (см. parser.py, комментарий перед финансовым
    блоком): "потратил ... фильм" — трата, а не запись в "посмотреть
    позже", хотя "фильм" — голый триггер watchlist."""
    result = parse_intent("потратил 500 на фильм в кино")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.finance_category == "entertainment"


def test_watchlist_trigger_without_finance_keyword_still_works():
    """Регрессия: обычное "хочу посмотреть фильм X" не должно было
    начать классифицироваться как трата — оно не начинается с триггера
    финансов вообще."""
    result = parse_intent("хочу посмотреть фильм Дюна")

    assert result.intent is Intent.ADD_WATCHLIST_ITEM


def test_parse_finance_expense_from_button_no_trigger_word():
    """Ответ на кнопку "➕ Трата" — без слова "потратил"."""
    result = parse_finance_expense("500 на такси")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.amount == 500
    assert result.finance_category == "transport"


def test_parse_finance_expense_no_amount():
    result = parse_finance_expense("на продукты")

    assert result.intent is Intent.ADD_EXPENSE
    assert result.amount is None


def test_parse_finance_income_from_button_no_trigger_word():
    result = parse_finance_income("80000")

    assert result.intent is Intent.ADD_INCOME
    assert result.amount == 80000


# --- Intent.CHAT (specs/020-butler-personas.md) -----------------------


def test_question_mark_is_chat():
    result = parse_intent("Как думаешь, стоит ли мне сменить работу?")

    assert result.intent is Intent.CHAT
    assert result.title == "Как думаешь, стоит ли мне сменить работу?"


def test_greeting_is_chat():
    result = parse_intent("Привет! Как сам?")

    assert result.intent is Intent.CHAT


def test_thanks_is_chat():
    result = parse_intent("Спасибо, очень помогло")

    assert result.intent is Intent.CHAT


def test_plain_task_title_is_not_chat():
    result = parse_intent("Купить молоко")

    assert result.intent is Intent.ADD_TASK


def test_more_specific_intent_wins_over_chat_even_with_question_mark():
    """COMPLETE_TASK проверяется раньше CHAT в waterfall — command-слово
    в начале сильнее вопросительного знака в конце."""
    result = parse_intent("выполнил отчёт?")

    assert result.intent is Intent.COMPLETE_TASK
