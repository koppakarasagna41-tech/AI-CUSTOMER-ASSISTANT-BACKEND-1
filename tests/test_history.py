import importlib

from app.core.auth_deps import get_current_user

history_router_module = importlib.import_module("app.history.routers.history_router")


def test_history_list_returns_paginated_history(client, monkeypatch, current_user_payload):
    async def fake_list_history(*args, **kwargs):
        return [], 0

    monkeypatch.setattr(history_router_module, "list_conversation_history", fake_list_history)
    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.get("/api/v1/history")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["meta"]["total_items"] == 0


def test_search_history_returns_matches(client, monkeypatch, current_user_payload):
    async def fake_search(*args, **kwargs):
        return [{"_id": "msg-1", "conversation_id": "conv-1", "role": "user", "content": "hello", "status": "sent"}], 1

    monkeypatch.setattr(history_router_module, "search_messages", fake_search)
    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.get("/api/v1/history/search", params={"q": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["content"] == "hello"
