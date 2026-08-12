from app.telegram.callbacks import parse_callback


def test_parse_task_complete():
    assert parse_callback("t|c|5") == ("t", "c", "5")


def test_parse_task_delete():
    assert parse_callback("t|d|42") == ("t", "d", "42")


def test_parse_habit_action():
    assert parse_callback("h|x|7") == ("h", "x", "7")


def test_parse_goal_action():
    assert parse_callback("g|u|1") == ("g", "u", "1")


def test_parse_goal_noop_has_no_id():
    assert parse_callback("g|noop") == ("g", "noop", "")
