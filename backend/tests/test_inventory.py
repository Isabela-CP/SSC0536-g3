import copy
import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app import main
from app.inventory import JsonInventoryRepository


@pytest.fixture
def seed():
    with main.SEED_FILE.open(encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture
def contract():
    with main.OPENAPI_FILE.open(encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture
def client():
    with TestClient(main.app, headers={"Authorization": "Bearer gestor-token"}) as client:
        yield client


@pytest.fixture
def hotel(client, monkeypatch, seed):
    account = seed["contas_empresario"][0]
    user = {"id_usuario": account["id_conta"], "email": account["email"],
            "perfil": "HOTEL", "ativo": True,
            "id_estabelecimento": account["id_estabelecimento"]}
    monkeypatch.setitem(main.DEMO_USERS, user["email"], user)
    monkeypatch.setitem(main.TOKENS, "test-hotel-token", user["email"])
    client.headers["Authorization"] = "Bearer test-hotel-token"
    return client, user


def validate_response(contract, path, response):
    schema = contract["paths"][path]["get"]["responses"][str(response.status_code)]["content"]["application/json"]["schema"]
    validator = Draft202012Validator({**schema, "components": contract["components"]},
                                    format_checker=FormatChecker())
    validator.validate(response.json())


def ids(items):
    return [item["id_estabelecimento"] for item in items]


def test_default_list(client, seed, contract):
    response = client.get("/estabelecimentos")
    assert response.status_code == 200
    validate_response(contract, "/estabelecimentos", response)
    expected = sorted(seed["estabelecimentos"], key=lambda item: item["nome_fantasia"].casefold())
    assert ids(response.json()["data"]) == ids(expected)
    assert response.json()["pagination"] == {"page": 1, "page_size": 20, "total": len(expected), "total_pages": 1}
    assert "documentos" not in response.json()["data"][0]


@pytest.mark.parametrize("field", ["nome_fantasia", "razao_social", "cnpj"])
def test_search(client, seed, field):
    item = seed["estabelecimentos"][0]
    response = client.get("/estabelecimentos", params={"busca": item[field].upper()})
    assert response.status_code == 200
    assert ids(response.json()["data"]) == [item["id_estabelecimento"]]


@pytest.mark.parametrize("params", [
    {"id_categoria": 1}, {"id_categoria": 999},
    {"status": "ATIVO"}, {"status": "INATIVO"},
    {"cadastur_status": "OBRIGATORIO"}, {"cadastur_status": "OPCIONAL"},
    {"cadastur_status": "NAO_CONSTA"},
    {"aceita_pesquisas": True}, {"aceita_pesquisas": False},
    {"busca": "hotel", "status": "INATIVO", "id_categoria": 1,
     "cadastur_status": "OPCIONAL", "aceita_pesquisas": False},
    {"busca": "hotel", "status": "ATIVO", "aceita_pesquisas": False},
])
def test_filters(client, seed, params):
    expected = seed["estabelecimentos"]
    for field, value in params.items():
        if field == "busca":
            expected = [item for item in expected if value in item["nome_fantasia"].casefold()]
        else:
            expected = [item for item in expected if item[field] == value]
    expected = sorted(expected, key=lambda item: item["nome_fantasia"].casefold())
    response = client.get("/estabelecimentos", params=params)
    assert response.status_code == 200
    assert ids(response.json()["data"]) == ids(expected)
    assert response.json()["pagination"]["total"] == len(expected)


@pytest.mark.parametrize("field", ["nome_fantasia", "criado_em", "atualizado_em"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sort_filter_and_pagination(client, seed, field, order):
    expected = [item for item in seed["estabelecimentos"] if item["status"] == "ATIVO"]
    expected.sort(key=lambda item: item[field], reverse=order == "desc")
    result = []
    for page in range(1, len(expected) + 1):
        response = client.get("/estabelecimentos", params={
            "status": "ATIVO", "ordenar_por": field, "ordem": order,
            "page": page, "page_size": 1,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["pagination"] == {"page": page, "page_size": 1,
                                      "total": len(expected), "total_pages": len(expected)}
        result.extend(body["data"])
    assert ids(result) == ids(expected)


@pytest.mark.parametrize("params", [{"page": 100}, {"busca": "inexistente"}])
def test_empty_page(client, params):
    response = client.get("/estabelecimentos", params=params)
    assert response.status_code == 200
    assert response.json()["data"] == []
    if "busca" in params:
        assert response.json()["pagination"]["total"] == 0
        assert response.json()["pagination"]["total_pages"] == 1


@pytest.mark.parametrize("params", [
    {"busca": "x" * 121}, {"id_categoria": 0}, {"id_categoria": "abc"},
    {"status": "INVALIDO"}, {"cadastur_status": "INVALIDO"},
    {"aceita_pesquisas": "talvez"}, {"page": 0}, {"page": "abc"},
    {"page_size": 0}, {"page_size": 101},
    {"ordenar_por": "cnpj"}, {"ordem": "DESC"},
])
def test_invalid_parameters(client, contract, params):
    response = client.get("/estabelecimentos", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    validate_response(contract, "/estabelecimentos", response)


def test_parameter_boundaries(client):
    response = client.get("/estabelecimentos", params={"busca": "x" * 120, "page_size": 100})
    assert response.status_code == 200


def test_categories(client, seed, contract):
    response = client.get("/categorias-estabelecimento")
    assert response.json() == {"data": seed["categorias_estabelecimento"]}
    validate_response(contract, "/categorias-estabelecimento", response)


def test_details_and_documents(client, seed, contract):
    for item in seed["estabelecimentos"]:
        path = f'/estabelecimentos/{item["id_estabelecimento"]}'
        detail = client.get(path)
        assert detail.status_code == 200
        assert detail.json() == item
        validate_response(contract, "/estabelecimentos/{id_estabelecimento}", detail)
        documents = client.get(path + "/documentos")
        assert documents.status_code == 200
        assert documents.json() == {"data": item["documentos"]}
        validate_response(contract, "/estabelecimentos/{id_estabelecimento}/documentos", documents)


@pytest.mark.parametrize("suffix", ["", "/documentos"])
def test_not_found(client, contract, suffix):
    response = client.get("/estabelecimentos/00000000-0000-4000-8000-000000000000" + suffix)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    validate_response(contract, "/estabelecimentos/{id_estabelecimento}" + suffix, response)


@pytest.fixture
def paths(seed):
    detail = f'/estabelecimentos/{seed["estabelecimentos"][0]["id_estabelecimento"]}'
    return ["/categorias-estabelecimento", "/estabelecimentos", detail, detail + "/documentos"]


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer invalid", "Bearer "])
def test_unauthorized(paths, authorization):
    with TestClient(main.app) as client:
        headers = {} if authorization is None else {"Authorization": authorization}
        for path in paths:
            response = client.get(path, headers=headers)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHORIZED"
            assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["admin-token", "gestor-token", "editor-token"])
def test_internal_roles(client, paths, token):
    for path in paths:
        assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_inactive_user(client, paths, monkeypatch):
    original = main.DEMO_USERS[main.TOKENS["gestor-token"]]
    monkeypatch.setitem(main.DEMO_USERS, original["email"], {**original, "ativo": False})
    for path in paths:
        assert client.get(path).status_code == 401


def test_forbidden_role(client, paths, monkeypatch):
    original = main.DEMO_USERS[main.TOKENS["gestor-token"]]
    monkeypatch.setitem(main.DEMO_USERS, original["email"], {**original, "perfil": "DESCONHECIDO"})
    for path in paths:
        response = client.get(path)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_hotel_isolation(hotel, seed):
    client, user = hotel
    own_id = user["id_estabelecimento"]
    other_id = seed["estabelecimentos"][1]["id_estabelecimento"]
    response = client.get("/estabelecimentos", params={"id_estabelecimento": other_id})
    assert ids(response.json()["data"]) == [own_id]
    assert response.json()["pagination"]["total"] == 1
    assert client.get("/categorias-estabelecimento").status_code == 200
    for suffix in ("", "/documentos"):
        assert client.get(f"/estabelecimentos/{own_id}" + suffix).status_code == 200
        response = client.get(f"/estabelecimentos/{other_id}" + suffix)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    response = client.get("/estabelecimentos", params={
        "busca": seed["estabelecimentos"][1]["cnpj"],
        "ordenar_por": "criado_em", "ordem": "desc", "page_size": 1,
    })
    assert response.json()["data"] == []
    assert response.json()["pagination"]["total"] == 0


@pytest.mark.parametrize("association", [None, ""])
def test_hotel_without_association_is_forbidden(hotel, paths, association):
    client, user = hotel
    user["id_estabelecimento"] = association
    for path in paths:
        assert client.get(path).status_code == 403


@pytest.mark.parametrize("field", ["nome_fantasia", "criado_em", "atualizado_em"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_deterministic_ties(client, seed, tmp_path, field, order):
    data = copy.deepcopy(seed)
    for item in data["estabelecimentos"]:
        item[field] = data["estabelecimentos"][0][field]
    data["estabelecimentos"].reverse()
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    main.app.dependency_overrides[main.inventory_repository] = lambda: JsonInventoryRepository(path)
    try:
        result = []
        for page in range(1, len(data["estabelecimentos"]) + 1):
            response = client.get("/estabelecimentos", params={
                "ordenar_por": field, "ordem": order, "page": page, "page_size": 1,
            })
            assert response.status_code == 200
            result.extend(response.json()["data"])
        assert ids(result) == sorted(ids(seed["estabelecimentos"]))
    finally:
        main.app.dependency_overrides.pop(main.inventory_repository, None)


def test_nullable_search_fields(client, seed, tmp_path):
    data = copy.deepcopy(seed)
    data["estabelecimentos"][0].update(razao_social=None, cnpj=None)
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    main.app.dependency_overrides[main.inventory_repository] = lambda: JsonInventoryRepository(path)
    try:
        response = client.get("/estabelecimentos", params={"busca": "Hotel Serra Azul"})
        assert response.status_code == 200
        assert ids(response.json()["data"]) == ids(data["estabelecimentos"][:1])
    finally:
        main.app.dependency_overrides.pop(main.inventory_repository, None)


def test_hotel_login_uses_seed_association(client, seed):
    for account in seed["contas_empresario"]:
        response = client.post("/auth/login", json={"email": account["email"], "senha": "hotel-demo"})
        assert response.status_code == 200
        assert response.json()["usuario"]["perfil"] == "HOTEL"
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        listing = client.get("/estabelecimentos", headers=headers)
        assert listing.status_code == 200
        assert ids(listing.json()["data"]) == [account["id_estabelecimento"]]


def test_date_order_uses_instants(client, seed, tmp_path):
    data = copy.deepcopy(seed)
    data["estabelecimentos"] = data["estabelecimentos"][:2]
    data["estabelecimentos"][0]["criado_em"] = "2026-01-01T01:00:00+02:00"
    data["estabelecimentos"][1]["criado_em"] = "2026-01-01T00:00:00Z"
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    main.app.dependency_overrides[main.inventory_repository] = lambda: JsonInventoryRepository(path)
    try:
        response = client.get("/estabelecimentos", params={"ordenar_por": "criado_em"})
        assert response.status_code == 200
        assert ids(response.json()["data"]) == ids(data["estabelecimentos"])
    finally:
        main.app.dependency_overrides.pop(main.inventory_repository, None)
