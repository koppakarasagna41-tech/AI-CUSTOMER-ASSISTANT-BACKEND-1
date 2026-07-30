import json
import uuid
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    email = f"copilot-{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Copilot Test",
            "email": email,
            "password": "ShortPass123",
            "role": "customer",
        },
    )
    print("register_status=", reg.status_code)
    print("register_body=", json.dumps(reg.json(), indent=2, ensure_ascii=False))

    if reg.status_code == 201:
        token = reg.json()["data"]["tokens"]["access_token"]
        chat = client.post(
            "/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Hello, is AI working?", "title": "Test chat"},
        )
        print("chat_status=", chat.status_code)
        print("chat_body=", json.dumps(chat.json(), indent=2, ensure_ascii=False))
    else:
        print("registration failed, skipping chat test")
