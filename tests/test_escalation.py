import importlib

from app.core.auth_deps import get_current_user, require_admin

escalation_router_module = importlib.import_module("app.escalation.routers.escalation_router")


def test_escalation_check_returns_result(client, monkeypatch, current_user_payload):
    class FakeSignal:
        trigger = "negative_streak"
        priority = "high"
        description = "Repeated angry messages"
        evidence = {"count": 3}

    async def fake_detect(*args, **kwargs):
        return [FakeSignal()]

    async def fake_ticket(*args, **kwargs):
        return {"ticket_id": "TKT-1"}

    async def fake_save(*args, **kwargs):
        return "esc-1"

    async def fake_notify(*args, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(escalation_router_module, "detect_escalation_signals", fake_detect)
    monkeypatch.setattr(escalation_router_module, "generate_escalation_ticket", fake_ticket)
    monkeypatch.setattr(escalation_router_module, "save_escalation_event", fake_save)
    monkeypatch.setattr(escalation_router_module, "notify_admin", fake_notify)
    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post("/api/v1/escalation/check/conv-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["should_escalate"] is True


def test_manual_escalation_is_allowed_for_admin(client, monkeypatch):
    admin_user = {"_id": "admin-1", "role": "admin"}

    async def fake_ticket(*args, **kwargs):
        return {"ticket_id": "TKT-2"}

    async def fake_save(*args, **kwargs):
        return "esc-2"

    async def fake_notify(*args, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(escalation_router_module, "generate_escalation_ticket", fake_ticket)
    monkeypatch.setattr(escalation_router_module, "save_escalation_event", fake_save)
    monkeypatch.setattr(escalation_router_module, "notify_admin", fake_notify)
    client.app.dependency_overrides[require_admin] = lambda: admin_user

    response = client.post(
        "/api/v1/escalation/manual",
        json={"conversation_id": "conv-1", "reason": "Manual review"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
