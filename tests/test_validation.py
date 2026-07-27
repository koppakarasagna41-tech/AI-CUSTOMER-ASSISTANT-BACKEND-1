from app.core.auth_deps import get_current_user


def test_invalid_login_payload_returns_validation_error(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": ""},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "VALIDATION_ERROR"


def test_invalid_ticket_payload_returns_validation_error(client):
    async def override_get_current_user():
        return {"_id": "user-1", "role": "customer"}

    client.app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post(
        "/api/v1/tickets",
        json={"subject": "", "description": ""},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "VALIDATION_ERROR"
