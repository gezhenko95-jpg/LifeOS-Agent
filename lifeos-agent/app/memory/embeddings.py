"""
Чистые функции для семантического поиска по памяти (см.
specs/011-semantic-memory-search.md). Без БД — на входе векторы/записи,
на выходе число/отсортированный список. Тестируются без моков.
"""

import math

from app.memory.models import MemoryEntry


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """0.0 — нет сходства/некорректный вход (пустой вектор, разная
    размерность, нулевая норма) — не роняем вызывающий код на кривых
    данных, просто считаем несравнимое несовпадающим."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def rank_by_similarity(
    query_embedding: list[float], entries: list[MemoryEntry], limit: int = 5
) -> list[MemoryEntry]:
    """Топ-N записей по убыванию косинусного сходства с query_embedding.
    Порога на минимальное сходство нет (см. specs/011-semantic-memory-
    search.md, "Что НЕ входит") — вызывающий код сам решает, как
    подать результат пользователю (см. ConversationEngine._recall)."""
    scored = [
        (cosine_similarity(query_embedding, entry.embedding), entry)
        for entry in entries
        if entry.embedding
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]
