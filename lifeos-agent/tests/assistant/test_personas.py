"""
app/assistant/personas.py — характер-листы и сборка системного промпта.
"""

from app.assistant.personas import (
    DEFAULT_PERSONA,
    PERSONA_LABELS,
    Persona,
    build_insight_prompt,
    character_sheet,
)


def test_every_persona_has_a_label():
    for persona in Persona:
        assert persona in PERSONA_LABELS


def test_every_persona_has_a_distinct_character_sheet():
    sheets = {persona: character_sheet(persona) for persona in Persona}
    assert len(set(sheets.values())) == len(Persona)


def test_default_persona_is_butler():
    assert DEFAULT_PERSONA is Persona.BUTLER


def test_build_insight_prompt_combines_character_and_task():
    prompt = build_insight_prompt(Persona.TRAINER, "Задание.")

    assert character_sheet(Persona.TRAINER) in prompt
    assert "Задание." in prompt
