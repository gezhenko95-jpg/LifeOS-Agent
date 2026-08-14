# Semantic Memory Search Specification

---

# Цель

Сейчас `MemoryService.search` ищет по буквальному вхождению подстроки в
`content` (см. `app/memory/service.py`) — не найдёт запись про «смену
работы», если пользователь спросит «что я думал про увольнение». Цель —
добавить смысловой поиск через embeddings как fallback, когда буквальный
поиск ничего не нашёл, не трогая сам буквальный поиск (он быстрый,
бесплатный и точный — не нужно его заменять).

---

# Данные

OpenRouter поддерживает `/embeddings` тем же ключом, что уже используется
для чата (проверено живым вызовом) — новый провайдер не нужен, только
новая настройка модели.

`MemoryEntry.embedding` — новая колонка (`JSON`, nullable, миграция
`011_add_embedding_to_memory_entries.py`). `JSON`, не `pgvector`
(ADR-004: pgvector = смена образа Postgres + новый тип данных ради
проекта на несколько сотен записей — несоразмерная сложность). Косинусное
сходство считается в Python на уже выбранных из БД записях — датасет
одного пользователя, это быстро и просто.

---

# Заполнение embedding (фоновая job, не на каждую запись синхронно)

Эмбеддинг НЕ считается синхронно в момент `MemoryService.save` — `save`
вызывается из многих мест (`ConversationEngine`, `app/api/memory.py`,
`PendingPromptService`), заводить туда AI-зависимость ради одной фичи не
стоит (ADR-005). Вместо этого — новая `app/telegram/jobs.py::
embed_pending_memories_job`, `run_repeating` каждые
`memory_embedding_interval_seconds` (300 по умолчанию): берёт до
`memory_embedding_batch_size` (20) записей с `embedding IS NULL`,
эмбеддит по одной через `MemoryService.backfill_embeddings`. Ошибка AI на
одной записи не прерывает батч — пробуем на следующий заход. Новая
запись становится доступна семантическому поиску в течение ~5 минут, не
мгновенно — приемлемо для дневника/памяти.

---

# Поиск

`MemoryService.semantic_search(telegram_user_id, query, ai_client,
type=None, limit=5) -> list[MemoryEntry]`: тянет записи пользователя С
embedding (`MemoryRepository.list_with_embeddings`), эмбеддит `query`,
ранжирует по косинусному сходству (`app/memory/embeddings.py::
cosine_similarity`/`rank_by_similarity` — чистые функции, без БД).
Порога на минимальное сходство нет (см. "Что НЕ входит") — просто топ-N.

`ConversationEngine._recall`: сначала буквальный `MemoryService.search`
как сейчас; если пусто И есть `ai_client` — пробуем `semantic_search`. У
результата другая вводная фраза ("Точных совпадений с «X» нет, но вот
похожее:") — чтобы не выдавать смысловое совпадение за точное.

---

# Что НЕ входит

- Порог минимального сходства (отсекать совсем нерелевантное) — сложно
  откалибровать без реальных данных пользователя; вместо этого честная
  формулировка "вот похожее" снимает риск ложной уверенности.
- Переэмбеддинг при редактировании записи (`MemoryService.update`) —
  редактирование контента журнала случается редко, не в этой версии.
- Векторный индекс/pgvector — see выше, датасет слишком мал, чтобы это
  окупилось.

---

# Definition of Done

- `cosine_similarity`/`rank_by_similarity` — чистые тесты (ортогональные
  векторы, идентичные, пустой список, разная размерность);
- `AIClient.embed` — мок HTTP, успех/ошибка/битый ответ (по образцу
  `complete`);
- `MemoryRepository.list_with_embeddings`/`list_missing_embeddings` —
  интеграционные тесты на SQLite;
- `MemoryService.semantic_search`/`backfill_embeddings` — моки;
- `ConversationEngine._recall` — буквальный поиск найден → semantic не
  вызывается; буквальный пуст + AI есть → semantic; буквальный пуст +
  AI нет → "ничего не нашёл";
- живая проверка: реальный embed-вызов к OpenRouter, backfill на
  реальных записях владельца, `напомни про X` со смысловым, не буквальным
  совпадением.
