import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.core.exceptions import DatabaseError
from app.main import create_app


@pytest.mark.asyncio
async def test_lifespan_allows_app_to_boot_when_database_is_unavailable():
    app = create_app()

    with patch("app.main.connect_to_mongo", AsyncMock(side_effect=Exception("boom"))) as connect_mock:
        async with app.router.lifespan_context(app):
            pass

        connect_mock.assert_awaited_once()


def test_auth_register_returns_503_when_database_is_unavailable():
    app = create_app()

    with patch(
        "app.database.dependencies.get_database",
        side_effect=DatabaseError(
            message="Database is unavailable. Please try again later.",
            error_code="DATABASE_UNAVAILABLE",
            details={"service": "mongodb"},
        ),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Jane Doe",
                    "email": "jane@example.com",
                    "password": "SecurePass123",
                    "role": "customer",
                },
            )

    assert response.status_code == 503
    assert response.json()["error_code"] == "DATABASE_UNAVAILABLE"
