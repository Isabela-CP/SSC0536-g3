from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from app import main


@pytest.fixture
def env(write_env, monkeypatch):
    monkeypatch.setattr(main, "DEMO_USERS", deepcopy(main.DEMO_USERS))
    monkeypatch.setattr(main, "TOKENS", main.TOKENS.copy())
    for name in ("INVITES", "SURVEYS", "OCCUPANCY_RESPONSES", "REPORTS"):
        monkeypatch.setattr(main, name, [])
    return write_env


def account(env, email="nova@example.test", role="HOTEL"):
    body = {"nome": "Nova conta", "email": email, "perfil": role}
    if role == "HOTEL":
        body["id_estabelecimento"] = env.items[0]["id_estabelecimento"]
    response = env.client.post("/usuarios", json=body)
    assert response.status_code == 201
    return body


def research(env, **changes):
    body = {"titulo": "Ocupação de novembro", "tipo": "CONSOLIDADO", "periodo_inicio": "2026-11-01", "periodo_fim": "2026-11-30", "estabelecimentos": [env.items[0]["id_estabelecimento"]]}
    return env.client.post("/pesquisas-ocupacao", json={**body, **changes})


def test_invitation_activation_login_and_logout(env):
    body = account(env)
    invited = env.client.post("/convites", json={"email": body["email"]})
    assert invited.status_code == 201
    assert "token" not in invited.json()
    token = main.INVITES[0]["token"]
    path = f'/convites/{invited.json()["id_convite"]}/aceitacao'
    assert env.client.post(path, json={"token": token, "senha": ""}).status_code == 422
    assert env.client.post(path, json={"token": token, "senha": "nova-senha"}).status_code == 200
    assert env.client.post(path, json={"token": token, "senha": "nova-senha"}).status_code == 409
    login = env.client.post("/auth/login", json={"email": body["email"], "senha": "nova-senha"})
    assert login.status_code == 200
    assert login.json()["usuario"]["id_estabelecimento"] == body["id_estabelecimento"]
    headers = {"Authorization": f'Bearer {login.json()["access_token"]}'}
    assert env.client.get("/perfil", headers=headers).status_code == 200
    assert env.client.post("/auth/logout", headers=headers).status_code == 204
    assert env.client.get("/perfil", headers=headers).status_code == 401


def test_expired_and_invalid_invitation(env):
    account(env)
    invite = env.client.post("/convites", json={"email": "nova@example.test"}).json()
    path = f'/convites/{invite["id_convite"]}/aceitacao'
    assert env.client.post(path, json={"token": "incorreto", "senha": "teste"}).status_code == 404
    main.INVITES[0]["expira_em"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert env.client.post(path, json={"token": main.INVITES[0]["token"], "senha": "teste"}).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"email": None, "senha": "x"}, {"email": "marina.admin@example.test", "senha": "incorreta"}])
def test_invalid_login(env, payload):
    assert env.client.post("/auth/login", json=payload).status_code == 401


def test_profile_email_updates_session_index(env):
    result = env.client.patch("/perfil", json={"nome": "Nome atualizado", "email": " NOVO@EXAMPLE.TEST "})
    assert result.status_code == 200
    assert result.json()["email"] == "novo@example.test"
    assert env.client.get("/perfil").json()["nome"] == "Nome atualizado"
    assert env.client.post("/auth/login", json={"email": "novo@example.test", "senha": "admin-demo"}).status_code == 200
    assert env.client.post("/auth/login", json={"email": "marina.admin@example.test", "senha": "admin-demo"}).status_code == 401


@pytest.mark.parametrize("payload", [{}, {"nome": ""}, {"email": "invalido"}, {"perfil": "ADMINISTRADOR"}, {"senha": "nova"}])
def test_invalid_profile_patch(env, payload):
    assert env.client.patch("/perfil", json=payload).status_code == 422


def test_duplicate_email_and_hotel_association(env):
    assert env.client.patch("/perfil", json={"email": "rafael.consulta@example.test"}).status_code == 409
    response = env.client.get("/perfil", headers=env.headers("HOTEL"))
    assert response.json()["id_estabelecimento"] == env.items[0]["id_estabelecimento"]
    assert env.client.post("/usuarios", json={"nome": "Hotel", "email": "hotel@example.test", "perfil": "HOTEL"}).status_code == 422
    assert env.client.post("/usuarios", json={"nome": "Inválida", "email": "errado", "perfil": "GESTOR"}).status_code == 422
    for role in ("EDITOR", "GESTOR", "HOTEL"):
        assert env.client.post("/usuarios", json={"nome": "Conta", "email": "conta@example.test", "perfil": "GESTOR"}, headers=env.headers(role)).status_code == 403


@pytest.mark.parametrize("change", [{"tipo": "INVALIDO"}, {"titulo": ""}, {"periodo_inicio": "2026-12-01"}, {"periodo_fim": "invalida"}, {"estabelecimentos": []}, {"estabelecimentos": ["inexistente"]}])
def test_survey_validation(env, change):
    assert research(env, **change).status_code == 422
    assert main.SURVEYS == []


def test_survey_permissions_partial_updates_and_closing(env):
    created = research(env)
    assert created.status_code == 201
    id = created.json()["id_pesquisa"]
    assert env.client.patch(f"/pesquisas-ocupacao/{id}", json={"titulo": "Outro título"}).status_code == 200
    assert env.client.patch(f"/pesquisas-ocupacao/{id}", json={"periodo_inicio": "2026-12-01"}).status_code == 422
    assert env.client.post("/pesquisas-ocupacao", json={}, headers=env.headers("GESTOR")).status_code == 403
    assert env.client.post(f"/pesquisas-ocupacao/{id}/encerramento").status_code == 200
    assert env.client.patch(f"/pesquisas-ocupacao/{id}", json={"titulo": "Bloqueado"}).status_code == 409
    assert env.client.post(f"/pesquisas-ocupacao/{id}/encerramento").status_code == 409
    assert [event["acao"] for event in env.audit] == ["PESQUISA_CRIADA", "PESQUISA_ATUALIZADA", "PESQUISA_ENCERRADA"]


def test_hotel_pending_response_and_isolation(env):
    created = research(env).json()
    other = research(env, estabelecimentos=[env.items[1]["id_estabelecimento"]]).json()
    headers = env.headers("HOTEL")
    assert len(env.client.get("/pesquisas-ocupacao", headers=headers).json()["data"]) == 1
    assert len(env.client.get("/pesquisas-ocupacao/pendentes", headers=headers).json()["data"]) == 1
    assert env.client.post(f'/pesquisas-ocupacao/{other["id_pesquisa"]}/respostas', json={"taxa_ocupacao": 50}, headers=headers).status_code == 403
    response = env.client.post(f'/pesquisas-ocupacao/{created["id_pesquisa"]}/respostas', json={"taxa_ocupacao": 75.5}, headers=headers)
    assert response.status_code == 201
    assert response.json()["id_estabelecimento"] == env.items[0]["id_estabelecimento"]
    assert env.client.post(f'/pesquisas-ocupacao/{created["id_pesquisa"]}/respostas', json={"taxa_ocupacao": 50}, headers=headers).status_code == 409
    assert env.client.get("/pesquisas-ocupacao/pendentes", headers=headers).json()["data"] == []
    assert len(env.client.get("/respostas-ocupacao/historico", headers=headers).json()["data"]) == 1


@pytest.mark.parametrize("value", [-1, 101, True, None, "50"])
def test_invalid_occupancy(env, value):
    id = research(env).json()["id_pesquisa"]
    assert env.client.post(f"/pesquisas-ocupacao/{id}/respostas", json={"taxa_ocupacao": value}, headers=env.headers("HOTEL")).status_code == 422
    assert main.OCCUPANCY_RESPONSES == []
