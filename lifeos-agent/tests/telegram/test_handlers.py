from app.telegram.handlers import extract_created_task_title


def test_extracts_title_from_normal_task_reply():
    reply = "Добавил задачу: «Купить молоко»"

    assert extract_created_task_title(reply) == "Купить молоко"


def test_extracts_title_with_high_priority_prefix():
    reply = "❗ Добавил задачу: «Позвонить в банк»"

    assert extract_created_task_title(reply) == "Позвонить в банк"


def test_extracts_title_when_date_and_recurrence_suffix_present():
    reply = "Добавил задачу: «Оплатить интернет» на 20.08.2026 🔁"

    assert extract_created_task_title(reply) == "Оплатить интернет"


def test_returns_none_for_unrelated_reply():
    assert extract_created_task_title("Добавил цель «Марафон» 🎯") is None
    assert extract_created_task_title("Готово: «X» отмечена выполненной.") is None
    assert extract_created_task_title("Не понял, какую задачу добавить.") is None
