from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.finance.service import CategoryBreakdown, FinanceSummary
from app.scheduler.finance_report import build_finance_report

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _finance_service(summary: FinanceSummary) -> AsyncMock:
    service = AsyncMock()
    service.build_period_summary.return_value = summary
    return service


async def test_empty_period_shows_zeroes():
    summary = FinanceSummary(income_total=0, mandatory_total=0, free_money=0)

    text = await build_finance_report(1, _finance_service(summary), now=NOW)

    assert "Доход: 0 ₽" in text
    assert "Свободно: 0 ₽" in text
    assert "август" in text


async def test_income_and_mandatory_shown():
    summary = FinanceSummary(
        income_total=80000, mandatory_total=45000, free_money=35000
    )

    text = await build_finance_report(1, _finance_service(summary), now=NOW)

    assert "Доход: 80 000 ₽" in text
    assert "Обязательные платежи: 45 000 ₽" in text
    assert "Свободно: 35 000 ₽" in text


async def test_category_within_norm_no_warning():
    summary = FinanceSummary(
        income_total=10000,
        mandatory_total=0,
        free_money=10000,
        categories=[
            CategoryBreakdown(
                category="groceries", label="🛒 Продукты", spent=2000, norm=3000
            )
        ],
    )

    text = await build_finance_report(1, _finance_service(summary), now=NOW)

    assert "🛒 Продукты: 2 000 / 3 000 ₽ нормы" in text
    assert "⚠️" not in text


async def test_category_over_budget_shows_warning():
    summary = FinanceSummary(
        income_total=10000,
        mandatory_total=0,
        free_money=10000,
        categories=[
            CategoryBreakdown(
                category="eating_out", label="🍔 Кафе", spent=9000, norm=1500
            )
        ],
    )

    text = await build_finance_report(1, _finance_service(summary), now=NOW)

    assert "⚠️ 🍔 Кафе: 9 000 / 1 500 ₽ нормы — сверх нормы" in text


async def test_no_categories_no_category_section():
    summary = FinanceSummary(income_total=0, mandatory_total=0, free_money=0)

    text = await build_finance_report(1, _finance_service(summary), now=NOW)

    assert "нормы" not in text


async def test_ai_insight_appended_on_success():
    summary = FinanceSummary(income_total=1000, mandatory_total=0, free_money=1000)
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Трать поменьше на кофе."

    text = await build_finance_report(
        1, _finance_service(summary), ai_client=ai_client, now=NOW
    )

    assert "💡 Трать поменьше на кофе." in text


async def test_ai_failure_falls_back_to_dry_report():
    from app.ai.client import AIServiceError

    summary = FinanceSummary(income_total=1000, mandatory_total=0, free_money=1000)
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    text = await build_finance_report(
        1, _finance_service(summary), ai_client=ai_client, now=NOW
    )

    assert "💡" not in text
    assert "Доход: 1 000 ₽" in text


async def test_no_ai_client_no_insight():
    summary = FinanceSummary(income_total=1000, mandatory_total=0, free_money=1000)

    text = await build_finance_report(1, _finance_service(summary), now=NOW)

    assert "💡" not in text


async def test_ai_insight_uses_active_persona_voice():
    """specs/020-butler-personas.md — персонаж влияет на system-промпт
    AI-вставки в финансовом отчёте."""
    from app.assistant.personas import Persona

    summary = FinanceSummary(income_total=1000, mandatory_total=0, free_money=1000)
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Держись плана."

    await build_finance_report(
        1,
        _finance_service(summary),
        ai_client=ai_client,
        now=NOW,
        persona=Persona.FINANCIER,
    )

    messages = ai_client.complete.call_args.args[0]
    assert "cfo" in messages[0]["content"].lower()
