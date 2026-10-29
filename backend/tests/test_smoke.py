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


def test_list_categories_returns_seed_categories():
    response = client.get("/categorias-estabelecimento")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert len(body["data"]) > 0


def test_openapi_contract_is_exposed():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "openapi" in spec
    assert "/estabelecimentos" in spec["paths"]

