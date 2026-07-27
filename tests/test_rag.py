import importlib

from app.core.auth_deps import get_current_user

rag_router_module = importlib.import_module("app.rag.routers.rag_router")


def test_rag_query_returns_answer(client, monkeypatch, current_user_payload):
    class FakeResult:
        def __init__(self):
            self.conversation_id = "conv-rag"
            self.question = "How do I reset my password?"
            self.answer = "Use the forgot-password flow."
            self.confidence_score = 0.91
            self.escalated = False
            self.escalation_id = None
            self.sources = []
            self.tokens_used = 8
            self.model_used = "gemini-1.5-flash"
            self.response_time_ms = 12.3
            self.log_id = "log-1"

    async def fake_run_rag_pipeline(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(rag_router_module, "run_rag_pipeline", fake_run_rag_pipeline)
    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post(
        "/api/v1/rag/query",
        json={"question": "How do I reset my password?", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["answer"] == "Use the forgot-password flow."


def test_rag_ask_returns_escalation_message(client, monkeypatch, current_user_payload):
    class FakeResult:
        def __init__(self):
            self.question = "Where is billing info?"
            self.answer = "Please contact support."
            self.confidence_score = 0.2
            self.escalated = True
            self.response_time_ms = 9.1
            self.sources = []
            self.tokens_used = 0
            self.model_used = ""

    async def fake_run_ask_pipeline(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(rag_router_module, "run_ask_pipeline", fake_run_ask_pipeline)
    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post(
        "/api/v1/rag/ask",
        json={"question": "Where is billing info?", "top_k": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["answer"] == "Please contact support."
