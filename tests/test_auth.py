import pytest
from app.core.auth_deps import get_current_user


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_tokens(client, monkeypatch, current_user_payload):
    created_user = {
        **current_user_payload,
        "_id": "user-123",
        "password_hash": "hashed",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_create_user(*args, **kwargs):
        return created_user

    async def fake_get_user_by_email(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.create_user", fake_create_user)
    monkeypatch.setattr("app.routers.auth.get_user_by_email", fake_get_user_by_email)

    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password": "SecurePass123",
            "role": "customer",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "jane@example.com"
    assert body["data"]["tokens"]["access_token"]


def test_login_returns_error_for_invalid_credentials(client, monkeypatch):
    async def fake_get_user_by_email(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.get_user_by_email", fake_get_user_by_email)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["success"] is False


def test_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["success"] is False
