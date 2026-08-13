# Proactive Engagement Specification

---

# Цель

Бот сам инициирует диалог 3 раза в день (утро/день/вечер) и задаёт ОДИН
вопрос из ротации — про цели, привычки, проекты, предпочтения. Ответ
пользователя AI разбирает в структуру и **сразу сохраняет**
(привычка/цель/факт памяти) — без шага подтверждения. Ошибки правятся
обычным «удали …», как сейчас с задачами и привычками.

Это закрывает два разрыва, из-за которых бот раньше не мог наполнять себя
сам:

1. `ConversationEngine` не умел «задать вопрос → ждать ответ именно на
   него» — каждое сообщение разбиралось независимо (см.
   `specs/003-conversation.md`).
2. Через чат нельзя было создать Habit/Goal — `HabitService.create_habit`
   и `GoalService.create_goal` вызывались только из `/ui` и REST.

---

# Что НЕ входит

- Подтверждение перед записью в БД (сознательное решение — не MVP этой
  фичи, ошибки правятся вручную командой «удали …»).
- Учёт "тихих часов"/таймзоны пользователя сверх обычного локального
  времени сервера (как и у брифинга/рефлексии).
- Очередь из нескольких открытых вопросов — всегда только один, новый
  перезаписывает старый неотвеченный.

---

# Банк вопросов и выбор категории (`app/proactive/questions.py`, `service.py`)

Выбор категории — **детерминированный gap-detection**, без AI (ADR-004):
спрашиваем про то, чего у пользователя ещё нет. Проверяется по порядку,
первое совпадение побеждает:

| # | Условие | Категория |
|---|---|---|
| 1 | `GoalService.list_active_goals` пуст | `goal` |
| 2 | `HabitService.list_active_habits` пуст | `habit` |
| 3 | `MemoryService.list_entries(type=PROJECT)` пуст | `project` |
| 4 | `MemoryService.list_entries(type=PREFERENCE)` меньше 3 | `preference` |
| 5 | иначе | `reflect` (открытый вопрос "как дела") |

Внутри категории конкретная формулировка выбирается `random.choice` из
2-3 вариантов — чтобы не повторяться дословно.

Примерно в половине случаев (`PendingPromptService._with_musing`,
`_MUSING_CHANCE = 0.5`) к основному вопросу добавляется вторая строка —
экзистенциальный вопрос или интересный факт-вопрос
(`MUSING_QUESTIONS`), для разнообразия. Musing **не** сохраняется в
`pending_prompts` и не участвует в AI-разборе ответа — если пользователь
ответит именно на него, `extract_prompt_answer` справедливо сочтёт это
`unrelated` к основной категории (см. ниже), и сообщение уйдёт по
обычному пути.

---

# Состояние "открытый вопрос" (`app/proactive/models.py`, `repository.py`)

Таблица `pending_prompts` — **одна строка на пользователя** (unique
`telegram_user_id`), upsert вместо очереди:

```python
class PendingPrompt(Base):
    id: int
    telegram_user_id: int   # unique
    category: str           # goal | habit | project | preference | reflect
    question_text: str
    asked_at: datetime
```

Новый вопрос (от очередного запланированного слота) перезаписывает
предыдущий неотвеченный — история не копится, пользователь никогда не
видит "backlog" вопросов.

`PendingPromptRepository`: `get_for_user`, `upsert`, `clear_for_user`.
`PendingPromptService`: `pick_and_open` (выбрать категорию + записать),
`get_open`, `clear`.

---

# AI-разбор ответа (`app/proactive/ai_extract.py`)

`extract_prompt_answer(category, question_text, user_reply, ai_client)` —
паттерн идентичен `app/conversation/ai_fallback.py`: строгий JSON-промпт,
любая ошибка (сеть, невалидный JSON, неизвестное значение) → `None`,
никогда не роняет бота.

Категория даётся модели только как **подсказка контекста** — решение о
действии принимается по содержанию ответа (гибче: "reflect"-ответ может
на деле оказаться описанием цели).

```json
{"action": "create_goal|create_habit|save_memory|unrelated",
 "title": "строка или null",
 "target_date": "YYYY-MM-DD или null",
 "memory_type": "fact|preference|project или null",
 "content": "строка или null"}
```

`action=unrelated` — ответ явно не связан с вопросом (например, это
новая задача, а не ответ). Сигнал для `ConversationEngine`: обработать
текст как обычно, вопрос остаётся открытым.

`memory_type` ограничен `fact|preference|project` — `MemoryType.GOAL`
(легаси, текстовые цели) и `MemoryType.JOURNAL` (свой отдельный флоу,
`specs/005-*`) сюда не входят: структурные цели идут через
`GoalService.create_goal`, а не через Memory.

---

# Интеграция с ConversationEngine (`app/conversation/engine.py`)

`ConversationEngine` получает два новых **опциональных** параметра
(`goal_service`, `pending_prompt_service`, оба по умолчанию `None`) —
не ломает существующие вызовы без них.

`handle_message` — новая ветка ПЕРЕД существующим ai_fallback
(`ai_fallback.py`, разбор намерения целиком):

```
parsed = parse_intent(text)

если parsed.intent == ADD_TASK и pending_prompt_service и ai_client заданы:
    попробовать понять text как ответ на открытый вопрос
    если получилось → вернуть подтверждение, ЗАКОНЧИТЬ

если parsed.intent == ADD_TASK и title пуст и ai_client задан:
    (существующий fallback — разбор намерения целиком, без изменений)

dispatch(parsed)  # обычная обработка, в т.ч. создание новой задачи
```

Почему проверка вешается именно на `ADD_TASK`: это единственный intent,
означающий "текст не подошёл ни под одно ключевое слово" — то есть именно
тот случай, когда сообщение может оказаться свободным ответом на вопрос.
Явные команды («покажи задачи», «удали молоко», «привычка чтение» и
т.п.) всегда обрабатываются как обычно, даже если есть открытый вопрос —
пользователь не должен терять доступ к обычным командам из-за
проактивного вопроса.

`_try_answer_pending_prompt`:
- нет открытого вопроса → `None` (обычная обработка);
- `extract_prompt_answer` вернул `None`/`unrelated` → `None`, pending НЕ
  чистится (вопрос остаётся открытым; сообщение уйдёт в обычный ADD_TASK
  и, скорее всего, создаст настоящую новую задачу — это ожидаемо: так и
  должно быть, если пользователь просто написал что-то не в тему);
- `action` распознан, но обязательное поле пусто (например
  `create_goal` без `title`) → тоже `None`, pending НЕ чистится (не
  теряем вопрос из-за кривого ответа AI);
- успех → pending чистится, вызывается нужный сервис, возвращается
  короткое подтверждение («Добавил цель «X» 🎯», «Добавил привычку «Y»
  🔁», «Запомнил: Z 📝»).

---

# Планировщик (`app/telegram/jobs.py`, `app/telegram/bot.py`)

`send_proactive_prompt_job` — одно тело job, регистрируется 3 раза с
разными `name=` и временем (см. `app/core/config.py`):
`proactive_prompt_morning_hour/minute` (10:30 по умолчанию),
`_midday_hour/minute` (14:00), `_evening_hour/minute` (19:00).

Каждое — отдельное сообщение, НЕ встроено в утренний брифинг (08:00) или
вечернюю рефлексию (21:00) — чтобы не смешивать с уже существующим
парсингом `дневник: ...`-ответов в вечерней рефлексии
(`specs/005-*`/`flows/005-*`).

Если `owner_telegram_user_id` не задан или `get_ai_client(settings)`
вернул `None` (ключ OpenRouter не задан) — job тихо ничего не отправляет:
без AI отвечать на свободный текст всё равно нечем, задавать вопрос
бессмысленно.

---

# Definition of Done

- `app/proactive/service.py` — приоритет gap-detection покрыт тестами на
  каждую ветку (нет целей / нет привычек / нет проектов / <3
  предпочтений / всё заполнено);
- `app/proactive/repository.py` — upsert/get/clear покрыты
  интеграционным тестом на sqlite in-memory (см.
  `tests/tasks/test_reminders_repository.py` как образец);
- `app/proactive/ai_extract.py` — покрыт как `ai_fallback.py`: успешные
  `create_goal`/`create_habit`/`save_memory`, невалидный JSON, сетевая
  ошибка, `unrelated` — без единого реального сетевого вызова в тестах;
- `ConversationEngine` — покрыт: pending есть и распознан → нужный сервис
  вызван и pending очищен; `unrelated`/ошибка → pending НЕ очищен и
  создаётся обычная задача; `pending_prompt_service=None` — старое
  поведение не меняется (регрессия для уже существующих тестов).
