"""
Проверка владельца сущности — используется во всех сервисных методах,
которые получают голый `id` (см. AUDIT.md, A-1/B-2). Раньше эти методы
не принимали telegram_user_id вообще: сервис доверял id из
callback_data/REST-запроса, не проверяя, что сущность принадлежит
вызывающему.

Несовпадение владельца обрабатывается ТАК ЖЕ, как "не найдено" — не
403, а тот же самый None/умолчание, что и для несуществующего id. Не
подтверждаем существование чужой сущности (уже принятый в проекте
паттерн, см. TaskService.update_task)."""

from typing import Protocol, TypeVar


class _HasOwner(Protocol):
    telegram_user_id: int


ModelT = TypeVar("ModelT", bound=_HasOwner)


def owned_or_none(entity: ModelT | None, telegram_user_id: int) -> ModelT | None:
    if entity is None or entity.telegram_user_id != telegram_user_id:
        return None
    return entity
