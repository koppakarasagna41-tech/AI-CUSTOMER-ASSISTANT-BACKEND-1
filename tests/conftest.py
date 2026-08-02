import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

import app.main as main_module
import app.database.dependencies as database_dependencies
from app.main import create_app


class _DummyCursor:
    def __init__(self, items=None):
        self._items = list(items or [])

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self._items[:length] if length is not None else self._items)


class _DummyCollection:
    def __init__(self, name: str):
        self.name = name

    def aggregate(self, *args, **kwargs):
        return _DummyCursor([])

    async def find_one(self, *args, **kwargs):
        if args:
            query = args[0]
            if isinstance(query, dict) and "conversation_id" in query:
                return {"conversation_id": query["conversation_id"], "user_id": "user-123"}
        return None

    async def count_documents(self, *args, **kwargs):
        return 0

    def find(self, *args, **kwargs):
        return _DummyCursor([])

    async def delete_many(self, *args, **kwargs):
        return type("DeleteResult", (), {"deleted_count": 0})()

    async def delete_one(self, *args, **kwargs):
        return None

    async def update_one(self, *args, **kwargs):
        return None

    async def insert_one(self, *args, **kwargs):
        return None

    async def insert_many(self, *args, **kwargs):
        return None

    async def find_one_and_update(self, *args, **kwargs):
        return None


class _DummyDatabase:
    def __getitem__(self, name: str):
        return _DummyCollection(name)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main_module, "connect_to_mongo", AsyncMock())
    monkeypatch.setattr(main_module, "close_mongo_connection", AsyncMock())
    monkeypatch.setattr(database_dependencies, "get_database", lambda: _DummyDatabase())

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_dependency_overrides(client):
    client.app.dependency_overrides.clear()
    yield
    client.app.dependency_overrides.clear()


@pytest.fixture
def current_user_payload():
    return {
        "_id": "user-123",
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "role": "customer",
        "is_active": True,
    }
