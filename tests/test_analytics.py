import importlib

from app.core.auth_deps import require_agent_or_admin

analytics_router_module = importlib.import_module("app.analytics.routers.analytics_router")


def test_dashboard_returns_metrics(client, monkeypatch):
    class FakeMetrics:
        def __init__(self):
            self.total_conversations = 1

        def model_dump(self):
            return {"overview": {"total_conversations": 1}}

    async def fake_dashboard(*args, **kwargs):
        return FakeMetrics()

    monkeypatch.setattr(analytics_router_module, "get_dashboard", fake_dashboard)
    client.app.dependency_overrides[require_agent_or_admin] = lambda: {"_id": "admin-1", "role": "admin"}

    response = client.get("/api/v1/analytics/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["overview"]["total_conversations"] == 1


def test_export_tickets_returns_stream(client, monkeypatch):
    async def fake_export_tickets(*args, **kwargs):
        return [{"ticket_id": "TKT-1", "subject": "Billing"}]

    monkeypatch.setattr(analytics_router_module, "export_tickets", fake_export_tickets)
    client.app.dependency_overrides[require_agent_or_admin] = lambda: {"_id": "admin-1", "role": "admin"}

    response = client.get("/api/v1/analytics/export/tickets")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
