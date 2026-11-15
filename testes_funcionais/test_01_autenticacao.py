"""UC00 — Autenticar no sistema (RF-06, RNF-01) e controle de sessão."""
import pytest

from apoio_api import CONTAS, SENHAS, defeito, erro

pytestmark = pytest.mark.uc("UC00")

ROTAS_INTERNAS = ["/perfil", "/usuarios", "/auditoria", "/dashboard", "/estabelecimentos",
                  "/categorias-estabelecimento", "/pesquisas-ocupacao", "/respostas-ocupacao/historico"]


@pytest.mark.parametrize("perfil", ["ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL"])
def test_ft_aut_01_login_valido_carrega_perfil(api, perfil):
    """CF — credenciais válidas iniciam sessão com o perfil correto (fluxo principal 1–5)."""
    resposta = api.anon.post("/auth/login", json={"email": CONTAS[perfil], "senha": SENHAS[perfil]})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token_type"] == "Bearer" and len(corpo["access_token"]) >= 32
    assert corpo["usuario"]["perfil"] == perfil and corpo["usuario"]["ativo"] is True
    assert 60 <= corpo["expires_in"] <= 86400
    perfil_atual = api.anon.get("/perfil", headers={"Authorization": "Bearer " + corpo["access_token"]})
    assert perfil_atual.json()["email"] == CONTAS[perfil]


def test_ft_aut_02_email_normalizado(api):
    """CF — e-mail com maiúsculas e espaços é aceito (mesma conta)."""
    resposta = api.anon.post("/auth/login", json={"email": "  MARINA.Admin@Example.TEST ", "senha": "admin-demo"})
    assert resposta.status_code == 200


def test_ft_aut_03_credenciais_invalidas_mensagem_neutra(api):
    """EX 3a — senha errada e e-mail inexistente: 401 com a mesma mensagem (anti-enumeração)."""
    senha_errada = api.anon.post("/auth/login", json={"email": CONTAS["EDITOR"], "senha": "senha-errada"})
    inexistente = api.anon.post("/auth/login", json={"email": "ninguem@example.test", "senha": "senha-errada"})
    assert senha_errada.status_code == inexistente.status_code == 401
    assert erro(senha_errada).code == erro(inexistente).code == "INVALID_CREDENTIALS"
    assert erro(senha_errada).message == erro(inexistente).message
    assert "access_token" not in senha_errada.json()


@pytest.mark.parametrize("conta", ["GESTOR_INATIVO", "EDITOR_PENDENTE"])
def test_ft_aut_04_conta_inativa_ou_pendente_nao_entra(api, conta):
    """EX — conta INATIVA ou PENDENTE (convite não aceito) não autentica, mesmo com senha do seed."""
    senha = SENHAS[conta.split("_")[0]]
    resposta = api.anon.post("/auth/login", json={"email": CONTAS[conta], "senha": senha})
    assert resposta.status_code == 401


@pytest.mark.parametrize("rota", ROTAS_INTERNAS)
def test_ft_aut_05_rotas_internas_exigem_sessao(api, rota):
    """EX — sem token, nenhuma rota interna devolve dados."""
    resposta = api.anon.get(rota)
    assert resposta.status_code == 401
    assert "data" not in resposta.json()


def test_ft_aut_06_token_forjado_rejeitado(api):
    """EX — token desconhecido ou esquema diferente de Bearer é recusado."""
    for cabecalho in ("Bearer token-inventado-123", "Basic YWRtaW46YWRtaW4=", "admin-token"):
        assert api.anon.get("/perfil", headers={"Authorization": cabecalho}).status_code == 401


def test_ft_aut_07_logout_revoga_sessao(api):
    """CF — após logout, o mesmo token deixa de valer."""
    cliente = api.como("EDITOR")
    assert cliente.get("/perfil").status_code == 200
    assert cliente.post("/auth/logout").status_code == 204
    assert cliente.get("/perfil").status_code == 401


def test_ft_aut_08_sessao_expirada(api):
    """EX — sessão com validade vencida é recusada pelo servidor."""
    cliente = api.como("GESTOR")
    api.sql("UPDATE sessoes SET expira_em = now() - interval '1 second'")
    assert cliente.get("/estabelecimentos").status_code == 401


@defeito("DF-01", "Não há limitação de tentativas: após 5 senhas erradas, a credencial correta ainda autentica (UC11 3c).")
def test_ft_aut_09_bloqueio_apos_tentativas_invalidas(api):
    """EX 3c — várias tentativas inválidas devem bloquear temporariamente o acesso."""
    for _ in range(5):
        assert api.anon.post("/auth/login", json={"email": CONTAS["HOTEL"], "senha": "errada!!"}).status_code == 401
    durante_bloqueio = api.anon.post("/auth/login", json={"email": CONTAS["HOTEL"], "senha": SENHAS["HOTEL"]})
    assert durante_bloqueio.status_code in (423, 429)
