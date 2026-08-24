"""
Интеграционный тест REST API финансов — долги и аналитика
(specs/017-finance.md, довесок). transactions/summary уже проверялись
только через сервис/репозиторий, интеграционного теста REST не было.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import require_api_token
from app.db.base import Base
from app.db.session import get_session
from app.main import app


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_api_token] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_analytics_returns_requested_months(client):
    response = await client.get(
        "/finance/analytics", params={"telegram_user_id": 1, "months": 3}
    )
    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_analytics_reflects_transactions(client):
    await client.post(
        "/finance/transactions",
        json={"telegram_user_id": 1, "kind": "income", "amount": 5000},
    )

    response = await client.get(
        "/finance/analytics", params={"telegram_user_id": 1, "months": 1}
    )
    assert response.json()[0]["income_total"] == 5000
    assert response.json()[0]["net"] == 5000


# --- Рекомендации по бюджету (отчёт владельца 24.08, вечер #6, волна 8) -----


async def test_recommendations_empty_without_history(client):
    response = await client.get(
        "/finance/recommendations", params={"telegram_user_id": 9}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_recommendations_exclude_mandatory_and_current_month(client):
    # Обязательная категория — не в счёт вообще.
    await client.post(
        "/finance/transactions",
        json={
            "telegram_user_id": 9,
            "kind": "expense",
            "amount": 40000,
            "category": "rent",
        },
    )
    # Необязательная категория, но текущий месяц — тоже не в счёт (ещё
    # не закончился), поэтому здесь всё ещё пусто.
    await client.post(
        "/finance/transactions",
        json={
            "telegram_user_id": 9,
            "kind": "expense",
            "amount": 3000,
            "category": "groceries",
        },
    )

    response = await client.get(
        "/finance/recommendations", params={"telegram_user_id": 9}
    )
    assert response.json() == []


async def test_create_and_list_debt(client):
    response = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 2, "name": "Кредит на авто", "total_amount": 300000},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["remaining_amount"] == 300000

    response = await client.get("/finance/debts", params={"telegram_user_id": 2})
    assert len(response.json()) == 1


async def test_create_debt_zero_amount_returns_400(client):
    response = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 2, "name": "Долг", "total_amount": 0},
    )
    assert response.status_code == 422  # gt=0 в схеме — Pydantic ловит раньше сервиса


async def test_pay_debt_reduces_remaining(client):
    create_resp = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 3, "name": "Рассрочка", "total_amount": 10000},
    )
    debt_id = create_resp.json()["id"]

    pay_resp = await client.post(
        f"/finance/debts/{debt_id}/payment",
        json={"telegram_user_id": 3, "amount": 4000},
    )
    assert pay_resp.status_code == 200
    assert pay_resp.json()["remaining_amount"] == 6000


async def test_pay_missing_debt_returns_404(client):
    response = await client.post(
        "/finance/debts/9999/payment",
        json={"telegram_user_id": 3, "amount": 100},
    )
    assert response.status_code == 404


async def test_delete_debt(client):
    create_resp = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 4, "name": "Долг", "total_amount": 1000},
    )
    debt_id = create_resp.json()["id"]

    response = await client.delete(
        f"/finance/debts/{debt_id}", params={"telegram_user_id": 4}
    )
    assert response.status_code == 204

    list_resp = await client.get("/finance/debts", params={"telegram_user_id": 4})
    assert list_resp.json() == []


# --- Лог платежей + план рассрочки (отчёт владельца 24.08, вечер #6, волна 7)


async def test_pay_debt_logs_payment_history(client):
    create_resp = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 5, "name": "Рассрочка", "total_amount": 10000},
    )
    debt_id = create_resp.json()["id"]

    await client.post(
        f"/finance/debts/{debt_id}/payment",
        json={"telegram_user_id": 5, "amount": 4000},
    )
    await client.post(
        f"/finance/debts/{debt_id}/payment",
        json={"telegram_user_id": 5, "amount": 2000},
    )

    response = await client.get(
        f"/finance/debts/{debt_id}/payments", params={"telegram_user_id": 5}
    )
    assert response.status_code == 200
    amounts = [p["amount"] for p in response.json()]
    assert amounts == [4000, 2000]


async def test_debt_payments_empty_before_any_payment(client):
    create_resp = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 5, "name": "Долг", "total_amount": 1000},
    )
    debt_id = create_resp.json()["id"]

    response = await client.get(
        f"/finance/debts/{debt_id}/payments", params={"telegram_user_id": 5}
    )
    assert response.json() == []


async def test_update_debt_sets_monthly_payment_plan(client):
    create_resp = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 6, "name": "Долг", "total_amount": 12000},
    )
    debt_id = create_resp.json()["id"]

    response = await client.patch(
        f"/finance/debts/{debt_id}",
        params={"telegram_user_id": 6},
        json={
            "monthly_payment": 1000,
            "next_payment_due": "2026-09-01T00:00:00Z",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_payment"] == 1000
    assert body["next_payment_due"].startswith("2026-09-01")


async def test_update_debt_clears_plan(client):
    create_resp = await client.post(
        "/finance/debts",
        json={"telegram_user_id": 6, "name": "Долг", "total_amount": 12000},
    )
    debt_id = create_resp.json()["id"]
    await client.patch(
        f"/finance/debts/{debt_id}",
        params={"telegram_user_id": 6},
        json={"monthly_payment": 1000},
    )

    response = await client.patch(
        f"/finance/debts/{debt_id}",
        params={"telegram_user_id": 6},
        json={"clear_monthly_payment": True},
    )
    assert response.json()["monthly_payment"] is None


async def test_update_missing_debt_returns_404(client):
    response = await client.patch(
        "/finance/debts/9999",
        params={"telegram_user_id": 6},
        json={"monthly_payment": 1000},
    )
    assert response.status_code == 404
