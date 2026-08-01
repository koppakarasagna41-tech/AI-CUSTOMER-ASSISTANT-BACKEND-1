from types import SimpleNamespace

import pytest
from app.core.auth_deps import get_current_user
from app.core.security import verify_password


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_tokens(client, monkeypatch, current_user_payload):
    created_user = {
        **current_user_payload,
        "_id": "user-123",
        "password_hash": "hashed",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_create_user(*args, **kwargs):
        return created_user

    async def fake_get_user_by_email(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.create_user", fake_create_user)
    monkeypatch.setattr("app.routers.auth.get_user_by_email", fake_get_user_by_email)

    client.app.dependency_overrides[get_current_user] = lambda: current_user_payload

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password": "SecurePass123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "jane@example.com"
    assert body["data"]["tokens"]["access_token"]


def test_register_rejects_agent_role(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password": "SecurePass123",
            "role": "agent",
        },
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "INVALID_ROLE"


def test_register_rejects_admin_role(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password": "SecurePass123",
            "role": "admin",
        },
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "INVALID_ROLE"


@pytest.mark.asyncio
async def test_create_user_promotes_first_user_to_admin(monkeypatch):
    async def fake_document_exists(*args, **kwargs):
        return False

    async def fake_count_documents(*args, **kwargs):
        return 0

    monkeypatch.setattr("app.services.user_service.document_exists", fake_document_exists)
    monkeypatch.setattr("app.services.user_service.count_documents", fake_count_documents)

    async def fake_create_document(col, data):
        return "id-1"

    async def fake_get_document_by_id(col, did):
        return {
            "_id": did,
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "role": "admin",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

    monkeypatch.setattr("app.services.user_service.create_document", fake_create_document)
    monkeypatch.setattr("app.services.user_service.get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr("app.services.user_service.hash_password", lambda password: "hashed")

    from app.services.user_service import create_user

    user = await create_user(
        col=object(),
        full_name="Jane Doe",
        email="jane@example.com",
        password="SecurePass123",
    )

    assert user["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_can_create_agent_via_admin_agents_endpoint(client, monkeypatch, current_user_payload):
    created_user = {
        **current_user_payload,
        "_id": "user-456",
        "full_name": "Agent Smith",
        "email": "agent@example.com",
        "role": "agent",
        "password_hash": "hashed",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_create_user(*args, **kwargs):
        assert kwargs["role"] == "agent"
        return created_user

    monkeypatch.setattr("app.routers.admin_agents.user_service.create_user", fake_create_user)
    admin_payload = {**current_user_payload, "role": "admin"}
    client.app.dependency_overrides[get_current_user] = lambda: admin_payload

    response = client.post(
        "/api/v1/admin/agents",
        json={
            "full_name": "Agent Smith",
            "email": "agent@example.com",
            "password": "TemporaryPass123",
            "role": "agent",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "agent@example.com"
    assert body["data"]["role"] == "agent"


@pytest.mark.asyncio
async def test_admin_can_list_agents(client, monkeypatch, current_user_payload):
    agent_document = {
        "_id": "agent-123",
        "full_name": "Agent Smith",
        "email": "agent@example.com",
        "role": "agent",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_count_documents(*args, **kwargs):
        return 1

    async def fake_get_documents(*args, **kwargs):
        return [agent_document]

    monkeypatch.setattr("app.routers.admin_agents.count_documents", fake_count_documents)
    monkeypatch.setattr("app.routers.admin_agents.get_documents", fake_get_documents)
    client.app.dependency_overrides[get_current_user] = lambda: {**current_user_payload, "role": "admin"}

    response = client.get("/api/v1/admin/agents?page=1&page_size=10")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["email"] == "agent@example.com"
    assert body["meta"]["total_items"] == 1


@pytest.mark.asyncio
async def test_admin_can_get_agent(client, monkeypatch, current_user_payload):
    agent_document = {
        "_id": "agent-123",
        "full_name": "Agent Smith",
        "email": "agent@example.com",
        "role": "agent",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_get_document_by_id(*args, **kwargs):
        return agent_document

    monkeypatch.setattr("app.routers.admin_agents.get_document_by_id", fake_get_document_by_id)
    client.app.dependency_overrides[get_current_user] = lambda: {**current_user_payload, "role": "admin"}

    response = client.get("/api/v1/admin/agents/agent-123")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["id"] == "agent-123"
    assert body["data"]["role"] == "agent"


@pytest.mark.asyncio
async def test_admin_can_reset_agent_password(client, monkeypatch, current_user_payload):
    async def fake_get_document_by_id(*args, **kwargs):
        return {
            "_id": "agent-123",
            "full_name": "Agent Smith",
            "email": "agent@example.com",
            "role": "agent",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

    async def fake_update_document_by_id(*args, **kwargs):
        return True

    monkeypatch.setattr("app.routers.admin_agents.get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr("app.routers.admin_agents.update_document_by_id", fake_update_document_by_id)
    client.app.dependency_overrides[get_current_user] = lambda: {**current_user_payload, "role": "admin"}

    response = client.post(
        "/api/v1/admin/agents/agent-123/reset-password",
        json={"password": "NewTemporaryPass123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Agent password reset successfully."


@pytest.mark.asyncio
async def test_admin_can_update_agent(client, monkeypatch, current_user_payload):
    updated_agent = {
        "_id": "agent-123",
        "full_name": "Agent Smith Updated",
        "email": "agent@example.com",
        "role": "agent",
        "is_active": False,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-02T00:00:00",
    }

    async def fake_update_document_by_id(*args, **kwargs):
        return True

    async def fake_get_document_by_id(*args, **kwargs):
        return updated_agent

    monkeypatch.setattr("app.routers.admin_agents.update_document_by_id", fake_update_document_by_id)
    monkeypatch.setattr("app.routers.admin_agents.get_document_by_id", fake_get_document_by_id)
    client.app.dependency_overrides[get_current_user] = lambda: {**current_user_payload, "role": "admin"}

    response = client.patch(
        "/api/v1/admin/agents/agent-123",
        json={"is_active": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["is_active"] is False
    assert body["data"]["full_name"] == "Agent Smith Updated"


@pytest.mark.asyncio
async def test_admin_can_delete_agent(client, monkeypatch, current_user_payload):
    agent_document = {
        "_id": "agent-123",
        "full_name": "Agent Smith",
        "email": "agent@example.com",
        "role": "agent",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_get_document_by_id(*args, **kwargs):
        return agent_document

    async def fake_delete_document_by_id(*args, **kwargs):
        return True

    monkeypatch.setattr("app.routers.admin_agents.get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr("app.routers.admin_agents.delete_document_by_id", fake_delete_document_by_id)
    client.app.dependency_overrides[get_current_user] = lambda: {**current_user_payload, "role": "admin"}

    response = client.delete("/api/v1/admin/agents/agent-123")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Agent deleted."


@pytest.mark.asyncio
async def test_seed_initial_admin_creates_admin_from_env(monkeypatch):
    created = []

    async def fake_count_documents(*args, **kwargs):
        return 0

    async def fake_create_user(*args, **kwargs):
        created.append(kwargs)
        return {"_id": "admin-1", "role": "admin", "email": kwargs["email"]}

    monkeypatch.setattr("app.services.user_service.count_documents", fake_count_documents)
    monkeypatch.setattr("app.services.user_service.create_user", fake_create_user)
    monkeypatch.setattr(
        "app.services.user_service.settings",
        SimpleNamespace(INITIAL_ADMIN_EMAIL="koppakarasagna41@gmail.com", INITIAL_ADMIN_PASSWORD="rasagna@A3"),
    )

    from app.services.user_service import seed_initial_admin

    result = await seed_initial_admin(object())

    assert result["role"] == "admin"
    assert created[0]["role"] == "admin"
    assert created[0]["email"] == "koppakarasagna41@gmail.com"


@pytest.mark.asyncio
async def test_seed_initial_admin_creates_admin_when_other_users_exist(monkeypatch):
    created = []

    async def fake_get_document(*args, **kwargs):
        return None

    async def fake_count_documents(*args, **kwargs):
        return 3

    async def fake_create_user(*args, **kwargs):
        created.append(kwargs)
        return {"_id": "admin-2", "role": "admin", "email": kwargs["email"]}

    monkeypatch.setattr("app.services.user_service.get_document", fake_get_document)
    monkeypatch.setattr("app.services.user_service.count_documents", fake_count_documents)
    monkeypatch.setattr("app.services.user_service.create_user", fake_create_user)
    monkeypatch.setattr(
        "app.services.user_service.settings",
        SimpleNamespace(INITIAL_ADMIN_EMAIL="koppakarasagna41@gmail.com", INITIAL_ADMIN_PASSWORD="rasagna@A3"),
    )

    from app.services.user_service import seed_initial_admin

    result = await seed_initial_admin(object())

    assert result["role"] == "admin"
    assert created[0]["role"] == "admin"
    assert created[0]["email"] == "koppakarasagna41@gmail.com"


@pytest.mark.asyncio
async def test_seed_initial_admin_promotes_existing_user_with_matching_email(monkeypatch):
    updated = []

    async def fake_get_document(*args, **kwargs):
        if kwargs.get("filter_query", {}).get("role") == "admin":
            return None
        return {"_id": "user-99", "email": "koppakarasagna41@gmail.com", "role": "customer"}

    async def fake_update_document_by_id(*args, **kwargs):
        updated.append((args[1], args[2]))
        return True

    async def fake_get_document_by_id(*args, **kwargs):
        return {"_id": "user-99", "email": "koppakarasagna41@gmail.com", "role": "admin", "is_active": True}

    monkeypatch.setattr("app.services.user_service.get_document", fake_get_document)
    monkeypatch.setattr("app.services.user_service.update_document_by_id", fake_update_document_by_id)
    monkeypatch.setattr("app.services.user_service.get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr("app.services.user_service.hash_password", lambda password: "hashed")
    monkeypatch.setattr(
        "app.services.user_service.settings",
        SimpleNamespace(INITIAL_ADMIN_EMAIL="koppakarasagna41@gmail.com", INITIAL_ADMIN_PASSWORD="rasagna@A3"),
    )

    from app.services.user_service import seed_initial_admin

    result = await seed_initial_admin(object())

    assert result["role"] == "admin"
    assert updated[0][0] == "user-99"
    assert updated[0][1]["$set"]["role"] == "admin"


@pytest.mark.asyncio
async def test_seed_initial_admin_repairs_invalid_existing_admin_hash(monkeypatch):
    updated = []

    async def fake_get_document(*args, **kwargs):
        if kwargs.get("filter_query", {}).get("role") == "admin":
            return {
                "_id": "admin-1",
                "email": "koppakarasagna41@gmail.com",
                "role": "admin",
                "password_hash": "not-a-valid-hash",
            }
        return None

    async def fake_update_document_by_id(*args, **kwargs):
        updated.append((args[1], args[2]))
        return True

    async def fake_get_document_by_id(*args, **kwargs):
        return {
            "_id": "admin-1",
            "email": "koppakarasagna41@gmail.com",
            "role": "admin",
            "password_hash": "$2b$12$dummyhashforpytest",
        }

    monkeypatch.setattr("app.services.user_service.get_document", fake_get_document)
    monkeypatch.setattr("app.services.user_service.update_document_by_id", fake_update_document_by_id)
    monkeypatch.setattr("app.services.user_service.get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        "app.services.user_service.settings",
        SimpleNamespace(INITIAL_ADMIN_EMAIL="koppakarasagna41@gmail.com", INITIAL_ADMIN_PASSWORD="rasagna@A3"),
    )

    from app.services.user_service import seed_initial_admin

    result = await seed_initial_admin(object())

    assert result["role"] == "admin"
    assert updated
    assert verify_password("rasagna@A3", updated[0][1]["$set"]["password_hash"]) is True


@pytest.mark.asyncio
async def test_admin_can_create_agent_via_users_endpoint(client, monkeypatch, current_user_payload):
    created_user = {
        **current_user_payload,
        "_id": "user-456",
        "full_name": "Agent Smith",
        "email": "agent@example.com",
        "role": "agent",
        "password_hash": "hashed",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    async def fake_create_user(*args, **kwargs):
        assert kwargs["role"] == "agent"
        return created_user

    monkeypatch.setattr("app.routers.users.user_service.create_user", fake_create_user)
    admin_payload = {**current_user_payload, "role": "admin"}
    client.app.dependency_overrides[get_current_user] = lambda: admin_payload

    response = client.post(
        "/api/v1/users",
        json={
            "full_name": "Agent Smith",
            "email": "agent@example.com",
            "password": "TemporaryPass123",
            "role": "agent",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "agent@example.com"
    assert body["data"]["role"] == "agent"


@pytest.mark.asyncio
async def test_admin_can_reset_agent_password(client, monkeypatch, current_user_payload):
    async def fake_update_document_by_id(*args, **kwargs):
        return True

    async def fake_get_user_by_id(*args, **kwargs):
        return {
            "_id": "user-456",
            "full_name": "Agent Smith",
            "email": "agent@example.com",
            "role": "agent",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

    monkeypatch.setattr("app.routers.users.update_document_by_id", fake_update_document_by_id)
    monkeypatch.setattr("app.routers.users.user_service.get_user_by_id", fake_get_user_by_id)
    client.app.dependency_overrides[get_current_user] = lambda: {**current_user_payload, "role": "admin"}

    response = client.post(
        "/api/v1/users/user-456/reset-password",
        json={"password": "NewTemporaryPass123"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_login_returns_error_for_invalid_credentials(client, monkeypatch):
    async def fake_get_user_by_email(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.get_user_by_email", fake_get_user_by_email)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["success"] is False


def test_verify_password_handles_invalid_hashes():
    assert verify_password("password", "not-a-valid-hash") is False
    assert verify_password("password", "") is False


def test_login_falls_back_to_name_when_full_name_missing(client, monkeypatch):
    async def fake_get_user_by_email(*args, **kwargs):
        return {
            "_id": "user-123",
            "name": "Jane Doe",
            "email": "jane@example.com",
            "role": "customer",
            "is_active": True,
            "password_hash": "hashed",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

    async def fake_update_last_login(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr("app.routers.auth.verify_password", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.routers.auth.update_last_login", fake_update_last_login)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["user"]["full_name"] == "Jane Doe"


def test_login_handles_legacy_user_doc_with_non_string_timestamps(client, monkeypatch):
    async def fake_get_user_by_email(*args, **kwargs):
        return {
            "_id": "user-123",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "role": "customer",
            "is_active": True,
            "password_hash": "hashed",
            "created_at": object(),
            "updated_at": object(),
        }

    async def fake_update_last_login(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr("app.routers.auth.verify_password", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.routers.auth.update_last_login", fake_update_last_login)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["user"]["email"] == "jane@example.com"


def test_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_register_allows_localhost_cors_preflight(client):
    response = client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
