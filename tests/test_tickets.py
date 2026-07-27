from app.core.auth_deps import get_current_user


def test_create_ticket_returns_success(client, monkeypatch, current_user_payload):
    async def fake_create_ticket(*args, **kwargs):
        return {
            "_id": "ticket-1",
            "ticket_id": "TKT-20240101-000001",
            "user_id": "user-123",
            "conversation_id": None,
            "subject": "Billing issue",
            "description": "Charged twice",
            "category": "billing",
            "status": "open",
            "priority": "high",
            "assigned_to": None,
            "resolved_at": None,
            "category_confidence": 0.99,
            "auto_classified": True,
            "classification_model": "gemini-1.5-flash",
            "tags": [],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

    monkeypatch.setattr("app.routers.tickets.create_ticket", fake_create_ticket)
    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post(
        "/api/v1/tickets",
        json={"subject": "Billing issue", "description": "Charged twice"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["subject"] == "Billing issue"


def test_ticket_stats_requires_authentication(client):
    response = client.get("/api/v1/tickets/stats")
    assert response.status_code == 401
    assert response.json()["success"] is False
