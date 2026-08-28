"""
app/telegram/jobs.py — джобы планировщика. `AsyncSessionLocal` мокается
целиком (тот же приём, что `no_db` в test_menu_navigation.py), сервисы
подменяются на AsyncMock с готовыми возвратами — реальная БД не нужна.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.assistant.personas import Persona
from app.digest.models import Digest
from app.habits.models import Habit
from app.telegram import jobs


@pytest.fixture
def no_db(monkeypatch) -> None:
    monkeypatch.setattr(jobs, "AsyncSessionLocal", MagicMock())


def _context() -> MagicMock:
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


def _owner_settings() -> MagicMock:
    return MagicMock(owner_telegram_user_id=1)


async def test_send_digests_job_attaches_save_button(no_db, monkeypatch):
    """specs/016-engagement-hooks.md: под каждым дайджестом — кнопка
    "⭐ Сохранить" с id темы в callback_data (см. app/telegram/callbacks.py
    ::_handle_digest_action, action "f")."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    digest = Digest(id=7, telegram_user_id=1, name="ESG", auto_frequency="daily")
    service = AsyncMock()
    service.list_digests.return_value = [digest]
    service.build_digest_text.return_value = "Свежие новости ESG."
    monkeypatch.setattr(jobs, "build_digest_service", lambda session: service)

    context = _context()
    await jobs.send_digests_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Свежие новости ESG."
    markup = kwargs["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["d|f|7"]


async def test_send_digests_job_skips_when_no_new_posts(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    digest = Digest(id=7, telegram_user_id=1, name="ESG", auto_frequency="daily")
    service = AsyncMock()
    service.list_digests.return_value = [digest]
    service.build_digest_text.return_value = None
    monkeypatch.setattr(jobs, "build_digest_service", lambda session: service)

    context = _context()
    await jobs.send_digests_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_send_digests_job_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_digests_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_morning_briefing_appends_reflection_question(no_db, monkeypatch):
    """specs/016-engagement-hooks.md: утренняя рефлексия (раньше —
    отдельная джоба в отдельном слоте) теперь дописывается снизу к
    брифингу — один push вместо двух."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    monkeypatch.setattr(
        jobs, "build_morning_briefing", AsyncMock(return_value="Доброе утро!")
    )
    monkeypatch.setattr(jobs, "_try_build_chart", AsyncMock(return_value=None))
    prompt_service = AsyncMock()
    prompt_service.pick_morning_reflection.return_value = "Что тебе снилось?"
    monkeypatch.setattr(jobs, "build_prompt_service", lambda session: prompt_service)
    monkeypatch.setattr(jobs, "build_assistant_service", lambda session: AsyncMock())

    context = _context()
    await jobs.send_morning_briefing_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Доброе утро!\n\nЧто тебе снилось?"
    prompt_service.pick_morning_reflection.assert_awaited_once_with(1, allow_gap=False)


async def test_morning_briefing_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_morning_briefing_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_send_finance_report_job_sends_report(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    monkeypatch.setattr(
        jobs, "build_finance_report", AsyncMock(return_value="Финансы за август")
    )
    monkeypatch.setattr(jobs, "build_finance_service", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_assistant_service", lambda session: AsyncMock())

    context = _context()
    await jobs.send_finance_report_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Финансы за август"


async def test_send_finance_report_job_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_finance_report_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_midday_checkin_includes_habit_list_text(no_db, monkeypatch):
    """Раньше текст со списком привычек (build_habits_message) выбрасывался
    (`_, markup = ...`) — уходил только общий вопрос + кнопки с голыми
    номерами "1"/"2" без подписей, на что они отвечают (баг с реального
    использования). Список должен быть виден в самом сообщении."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    habit = Habit(id=1, telegram_user_id=1, title="Чтение")
    service = AsyncMock()
    service.list_active_habits.return_value = [habit]
    service.get_streaks_bulk.return_value = {1: 3}
    monkeypatch.setattr(jobs, "HabitService", lambda repository: service)
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    monkeypatch.setattr(jobs, "PendingPromptRepository", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())

    context = _context()
    await jobs.send_midday_checkin_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "Чтение" in kwargs["text"]
    assert "Как проходит твой день" in kwargs["text"]
    assert kwargs["parse_mode"] is not None
    callbacks = [
        b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row
    ]
    assert "h|d|1" in callbacks


async def test_midday_checkin_no_habits_sends_plain_question(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    service = AsyncMock()
    service.list_active_habits.return_value = []
    monkeypatch.setattr(jobs, "HabitService", lambda repository: service)
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    monkeypatch.setattr(jobs, "PendingPromptRepository", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())

    context = _context()
    await jobs.send_midday_checkin_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == jobs._MIDDAY_TEXT_NO_HABITS


# --- Незапланированные сообщения персонажа (specs/027-butler-personas-phase2.md) --


async def test_midday_checkin_appends_persona_nudge_when_ai_available(
    no_db, monkeypatch
):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: AsyncMock())
    service = AsyncMock()
    service.list_active_habits.return_value = []
    monkeypatch.setattr(jobs, "HabitService", lambda repository: service)
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    monkeypatch.setattr(jobs, "PendingPromptRepository", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())

    assistant_service = AsyncMock()
    assistant_service.get_today_nudge_trigger.return_value = None
    assistant_service.get_persona.return_value = Persona.TRAINER
    monkeypatch.setattr(
        jobs, "build_assistant_service", lambda session: assistant_service
    )
    monkeypatch.setattr(
        jobs,
        "find_nudge_candidate",
        AsyncMock(return_value=("habit_streak:1", "Стрик «Бег» прервался.")),
    )
    monkeypatch.setattr(
        jobs, "generate_nudge_text", AsyncMock(return_value="Загляни в бота!")
    )

    context = _context()
    await jobs.send_midday_checkin_job(context)

    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == f"{jobs._MIDDAY_TEXT_NO_HABITS}\n\nЗагляни в бота!"
    assistant_service.record_nudge_sent.assert_awaited_once_with(1, "habit_streak:1")


async def test_midday_checkin_no_nudge_when_no_candidate(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: AsyncMock())
    service = AsyncMock()
    service.list_active_habits.return_value = []
    monkeypatch.setattr(jobs, "HabitService", lambda repository: service)
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    monkeypatch.setattr(jobs, "PendingPromptRepository", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())

    assistant_service = AsyncMock()
    assistant_service.get_today_nudge_trigger.return_value = None
    monkeypatch.setattr(
        jobs, "build_assistant_service", lambda session: assistant_service
    )
    monkeypatch.setattr(jobs, "find_nudge_candidate", AsyncMock(return_value=None))

    context = _context()
    await jobs.send_midday_checkin_job(context)

    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == jobs._MIDDAY_TEXT_NO_HABITS
    assistant_service.record_nudge_sent.assert_not_awaited()


async def test_midday_checkin_excludes_trigger_already_sent_today(no_db, monkeypatch):
    """Второй сегодняшний слот не должен передать find_nudge_candidate
    без exclude — иначе он бы заново нашёл тот же повод, отправленный
    на первом слоте (см. app/scheduler/persona_nudges.py)."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: AsyncMock())
    service = AsyncMock()
    service.list_active_habits.return_value = []
    monkeypatch.setattr(jobs, "HabitService", lambda repository: service)
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    monkeypatch.setattr(jobs, "PendingPromptRepository", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())

    assistant_service = AsyncMock()
    assistant_service.get_today_nudge_trigger.return_value = "habit_streak:1"
    monkeypatch.setattr(
        jobs, "build_assistant_service", lambda session: assistant_service
    )
    find_candidate = AsyncMock(return_value=None)
    monkeypatch.setattr(jobs, "find_nudge_candidate", find_candidate)

    context = _context()
    await jobs.send_midday_checkin_job(context)

    _, kwargs = find_candidate.call_args
    assert kwargs["exclude_trigger_key"] == "habit_streak:1"


async def test_midday_checkin_no_nudge_without_ai_client(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    service = AsyncMock()
    service.list_active_habits.return_value = []
    monkeypatch.setattr(jobs, "HabitService", lambda repository: service)
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    monkeypatch.setattr(jobs, "PendingPromptRepository", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())
    find_candidate = AsyncMock()
    monkeypatch.setattr(jobs, "find_nudge_candidate", find_candidate)

    context = _context()
    await jobs.send_midday_checkin_job(context)

    find_candidate.assert_not_awaited()


async def test_evening_checkin_appends_persona_nudge(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: AsyncMock())
    monkeypatch.setattr(
        jobs, "build_evening_checkin_text", AsyncMock(return_value="Итоги дня.")
    )
    monkeypatch.setattr(jobs, "build_task_service", lambda session: AsyncMock())
    monkeypatch.setattr(jobs, "HabitService", lambda repository: AsyncMock())
    monkeypatch.setattr(jobs, "HabitRepository", lambda session: None)
    # random.random() < _EVENING_GAP_CHANCE может добавить gap-вопрос —
    # отключаем его для предсказуемости этого теста.
    monkeypatch.setattr(jobs.random, "random", lambda: 1.0)

    assistant_service = AsyncMock()
    assistant_service.get_today_nudge_trigger.return_value = None
    assistant_service.get_persona.return_value = Persona.BUTLER
    monkeypatch.setattr(
        jobs, "build_assistant_service", lambda session: assistant_service
    )
    monkeypatch.setattr(
        jobs,
        "find_nudge_candidate",
        AsyncMock(return_value=("task_overdue:5", "Задача просрочена.")),
    )
    monkeypatch.setattr(
        jobs, "generate_nudge_text", AsyncMock(return_value="Не забудь про отчёт.")
    )

    context = _context()
    await jobs.send_evening_checkin_job(context)

    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Итоги дня.\n\nНе забудь про отчёт."
    assistant_service.record_nudge_sent.assert_awaited_once_with(1, "task_overdue:5")


# --- Фокус-сессии (specs/026-focus-sessions.md) -----------------------------


def _focus_session(**kwargs):
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("work_minutes", 25)
    kwargs.setdefault("break_minutes", 5)
    return MagicMock(**kwargs)


async def test_focus_notifications_sends_work_done_message(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    session = _focus_session(break_minutes=5)
    service = AsyncMock()
    service.list_due_work_end.return_value = [session]
    service.mark_work_notified.return_value = session
    service.list_due_break_end.return_value = []
    monkeypatch.setattr(jobs, "build_focus_service", lambda s: service)

    context = _context()
    await jobs.send_focus_notifications_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "Работа окончена" in kwargs["text"]
    assert "5 мин" in kwargs["text"]
    service.mark_work_notified.assert_awaited_once_with(session)


async def test_focus_notifications_sends_break_done_message(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    session = _focus_session()
    service = AsyncMock()
    service.list_due_work_end.return_value = []
    service.list_due_break_end.return_value = [session]
    monkeypatch.setattr(jobs, "build_focus_service", lambda s: service)

    context = _context()
    await jobs.send_focus_notifications_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "завершена" in kwargs["text"]
    service.mark_break_notified.assert_awaited_once_with(session)


async def test_focus_notifications_break_done_shows_reward(no_db, monkeypatch):
    """specs/029 — сумма монет за сессию попадает в текст уведомления."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    session = _focus_session()
    completed = _focus_session()
    completed.reward_coins = 11
    service = AsyncMock()
    service.list_due_work_end.return_value = []
    service.list_due_break_end.return_value = [session]
    service.mark_break_notified.return_value = completed
    monkeypatch.setattr(jobs, "build_focus_service", lambda s: service)

    context = _context()
    await jobs.send_focus_notifications_job(context)

    _, kwargs = context.bot.send_message.call_args
    assert "+11 🪙" in kwargs["text"]


async def test_focus_notifications_ignores_other_users_sessions(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    session = _focus_session(telegram_user_id=999)
    service = AsyncMock()
    service.list_due_work_end.return_value = [session]
    service.list_due_break_end.return_value = []
    monkeypatch.setattr(jobs, "build_focus_service", lambda s: service)

    context = _context()
    await jobs.send_focus_notifications_job(context)

    context.bot.send_message.assert_not_awaited()
    service.mark_work_notified.assert_not_awaited()


async def test_focus_notifications_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_focus_notifications_job(context)

    context.bot.send_message.assert_not_awaited()


# --- Ферма/питомец (specs/028-farm-tamagotchi-rewards.md) --------------------


def _farm_plot(**kwargs):
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("hay_yield", 10)
    return MagicMock(**kwargs)


def _pet(**kwargs):
    kwargs.setdefault("telegram_user_id", 1)
    return MagicMock(**kwargs)


async def test_farm_pet_notifications_sends_hay_ready_message(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    plot = _farm_plot(hay_yield=10)
    farm_service = AsyncMock()
    farm_service.list_due_ready_notifications.return_value = [plot]
    farm_service.mark_ready_notified.return_value = plot
    monkeypatch.setattr(jobs, "build_farm_service", lambda s: farm_service)
    pet_service = AsyncMock()
    pet_service.list_due_hunger_notifications.return_value = []
    monkeypatch.setattr(jobs, "build_pet_service", lambda s: pet_service)

    context = _context()
    await jobs.send_farm_pet_notifications_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "Сено готово" in kwargs["text"]
    assert "10" in kwargs["text"]
    farm_service.mark_ready_notified.assert_awaited_once_with(plot)


async def test_farm_pet_notifications_sends_hungry_message(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    farm_service = AsyncMock()
    farm_service.list_due_ready_notifications.return_value = []
    monkeypatch.setattr(jobs, "build_farm_service", lambda s: farm_service)
    pet = _pet()
    pet_service = AsyncMock()
    pet_service.list_due_hunger_notifications.return_value = [pet]
    pet_service.mark_hunger_notified.return_value = pet
    monkeypatch.setattr(jobs, "build_pet_service", lambda s: pet_service)

    context = _context()
    await jobs.send_farm_pet_notifications_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "проголодался" in kwargs["text"]
    pet_service.mark_hunger_notified.assert_awaited_once_with(pet)


async def test_farm_pet_notifications_sends_both_in_one_tick(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    plot = _farm_plot()
    farm_service = AsyncMock()
    farm_service.list_due_ready_notifications.return_value = [plot]
    monkeypatch.setattr(jobs, "build_farm_service", lambda s: farm_service)
    pet = _pet()
    pet_service = AsyncMock()
    pet_service.list_due_hunger_notifications.return_value = [pet]
    monkeypatch.setattr(jobs, "build_pet_service", lambda s: pet_service)

    context = _context()
    await jobs.send_farm_pet_notifications_job(context)

    assert context.bot.send_message.await_count == 2


async def test_farm_pet_notifications_ignores_other_users_plot(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    plot = _farm_plot(telegram_user_id=999)
    farm_service = AsyncMock()
    farm_service.list_due_ready_notifications.return_value = [plot]
    monkeypatch.setattr(jobs, "build_farm_service", lambda s: farm_service)
    pet_service = AsyncMock()
    pet_service.list_due_hunger_notifications.return_value = []
    monkeypatch.setattr(jobs, "build_pet_service", lambda s: pet_service)

    context = _context()
    await jobs.send_farm_pet_notifications_job(context)

    context.bot.send_message.assert_not_awaited()
    farm_service.mark_ready_notified.assert_not_awaited()


async def test_farm_pet_notifications_ignores_other_users_pet(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    farm_service = AsyncMock()
    farm_service.list_due_ready_notifications.return_value = []
    monkeypatch.setattr(jobs, "build_farm_service", lambda s: farm_service)
    pet = _pet(telegram_user_id=999)
    pet_service = AsyncMock()
    pet_service.list_due_hunger_notifications.return_value = [pet]
    monkeypatch.setattr(jobs, "build_pet_service", lambda s: pet_service)

    context = _context()
    await jobs.send_farm_pet_notifications_job(context)

    context.bot.send_message.assert_not_awaited()
    pet_service.mark_hunger_notified.assert_not_awaited()


async def test_farm_pet_notifications_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_farm_pet_notifications_job(context)

    context.bot.send_message.assert_not_awaited()
