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
