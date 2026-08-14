from app.insights.formatting import build_insights_text


def test_no_findings_returns_fallback_text():
    text = build_insights_text([])

    assert "маловато данных" in text


def test_findings_rendered_as_bullets():
    text = build_insights_text(["Находка раз.", "Находка два."])

    assert "• Находка раз." in text
    assert "• Находка два." in text
    assert text.startswith("Инсайты за последние 60 дней")
