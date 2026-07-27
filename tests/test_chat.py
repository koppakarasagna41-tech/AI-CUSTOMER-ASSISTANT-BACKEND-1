from app.core.auth_deps import get_current_user


def test_start_chat_returns_ai_response(client, monkeypatch, current_user_payload):
    async def fake_create_document(*args, **kwargs):
        return "doc-id"

    async def fake_gemini_chat(*args, **kwargs):
        return type(
            "Result",
            (),
            {
                "conversation_id": "conv-1",
                "user_message_id": "user-msg",
                "ai_message_id": "ai-msg",
                "ai_content": "Hello there",
                "tokens_used": 12,
                "model_used": "gemini-1.5-flash",
                "is_fallback": False,
            },
        )()

    monkeypatch.setattr("app.routers.chat.GeminiService.is_configured", lambda: True)
    monkeypatch.setattr("app.routers.chat.create_document", fake_create_document)
    monkeypatch.setattr("app.routers.chat.GeminiService.chat", fake_gemini_chat)

    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello", "title": "Greeting"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["ai_response"]["content"] == "Hello there"


def test_chat_history_requires_valid_conversation(client, monkeypatch, current_user_payload):
    async def fake_get_document(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.chat.get_document", fake_get_document)

    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.get("/api/v1/chat/not-found/history")

    assert response.status_code == 404
    assert response.json()["success"] is False
