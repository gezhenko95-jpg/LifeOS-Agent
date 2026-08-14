from app.memory.embeddings import cosine_similarity, rank_by_similarity
from app.memory.models import MemoryEntry


def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_opposite_vectors():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_cosine_similarity_empty_vector_returns_zero():
    assert cosine_similarity([], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], []) == 0.0


def test_cosine_similarity_mismatched_dimensions_returns_zero():
    assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_similarity_zero_norm_returns_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


def _entry(id_: int, embedding: list[float] | None) -> MemoryEntry:
    return MemoryEntry(
        id=id_,
        telegram_user_id=1,
        type="fact",
        content=f"entry-{id_}",
        embedding=embedding,
    )


def test_rank_by_similarity_orders_descending():
    entries = [
        _entry(1, [0.0, 1.0]),  # ортогонален query -> 0.0
        _entry(2, [1.0, 0.0]),  # совпадает с query -> 1.0
        _entry(3, [0.7, 0.7]),  # частично похож
    ]

    result = rank_by_similarity([1.0, 0.0], entries, limit=5)

    assert [entry.id for entry in result] == [2, 3, 1]


def test_rank_by_similarity_skips_entries_without_embedding():
    entries = [_entry(1, None), _entry(2, [1.0, 0.0])]

    result = rank_by_similarity([1.0, 0.0], entries)

    assert [entry.id for entry in result] == [2]


def test_rank_by_similarity_respects_limit():
    entries = [_entry(i, [1.0, 0.0]) for i in range(1, 6)]

    result = rank_by_similarity([1.0, 0.0], entries, limit=2)

    assert len(result) == 2


def test_rank_by_similarity_empty_list_returns_empty():
    assert rank_by_similarity([1.0, 0.0], []) == []
