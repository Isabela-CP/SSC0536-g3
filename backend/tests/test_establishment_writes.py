from concurrent.futures import ThreadPoolExecutor

import pytest


ROOT = "/estabelecimentos"
DETAIL = ROOT + "/{id_estabelecimento}"
MISSING = "00000000-0000-4000-8000-000000000000"


def test_create_minimal_and_read(write_env, create_payload):
    env = write_env
    response = env.client.post(ROOT, json=create_payload)
    assert response.status_code == 201
    env.validate(response, ROOT, "post")
    item = response.json()
    assert item["status"] == "ATIVO"
    assert item["documentos"] == []
    assert item["meio_hospedagem"] is None
    assert item["infraestrutura"] is None
    assert item["aceita_pesquisas"] is True
    assert item["possui_cadastur"] is False
    assert item["cadastur_status"] == "OBRIGATORIO"
    assert env.client.get(ROOT + "/" + item["id_estabelecimento"]).json() == item
    assert env.client.get(ROOT, params={"busca": "Hotel Novo"}).json()["pagination"]["total"] == 1
    assert len(env.audit) == 1
    assert env.audit[0]["acao"] == "ESTABELECIMENTO_CRIADO"
    assert env.audit[0]["antes"] is None
    assert env.audit[0]["depois"] == item


@pytest.mark.parametrize("field", ["id_categoria", "nome_fantasia", "razao_social", "cnpj", "endereco"])
def test_missing_required_field(write_env, create_payload, field):
    create_payload.pop(field)
    response = write_env.client.post(ROOT, json=create_payload)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field
    write_env.validate(response, ROOT, "post")
    assert len(write_env.repository.establishments()) == len(write_env.items)
    assert write_env.audit == []


@pytest.mark.parametrize("changes", [
    {"cnpj": "00.000.000/0000-00"}, {"cnpj": "11.222.333/0001-80"},
    {"cnpj": "invalid"}, {"cnpj": "1122233300018"}, {"cnpj": None},
    {"razao_social": None}, {"id_categoria": 0}, {"id_categoria": 999},
    {"nome_fantasia": "a"}, {"endereco": "curt"}, {"email_comercial": "invalido"},
    {"latitude": 91}, {"longitude": -181}, {"aceita_pesquisas": None},
    {"aceita_pesquisas": "true"}, {"meio_hospedagem": {"total_leitos": -1}},
    {"infraestrutura": {"wifi": "sim"}},
    {"meio_hospedagem": {"formas_pagamento": ["PIX", "PIX"]}},
    {"meio_hospedagem": {"checkin_horario": "99:00:00"}},
    {"acessibilidade": {"possui_facilidade_pcd": "sim"}},
    {"status": "INATIVO"}, {"documentos": []},
])
def test_invalid_create(write_env, create_payload, changes):
    response = write_env.client.post(ROOT, json={**create_payload, **changes})
    assert response.status_code == 422
    write_env.validate(response, ROOT, "post")
    assert write_env.audit == []


@pytest.mark.parametrize("cnpj", ["11222333000181", "11.222.333/0001-81"])
def test_duplicate_cnpj(write_env, create_payload, cnpj):
    assert write_env.client.post(ROOT, json=create_payload).status_code == 201
    response = write_env.client.post(ROOT, json={**create_payload, "cnpj": cnpj})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    write_env.validate(response, ROOT, "post")
    assert len(write_env.audit) == 1


def test_concurrent_duplicate_create(write_env, create_payload):
    def create(_):
        return write_env.client.post(ROOT, json=create_payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == [201, 409]
    assert len(write_env.audit) == 1


def test_patch_partial_nested_and_null(write_env):
    env = write_env
    original = env.items[0]
    path = ROOT + "/" + original["id_estabelecimento"]
    response = env.client.patch(path, json={"bairro": None, "meio_hospedagem": {"total_uh": 99},
                                            "infraestrutura": {"wifi": False}, "aceita_pesquisas": False})
    assert response.status_code == 200
    env.validate(response, DETAIL, "patch")
    item = response.json()
    assert item["bairro"] is None
    assert item["aceita_pesquisas"] is False
    assert item["meio_hospedagem"]["total_uh"] == 99
    assert item["meio_hospedagem"]["total_leitos"] == original["meio_hospedagem"]["total_leitos"]
    assert item["infraestrutura"]["wifi"] is False
    assert item["cnpj"] == original["cnpj"]
    assert env.audit[-1]["antes"] == original
    assert env.audit[-1]["depois"] == item
    assert env.client.patch(path, json={"meio_hospedagem": None}).status_code == 200
    assert env.client.get(path).json()["meio_hospedagem"] is None
    assert env.audit[0]["depois"]["meio_hospedagem"]["total_uh"] == 99


@pytest.mark.parametrize("changes", [{}, {"nome_fantasia": None}, {"status": "INATIVO"},
                                    {"id_estabelecimento": MISSING}, {"infraestrutura": {"recepcao": None}}])
def test_invalid_patch(write_env, changes):
    response = write_env.client.patch(ROOT + "/" + write_env.items[0]["id_estabelecimento"], json=changes)
    assert response.status_code == 422
    assert write_env.audit == []


def test_patch_cnpj_duplicate_invalid_and_same(write_env, create_payload):
    env = write_env
    created = env.client.post(ROOT, json=create_payload).json()
    path = ROOT + "/" + env.items[0]["id_estabelecimento"]
    assert env.client.patch(path, json={"cnpj": created["cnpj"]}).status_code == 409
    assert env.client.patch(path, json={"cnpj": "11.222.333/0001-80"}).status_code == 422
    assert env.client.patch(ROOT + "/" + created["id_estabelecimento"], json={"cnpj": "11222333000181"}).status_code == 200
    assert env.client.patch(path, json={"razao_social": "Nova Razão Ltda."}).status_code == 200
    assert env.client.patch(path, json={"cnpj": None}).status_code == 200


@pytest.mark.parametrize("role", ["EDITOR", "HOTEL"])
@pytest.mark.parametrize("field", ["cnpj", "razao_social"])
@pytest.mark.parametrize("value", [None, "valor inválido"])
def test_protected_fields(write_env, role, field, value):
    env = write_env
    path = ROOT + "/" + env.items[0]["id_estabelecimento"]
    response = env.client.patch(path, json={field: value, "nome_fantasia": "Tentativa"}, headers=env.headers(role))
    assert response.status_code == 403
    env.validate(response, DETAIL, "patch")
    assert env.repository.establishment(env.items[0]["id_estabelecimento"]) == env.items[0]
    assert env.audit == []


@pytest.mark.parametrize("role", ["EDITOR", "HOTEL", "GESTOR"])
def test_create_admin_only(write_env, create_payload, role):
    assert write_env.client.post(ROOT, json=create_payload, headers=write_env.headers(role)).status_code == 403
    assert write_env.audit == []


@pytest.mark.parametrize("role", ["EDITOR", "HOTEL"])
def test_edit_allowed_and_hotel_scope(write_env, role):
    env = write_env
    own_id = env.items[0]["id_estabelecimento"]
    assert env.client.patch(ROOT + "/" + own_id, json={"nome_fantasia": "Atualizado"}, headers=env.headers(role)).status_code == 200
    other_id = env.items[1]["id_estabelecimento"]
    response = env.client.patch(ROOT + "/" + other_id, json={"bairro": "Novo"}, headers=env.headers(role))
    assert response.status_code == (403 if role == "HOTEL" else 200)


@pytest.mark.parametrize("suffix", ["inativacao", "reativacao"])
@pytest.mark.parametrize("role", ["EDITOR", "HOTEL", "GESTOR"])
def test_status_admin_only(write_env, suffix, role):
    env = write_env
    response = env.client.post(ROOT + "/" + env.items[0]["id_estabelecimento"] + "/" + suffix,
                               json={"motivo_inativacao": "Motivo de teste"}, headers=env.headers(role))
    assert response.status_code == 403
    assert env.audit == []


def test_status_transitions_and_audit_history(write_env):
    env = write_env
    original = env.items[0]
    path = ROOT + "/" + original["id_estabelecimento"]
    inactive = env.client.post(path + "/inativacao", json={"motivo_inativacao": "Encerramento temporário"})
    assert inactive.status_code == 200
    env.validate(inactive, DETAIL + "/inativacao", "post")
    assert inactive.json()["status"] == "INATIVO"
    assert inactive.json()["documentos"] == original["documentos"]
    conflict = env.client.post(path + "/inativacao", json={"motivo_inativacao": "Outro motivo"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ESTABELECIMENTO_JA_INATIVO"
    active = env.client.post(path + "/reativacao")
    assert active.status_code == 200
    env.validate(active, DETAIL + "/reativacao", "post")
    assert active.json()["status"] == "ATIVO"
    assert active.json()["motivo_inativacao"] is None
    conflict = env.client.post(path + "/reativacao")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ESTABELECIMENTO_JA_ATIVO"
    assert [event["acao"] for event in env.audit] == ["ESTABELECIMENTO_INATIVADO", "ESTABELECIMENTO_REATIVADO"]
    assert env.audit[0]["antes"] == original
    assert env.audit[0]["depois"]["motivo_inativacao"] == "Encerramento temporário"
    assert env.audit[1]["antes"]["status"] == "INATIVO"


@pytest.mark.parametrize("payload", [{}, {"motivo_inativacao": "ab"}, {"motivo_inativacao": "x" * 501},
                                     {"motivo_inativacao": None}])
def test_invalid_reason(write_env, payload):
    env = write_env
    response = env.client.post(ROOT + "/" + env.items[0]["id_estabelecimento"] + "/inativacao", json=payload)
    assert response.status_code == 422
    env.validate(response, DETAIL + "/inativacao", "post")
    assert env.audit == []


@pytest.mark.parametrize("length", [3, 500])
def test_reason_boundaries(write_env, length):
    env = write_env
    assert env.client.post(ROOT + "/" + env.items[0]["id_estabelecimento"] + "/inativacao",
                           json={"motivo_inativacao": "x" * length}).status_code == 200


@pytest.mark.parametrize("method,suffix,payload", [
    ("patch", "", {"nome_fantasia": "Teste"}),
    ("post", "/inativacao", {"motivo_inativacao": "Motivo"}), ("post", "/reativacao", None),
])
def test_not_found(write_env, method, suffix, payload):
    response = write_env.client.request(method, ROOT + "/" + MISSING + suffix, json=payload)
    assert response.status_code == 404
    write_env.validate(response, DETAIL + suffix, method)
    assert write_env.audit == []


def test_gestor_cannot_patch(write_env):
    env = write_env
    assert env.client.patch(ROOT + "/" + env.items[0]["id_estabelecimento"], json={"bairro": "Novo"},
                             headers=env.headers("GESTOR")).status_code == 403
    assert env.audit == []


def test_malformed_json(write_env):
    for method, path in [("post", ROOT), ("patch", ROOT + "/" + write_env.items[0]["id_estabelecimento"])]:
        response = write_env.client.request(method, path, content="{", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        write_env.validate(response, ROOT if method == "post" else DETAIL, method)


def test_write_unauthorized(write_env, create_payload):
    env = write_env
    env.client.headers.pop("Authorization")
    path = ROOT + "/" + env.items[0]["id_estabelecimento"]
    for method, endpoint, payload in [("post", ROOT, create_payload), ("patch", path, {"bairro": "Novo"}),
                                       ("post", path + "/inativacao", {"motivo_inativacao": "Teste"}),
                                       ("post", path + "/reativacao", None)]:
        response = env.client.request(method, endpoint, json=payload)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert env.audit == []
