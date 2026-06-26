"""Task 0 acceptance: /healthz returns 200 with {"status": "ok"}.

Must run with no external services and without importing Settings, so it
needs no environment variables set.
"""

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
