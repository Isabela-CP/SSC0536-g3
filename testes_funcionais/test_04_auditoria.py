"""UC03 — Registrar alteração no audit log (RF-03, RNF-05) e UC08 — Consultar audit log (RF-03)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.postgres_portal import PostgresPortal
from apoio_api import CONTAS, SERRA_AZUL, novo_estabelecimento


def _registro(api, acao, id_entidade):
    registros = [r for r in api.auditoria(acao) if r["id_entidade"] == str(id_entidade)]
    assert len(registros) == 1, f"esperado 1 registro {acao} para {id_entidade}, obtido {len(registros)}"
    return registros[0]


@pytest.mark.uc("UC03")
def test_ft_aud_01_criacao_registrada(api):
    """CF — criação gera registro com autor, data/hora, sem valor anterior e com valor novo."""
    antes = datetime.now(timezone.utc) - timedelta(seconds=5)
    criado = api.como("ADMINISTRADOR").post("/estabelecimentos", json=novo_estabelecimento()).json()
    registro = _registro(api, "ESTABELECIMENTO_CRIADO", criado["id_estabelecimento"])
    assert registro["usuario"] == CONTAS["ADMINISTRADOR"] and registro["entidade"] == "ESTABELECIMENTO"
    assert registro["antes"] is None and registro["depois"]["nome_fantasia"] == "Hotel Funcional"
    assert datetime.fromisoformat(registro["criado_em"]) >= antes


@pytest.mark.uc("UC03")
def test_ft_aud_02_edicao_registra_valor_anterior_e_novo(api):
    """CF — edição registra o autor real (EDITOR) e os valores anterior e posterior do campo."""
    api.como("EDITOR").patch(f"/estabelecimentos/{SERRA_AZUL}", json={"telefone_comercial": "+55 17 90000-0000"})
    registro = _registro(api, "ESTABELECIMENTO_ATUALIZADO", SERRA_AZUL)
    assert registro["usuario"] == CONTAS["EDITOR"]
    assert registro["antes"]["telefone_comercial"] == "+55 16 3333-1000"
    assert registro["depois"]["telefone_comercial"] == "+55 17 90000-0000"


@pytest.mark.uc("UC03")
def test_ft_aud_03_inativacao_registrada(api):
    """CF — inativação registra status anterior/posterior e o motivo."""
    api.como("ADMINISTRADOR").post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json={"motivo_inativacao": "Fechou"})
    registro = _registro(api, "ESTABELECIMENTO_INATIVADO", SERRA_AZUL)
    assert registro["antes"]["status"] == "ATIVO"
    assert registro["depois"]["status"] == "INATIVO" and registro["depois"]["motivo_inativacao"] == "Fechou"


@pytest.mark.uc("UC03")
def test_ft_aud_04_operacoes_de_conta_registradas(api):
    """CF — criação e inativação de conta também entram no log (UC03 incluído em UC07)."""
    admin = api.como("ADMINISTRADOR")
    usuario = admin.post("/usuarios", json={"nome": "Nova Estagiária", "email": "nova@example.test", "perfil": "EDITOR"}).json()
    admin.post("/usuarios/5/inativacao")
    assert _registro(api, "USUARIO_CRIADO", usuario["id_usuario"])["depois"]["perfil"] == "EDITOR"
    inativacao = _registro(api, "USUARIO_INATIVADO", 5)
    assert inativacao["antes"] == {"status": "ATIVO"} and inativacao["depois"] == {"status": "INATIVO"}


@pytest.mark.uc("UC08")
def test_ft_aud_05_filtros_por_acao_autor_e_periodo(api):
    """CF UC08 — filtros por ação, autor e período restringem o resultado."""
    api.como("EDITOR").patch(f"/estabelecimentos/{SERRA_AZUL}", json={"telefone_comercial": "+55 17 1"})
    admin = api.como("ADMINISTRADOR")
    por_autor = admin.get("/auditoria", params={"id_usuario": 4}).json()["data"]
    assert por_autor and all(r["id_usuario"] == 4 for r in por_autor)
    por_acao = admin.get("/auditoria", params={"acao": "ESTABELECIMENTO_ATUALIZADO"}).json()["data"]
    assert por_acao and all(r["acao"] == "ESTABELECIMENTO_ATUALIZADO" for r in por_acao)
    agora = datetime.now(timezone.utc)
    recente = admin.get("/auditoria", params={"data_inicio": (agora - timedelta(minutes=1)).isoformat()}).json()["data"]
    assert [r["acao"] for r in recente] == ["ESTABELECIMENTO_ATUALIZADO"]
    futuro = admin.get("/auditoria", params={"data_inicio": (agora + timedelta(days=1)).isoformat()}).json()["data"]
    assert futuro == []


@pytest.mark.uc("UC08")
def test_ft_aud_06_periodo_invertido(api):
    """EX — data final anterior à inicial: 422."""
    resposta = api.como("ADMINISTRADOR").get("/auditoria", params={
        "data_inicio": "2026-11-10T00:00:00+00:00", "data_fim": "2026-11-01T00:00:00+00:00"})
    assert resposta.status_code == 422


@pytest.mark.uc("UC08")
def test_ft_aud_07_filtro_por_empresa(api):
    """CF UC08 — filtrar o histórico por estabelecimento."""
    api.como("EDITOR").patch(f"/estabelecimentos/{SERRA_AZUL}", json={"telefone_comercial": "+55 17 1"})
    api.como("ADMINISTRADOR").post("/usuarios", json={"nome": "X", "email": "x@example.test", "perfil": "GESTOR"})
    filtrado = api.como("ADMINISTRADOR").get("/auditoria", params={"id_entidade": SERRA_AZUL}).json()["data"]
    assert filtrado and all(r["id_entidade"] == SERRA_AZUL for r in filtrado)


@pytest.mark.uc("UC08")
@pytest.mark.parametrize("perfil", ["EDITOR", "GESTOR", "HOTEL"])
def test_ft_aud_08_somente_admin_consulta(api, perfil):
    """EX — a consulta ao log é restrita ao ADMINISTRADOR."""
    assert api.como(perfil).get("/auditoria").status_code == 403


@pytest.mark.uc("UC03")
@pytest.mark.parametrize("metodo", ["put", "patch", "delete"])
def test_ft_aud_09_log_imutavel(api, metodo):
    """EX — o log não aceita alteração nem exclusão pela API."""
    admin = api.como("ADMINISTRADOR")
    total = len(api.auditoria())
    assert getattr(admin, metodo)("/auditoria").status_code == 405
    assert len(api.auditoria()) == total


@pytest.mark.uc("UC03")
def test_ft_aud_10_falha_no_log_desfaz_operacao(api, monkeypatch):
    """EX 3a — se o log não puder ser gravado, a alteração é desfeita e o usuário recebe erro."""
    token = api.anon.post("/auth/login", json={"email": CONTAS["ADMINISTRADOR"], "senha": "admin-demo"}).json()["access_token"]
    cliente = TestClient(main.app, raise_server_exceptions=False, headers={"Authorization": "Bearer " + token})
    original = PostgresPortal.audit

    def audit_com_falha(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("falha simulada na gravação do log")

    monkeypatch.setattr(PostgresPortal, "audit", audit_com_falha)
    criacao = cliente.post("/estabelecimentos", json=novo_estabelecimento())
    inativacao = cliente.post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json={"motivo_inativacao": "Teste"})
    conta = cliente.post("/usuarios", json={"nome": "Sem Log", "email": "semlog@example.test", "perfil": "EDITOR"})
    monkeypatch.setattr(PostgresPortal, "audit", original)

    assert criacao.status_code >= 500 and inativacao.status_code >= 500 and conta.status_code >= 500
    assert api.sql("SELECT count(*) AS n FROM estabelecimentos WHERE nome_fantasia='Hotel Funcional'")[0]["n"] == 0
    assert api.sql("SELECT status FROM estabelecimentos WHERE id_estabelecimento=%s", (SERRA_AZUL,))[0]["status"] == "ATIVO"
    assert api.sql("SELECT count(*) AS n FROM usuarios WHERE email='semlog@example.test'")[0]["n"] == 0
