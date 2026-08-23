"""
Pydantic-схемы для Assistant Service.
"""

from pydantic import BaseModel

from app.assistant.personas import Persona


class PersonaRead(BaseModel):
    telegram_user_id: int
    persona: Persona


class PersonaUpdate(BaseModel):
    telegram_user_id: int
    persona: Persona
