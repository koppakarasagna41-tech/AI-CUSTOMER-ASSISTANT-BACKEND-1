from pathlib import Path
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from app.main import create_app

load_dotenv(dotenv_path=Path('.env'))
app = create_app()
with TestClient(app) as client:
    response = client.post('/api/v1/auth/login', json={
        'email': 'koppakarasagna41@gmail.com',
        'password': 'rasagna@A3',
    })
    print('status', response.status_code)
    print(response.text)
