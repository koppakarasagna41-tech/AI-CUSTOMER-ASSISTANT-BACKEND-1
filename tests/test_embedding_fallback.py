import pytest

from app.knowledge.embeddings import embedding_service


@pytest.mark.asyncio
async def test_embed_texts_falls_back_to_local_embeddings(monkeypatch):
    monkeypatch.setattr(embedding_service, "_configured", True)

    def _raise(*args, **kwargs):
        raise RuntimeError("model not supported")

    monkeypatch.setattr(embedding_service.genai, "embed_content", _raise)

    vectors = await embedding_service.embed_texts(["refund policy", "password reset"])

    assert len(vectors) == 2
    assert vectors[0] != []
    assert len(vectors[0]) == embedding_service._DEFAULT_EMBEDDING_DIM
    assert all(isinstance(value, float) for value in vectors[0])
