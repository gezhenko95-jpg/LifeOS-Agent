"""
Сборка текста финансового отчёта (specs/017-finance.md).

По образцу app/scheduler/weekly_digest.py: считает за ТЕКУЩИЙ календарный
месяц (доход/аренда естественно месячные — не скользящее окно в 7 дней),
но отправляется еженедельно, как промежуточная сверка внутри месяца. Если
передан ai_client — поверх шаблона добавляется одна короткая AI-фраза,
тем же паттерном, что и в брифинге/дайджесте; ошибка AI не должна сорвать
отправку.
"""

import logging
from datetime import datetime, timezone
from html import escape

from app.ai.client import AIClient, AIServiceError
from app.assistant.personas import DEFAULT_PERSONA, Persona, build_insight_prompt
from app.finance.service import FinanceService

logger = logging.getLogger(__name__)

_INSIGHT_TASK_INSTRUCTION = (
    "Ниже черновик финансового отчёта пользователя за месяц (доход, "
    "обязательные платежи, траты по категориям против нормы). Добавь "
    "наблюдение или совет — 2-4 предложения (примерно до 70 слов), по "
    "существу и конкретно, не короткая острота. На русском языке, без "
    "предисловий, без кавычек и без markdown. Верни только текст этой "
    "вставки, ничего больше."
)


def _insight_system_prompt(persona: Persona) -> str:
    return build_insight_prompt(persona, _INSIGHT_TASK_INSTRUCTION)


def _esc(text: str) -> str:
    """Как app/scheduler/briefing.py::_esc — сообщение уходит с
    parse_mode=HTML."""
    return escape(str(text), quote=False)


def _month_start(now: datetime) -> datetime:
    return now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )


def _month_label(now: datetime) -> str:
    months = (
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    )
    return months[now.month - 1]


async def _generate_insight(
    ai_client: AIClient, report_text: str, persona: Persona
) -> str | None:
    messages = [
        {"role": "system", "content": _insight_system_prompt(persona)},
        {"role": "user", "content": report_text},
    ]
    try:
        insight = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI-инсайт для финансового отчёта не сгенерирован: %s", exc)
        return None

    insight = insight.strip()
    return insight or None


async def build_finance_report(
    telegram_user_id: int,
    finance_service: FinanceService,
    ai_client: AIClient | None = None,
    now: datetime | None = None,
    persona: Persona = DEFAULT_PERSONA,
) -> str:
    now = now or datetime.now(timezone.utc)
    since = _month_start(now)
    summary = await finance_service.build_period_summary(telegram_user_id, since)

    parts = [f"Финансы за {_month_label(now)} 📊", ""]
    parts.append(f"Доход: {summary.income_total:,} ₽".replace(",", " "))
    parts.append(
        f"Обязательные платежи: {summary.mandatory_total:,} ₽".replace(",", " ")
    )
    parts.append(f"Свободно: {summary.free_money:,} ₽".replace(",", " "))

    if summary.categories:
        parts.append("")
        for category in summary.categories:
            spent = f"{category.spent:,}".replace(",", " ")
            norm = f"{category.norm:,}".replace(",", " ")
            prefix = "⚠️ " if category.over_budget else ""
            suffix = " — сверх нормы" if category.over_budget else ""
            parts.append(
                f"{prefix}{_esc(category.label)}: {spent} / {norm} ₽ нормы{suffix}"
            )

    text = "\n".join(parts)

    if ai_client is not None:
        insight = await _generate_insight(ai_client, text, persona)
        if insight:
            text = f"{text}\n\n💡 {_esc(insight)}"

    return text
