import asyncio
from unittest.mock import AsyncMock

from app.services.gemini.gemini_service import GeminiService
from app.services.gemini.api_wrapper import GeminiError


def test_gemini_service_chat_delegates_to_generator(monkeypatch):
    fake_result = type("Result", (), {"foo": "bar"})()

    async def fake_generate_ai_response(*args, **kwargs):
        return fake_result

    monkeypatch.setattr("app.services.gemini.gemini_service.generate_ai_response", fake_generate_ai_response)

    result = asyncio.run(
        GeminiService.chat(
            conversation_id="conv-1",
            user_message="Hello",
            conversations_col=object(),
            messages_col=object(),
            user_name="Jane",
        )
    )

    assert result is fake_result


def test_gemini_service_is_configured(monkeypatch):
    monkeypatch.setattr("app.services.gemini.gemini_service.settings.GEMINI_API_KEY", "abc")
    assert GeminiService.is_configured() is True

    monkeypatch.setattr("app.services.gemini.gemini_service.settings.GEMINI_API_KEY", "")
    assert GeminiService.is_configured() is False


def test_generate_content_async_wraps_gemini_errors(monkeypatch):
    from app.services.gemini import api_wrapper

    monkeypatch.setattr(api_wrapper, "_ensure_configured", lambda: None)

    class FakeGenerationConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(api_wrapper.genai, "types", type("Types", (), {"GenerationConfig": FakeGenerationConfig})())
    monkeypatch.setattr(api_wrapper.genai, "GenerativeModel", lambda *args, **kwargs: None)

    class FakeLoop:
        def run_in_executor(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(api_wrapper.asyncio, "get_event_loop", lambda: FakeLoop())

    import pytest

    with pytest.raises(GeminiError):
        asyncio.run(
            api_wrapper.generate_content_async(
                model_name="gemini-1.5-flash",
                system_prompt="x",
                history=[],
                user_message="hi",
                max_tokens=16,
                temperature=0.1,
                top_p=0.9,
                top_k=10,
                timeout=5,
            )
        )
