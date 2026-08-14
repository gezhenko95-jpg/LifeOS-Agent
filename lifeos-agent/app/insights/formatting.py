"""
Финальная сборка текста Personal Insights из готовых находок
(см. specs/009-personal-insights.md, app/insights/calculations.py).
"""

_HEADER = "Инсайты за последние 60 дней 📊"
_NO_DATA_TEXT = "Пока маловато данных для инсайтов — возвращайся позже."


def build_insights_text(findings: list[str]) -> str:
    if not findings:
        return _NO_DATA_TEXT

    lines = [_HEADER, ""]
    lines.extend(f"• {finding}" for finding in findings)
    return "\n".join(lines)
