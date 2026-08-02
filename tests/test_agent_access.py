import pytest

import app.core.auth_deps as auth_deps


@pytest.fixture
def agent_user_payload():
    return {
        "_id": "agent-123",
        "full_name": "Agent Smith",
        "email": "agent@example.com",
        "role": "agent",
        "is_active": True,
    }


def test_agent_can_access_analytics_overview(client, agent_user_payload):
    async def fake_current_user():
        return agent_user_payload

    client.app.dependency_overrides[auth_deps.get_current_user] = fake_current_user

    response = client.get("/api/v1/analytics/overview", params={"period": "last_30_days"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True


def test_agent_can_access_reports_catalog(client, agent_user_payload):
    async def fake_current_user():
        return agent_user_payload

    client.app.dependency_overrides[auth_deps.get_current_user] = fake_current_user

    response = client.get("/api/v1/reports/available")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True


def test_agent_can_list_history(client, agent_user_payload):
    async def fake_current_user():
        return agent_user_payload

    client.app.dependency_overrides[auth_deps.get_current_user] = fake_current_user

    response = client.get("/api/v1/history", params={"page": 1, "page_size": 10})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
