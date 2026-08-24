"""
REST API для финансов (specs/017-finance.md).

Эндпоинты не содержат бизнес-логики — только вызывают FinanceService.
Не в первой итерации фичи (см. спеку, "Что НЕ входит") — добавлен по
прямой просьбе владельца, чтобы `/ui` тоже показывал траты/доходы, а не
только бот.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_debt_service, build_finance_service
from app.db.session import get_session
from app.finance.models import CATEGORIES, Transaction
from app.finance.schemas import (
    DebtCreate,
    DebtPayment,
    DebtPaymentRead,
    DebtRead,
    DebtUpdate,
    FinanceSummaryRead,
    MonthSummaryRead,
    TransactionCreate,
    TransactionRead,
)
from app.finance.service import DebtService, FinanceService

router = APIRouter(prefix="/finance", tags=["finance"])


def _to_read(transaction: Transaction) -> TransactionRead:
    read = TransactionRead.model_validate(transaction)
    if transaction.category is not None:
        read.category_label = CATEGORIES.get(transaction.category, transaction.category)
    return read


def get_finance_service(
    session: AsyncSession = Depends(get_session),
) -> FinanceService:
    return build_finance_service(session)


def get_debt_service(
    session: AsyncSession = Depends(get_session),
) -> DebtService:
    return build_debt_service(session)


def _current_month_start() -> datetime:
    """Тот же расчёт периода, что в app/scheduler/finance_report.py и
    app/telegram/callbacks.py — три места сознательно не сведены в одно
    общее (ADR-004, тот же приём, что у _esc в briefing.py/weekly_digest.py/
    keyboards.py: четыре строки дублировать дешевле, чем городить общий
    модуль под одну функцию)."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.post(
    "/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    payload: TransactionCreate,
    service: FinanceService = Depends(get_finance_service),
) -> TransactionRead:
    try:
        transaction = await service.add_transaction(
            telegram_user_id=payload.telegram_user_id,
            kind=payload.kind,
            amount=payload.amount,
            category=payload.category,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _to_read(transaction)


@router.get("/transactions", response_model=list[TransactionRead])
async def list_transactions(
    telegram_user_id: int,
    limit: int = 10,
    service: FinanceService = Depends(get_finance_service),
) -> list[TransactionRead]:
    transactions = await service.list_recent_transactions(telegram_user_id, limit)
    return [_to_read(t) for t in transactions]


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: int,
    telegram_user_id: int,
    service: FinanceService = Depends(get_finance_service),
) -> None:
    transaction = await service.delete_transaction(telegram_user_id, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Транзакция не найдена"
        )


@router.get("/summary", response_model=FinanceSummaryRead)
async def get_summary(
    telegram_user_id: int,
    since: Optional[datetime] = None,
    service: FinanceService = Depends(get_finance_service),
) -> FinanceSummaryRead:
    """`since` не задан — считаем с начала текущего календарного месяца
    (тот же период, что и в еженедельном отчёте)."""
    period_start = since or _current_month_start()
    summary = await service.build_period_summary(telegram_user_id, period_start)
    return FinanceSummaryRead.model_validate(summary)


@router.get("/analytics", response_model=list[MonthSummaryRead])
async def get_analytics(
    telegram_user_id: int,
    months: int = 6,
    service: FinanceService = Depends(get_finance_service),
) -> list[MonthSummaryRead]:
    """Доход/траты по месяцам за период — тренд для /ui (specs/017,
    довесок "добавить аналитику")."""
    summaries = await service.monthly_breakdown(telegram_user_id, months)
    return [MonthSummaryRead.model_validate(s) for s in summaries]


@router.post("/debts", response_model=DebtRead, status_code=status.HTTP_201_CREATED)
async def create_debt(
    payload: DebtCreate, service: DebtService = Depends(get_debt_service)
) -> DebtRead:
    try:
        debt = await service.add_debt(
            telegram_user_id=payload.telegram_user_id,
            name=payload.name,
            total_amount=payload.total_amount,
            due_date=payload.due_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return DebtRead.model_validate(debt)


@router.get("/debts", response_model=list[DebtRead])
async def list_debts(
    telegram_user_id: int, service: DebtService = Depends(get_debt_service)
) -> list[DebtRead]:
    debts = await service.list_debts(telegram_user_id)
    return [DebtRead.model_validate(d) for d in debts]


@router.post("/debts/{debt_id}/payment", response_model=DebtRead)
async def pay_debt(
    debt_id: int,
    payload: DebtPayment,
    service: DebtService = Depends(get_debt_service),
) -> DebtRead:
    try:
        debt = await service.record_payment(
            payload.telegram_user_id, debt_id, payload.amount
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if debt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Долг не найден"
        )
    return DebtRead.model_validate(debt)


@router.patch("/debts/{debt_id}", response_model=DebtRead)
async def update_debt(
    debt_id: int,
    telegram_user_id: int,
    payload: DebtUpdate,
    service: DebtService = Depends(get_debt_service),
) -> DebtRead:
    try:
        debt = await service.update_debt(
            telegram_user_id=telegram_user_id,
            debt_id=debt_id,
            due_date=payload.due_date,
            clear_due_date=payload.clear_due_date,
            monthly_payment=payload.monthly_payment,
            clear_monthly_payment=payload.clear_monthly_payment,
            next_payment_due=payload.next_payment_due,
            clear_next_payment_due=payload.clear_next_payment_due,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if debt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Долг не найден"
        )
    return DebtRead.model_validate(debt)


@router.get("/debts/{debt_id}/payments", response_model=list[DebtPaymentRead])
async def list_debt_payments(
    debt_id: int,
    telegram_user_id: int,
    service: DebtService = Depends(get_debt_service),
) -> list[DebtPaymentRead]:
    payments = await service.list_payments(telegram_user_id, debt_id)
    return [DebtPaymentRead.model_validate(p) for p in payments]


@router.delete("/debts/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debt(
    debt_id: int,
    telegram_user_id: int,
    service: DebtService = Depends(get_debt_service),
) -> None:
    debt = await service.delete_debt(telegram_user_id, debt_id)
    if debt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Долг не найден"
        )
