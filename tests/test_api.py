import os
from pathlib import Path

os.environ["SYNCPROOF_DB_PATH"] = str(Path("data/test-syncproof.db"))

from fastapi.testclient import TestClient
from app.main import app


def test_health():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
