from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_list_establishments_uses_contract_shape():
    response = client.get("/estabelecimentos", params={"page_size": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 4
    assert len(body["data"]) == 2
