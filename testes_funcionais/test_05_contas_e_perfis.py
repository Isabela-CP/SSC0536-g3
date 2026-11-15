"""UC07 — Gerenciar perfis de acesso (RF-06, RF-07, RNF-02), convites e senhas."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import main
from apoio_api import CONTAS, SERRA_AZUL, erro, nao_implementado

pytestmark = pytest.mark.uc("UC07")


def _parametros_do_link(link: str) -> dict:
    fragmento = urlsplit(link).fragment          # ex.: /ativar-convite?id=3&token=...
    return {k: v[0] for k, v in parse_qs(fragmento.partition("?")[2]).items()}


def _criar_e_ativar(api, email, perfil="EDITOR", senha="senha-segura-1", **extra):
    admin = api.como("ADMINISTRADOR")
    criado = admin.post("/usuarios", json={"nome": "Conta Teste", "email": email, "perfil": perfil, **extra})
    assert criado.status_code == 201, criado.text
    assert admin.post("/convites", json={"email": email}).status_code == 201
    link = _parametros_do_link(api.ultimo_link(email))
    ativacao = api.anon.post(f"/convites/{link['id']}/aceitacao", json={"token": link["token"], "senha": senha})
    assert ativacao.status_code == 200, ativacao.text
    return criado.json()


def test_ft_usr_01_criar_conta_fica_pendente(api):
    """CF — ADMIN cria conta EDITOR: aparece na lista como PENDENTE e ainda não entra."""
    admin = api.como("ADMINISTRADOR")
    criado = admin.post("/usuarios", json={"nome": "Beatriz Silva", "email": "beatriz@example.test", "perfil": "EDITOR"})
    assert criado.status_code == 201 and criado.json()["perfil"] == "EDITOR" and criado.json()["ativo"] is False
    lista = {u["email"]: u for u in admin.get("/usuarios").json()["data"]}
    assert lista["beatriz@example.test"]["status"] == "PENDENTE"
    assert api.anon.post("/auth/login", json={"email": "beatriz@example.test", "senha": "qualquer-senha"}).status_code == 401


def test_ft_usr_02_convite_por_email_ativa_e_permite_login(api):
    """CF — convite é enviado por e-mail; o link ativa a conta e o perfil é aplicado no login."""
    _criar_e_ativar(api, "beatriz@example.test", senha="nova-senha-123")
    cliente = api.login("beatriz@example.test", "nova-senha-123")
    assert cliente.get("/perfil").json()["perfil"] == "EDITOR"
    assert cliente.get("/usuarios").status_code == 403
    assert cliente.patch(f"/estabelecimentos/{SERRA_AZUL}", json={"telefone_comercial": "+55 1"}).status_code == 200


def test_ft_usr_03_convite_de_uso_unico_e_token_invalido(api):
    """EX — token errado: 404; convite já aceito: 409; reenvio cancela o convite anterior."""
    admin = api.como("ADMINISTRADOR")
    admin.post("/usuarios", json={"nome": "Conta", "email": "uso.unico@example.test", "perfil": "GESTOR"})
    admin.post("/convites", json={"email": "uso.unico@example.test"})
    primeiro = _parametros_do_link(api.ultimo_link("uso.unico@example.test"))
    admin.post("/convites", json={"email": "uso.unico@example.test"})
    segundo = _parametros_do_link(api.ultimo_link("uso.unico@example.test"))
    assert api.anon.post(f"/convites/{segundo['id']}/aceitacao", json={"token": "errado", "senha": "senha-ok-123"}).status_code == 404
    cancelado = api.anon.post(f"/convites/{primeiro['id']}/aceitacao", json={"token": primeiro["token"], "senha": "senha-ok-123"})
    assert cancelado.status_code == 409
    assert api.anon.post(f"/convites/{segundo['id']}/aceitacao", json={"token": segundo["token"], "senha": "senha-ok-123"}).status_code == 200
    assert api.anon.post(f"/convites/{segundo['id']}/aceitacao", json={"token": segundo["token"], "senha": "senha-ok-123"}).status_code == 409


@pytest.mark.parametrize("senha,esperado", [("1234567", 422), ("12345678", 200), ("x" * 128, 200), ("x" * 129, 422)])
def test_ft_usr_04_limites_de_senha(api, senha, esperado):
    """EX — valor limite da senha (8 a 128 caracteres) na ativação."""
    admin = api.como("ADMINISTRADOR")
    admin.post("/usuarios", json={"nome": "Conta", "email": "limite@example.test", "perfil": "GESTOR"})
    admin.post("/convites", json={"email": "limite@example.test"})
    link = _parametros_do_link(api.ultimo_link("limite@example.test"))
    resposta = api.anon.post(f"/convites/{link['id']}/aceitacao", json={"token": link["token"], "senha": senha})
    assert resposta.status_code == esperado


@pytest.mark.parametrize("email", [CONTAS["EDITOR"], "CAMILA.EDITORA@example.test"])
def test_ft_usr_05_email_duplicado(api, email):
    """EX — e-mail já cadastrado (inclusive com outra caixa): 409."""
    resposta = api.como("ADMINISTRADOR").post("/usuarios", json={"nome": "Dup", "email": email, "perfil": "GESTOR"})
    assert resposta.status_code == 409


@pytest.mark.parametrize("corpo,campo", [
    ({"perfil": "HOTEL"}, "id_estabelecimento"),
    ({"perfil": "EDITOR", "id_estabelecimento": SERRA_AZUL}, "id_estabelecimento"),
    ({"perfil": "SUPERUSUARIO"}, "perfil"),
    ({"perfil": "EDITOR", "email": "sem-arroba"}, "email")])
def test_ft_usr_06_dados_de_conta_invalidos(api, corpo, campo):
    """EX — perfil inválido, vínculo HOTEL ausente/indevido e e-mail malformado: 422."""
    payload = {"nome": "Conta", "email": "valida@example.test", **corpo}
    resposta = api.como("ADMINISTRADOR").post("/usuarios", json=payload)
    assert resposta.status_code == 422 and campo in erro(resposta).campos


def test_ft_usr_07_inativar_conta_revoga_sessao_e_reativar(api):
    """CF — inativação derruba a sessão em uso e impede login; reativação devolve o acesso."""
    editor = api.como("EDITOR")
    admin = api.como("ADMINISTRADOR")
    assert admin.post("/usuarios/4/inativacao").status_code == 200
    assert editor.get("/perfil").status_code == 401
    assert api.anon.post("/auth/login", json={"email": CONTAS["EDITOR"], "senha": "editor-demo"}).status_code == 401
    assert admin.post("/usuarios/4/reativacao").status_code == 200
    assert api.como("EDITOR").get("/perfil").status_code == 200


def test_ft_usr_08_transicoes_invalidas_de_conta(api):
    """EX — auto-inativação, conta pendente, repetição e id inexistente."""
    admin = api.como("ADMINISTRADOR")
    assert admin.post("/usuarios/1/inativacao").status_code == 409      # própria conta
    assert admin.post("/usuarios/6/reativacao").status_code == 409      # PENDENTE só por convite
    assert admin.post("/usuarios/3/inativacao").status_code == 409      # já inativa
    assert admin.post("/usuarios/999/inativacao").status_code == 404


def test_ft_usr_09_ultimo_administrador_preservado_sob_concorrencia(api):
    """EX 3a — dois administradores inativando um ao outro ao mesmo tempo: um deles permanece."""
    _criar_e_ativar(api, "admin2@example.test", perfil="ADMINISTRADOR", senha="admin2-senha")
    novo_id = api.sql("SELECT id FROM usuarios WHERE email='admin2@example.test'")[0]["id"]
    tokens = [api.anon.post("/auth/login", json=c).json()["access_token"] for c in (
        {"email": CONTAS["ADMINISTRADOR"], "senha": "admin-demo"}, {"email": "admin2@example.test", "senha": "admin2-senha"})]

    def inativar(par):
        token, alvo = par
        with TestClient(main.app, headers={"Authorization": "Bearer " + token}) as cliente:
            return cliente.post(f"/usuarios/{alvo}/inativacao").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(inativar, [(tokens[0], novo_id), (tokens[1], 1)]))
    ativos = api.sql("SELECT count(*) AS n FROM usuarios WHERE perfil='ADMINISTRADOR' AND status='ATIVO'")[0]["n"]
    assert ativos >= 1
    assert codigos in ([200, 401], [200, 409])


@pytest.mark.parametrize("perfil", ["EDITOR", "GESTOR", "HOTEL"])
def test_ft_usr_10_nao_admin_nao_gerencia_contas(api, perfil):
    """EX — gestão de contas restrita ao ADMINISTRADOR."""
    cliente = api.como(perfil)
    assert cliente.get("/usuarios").status_code == 403
    assert cliente.post("/usuarios", json={"nome": "X", "email": "x@example.test", "perfil": "ADMINISTRADOR"}).status_code == 403
    assert cliente.post("/convites", json={"email": CONTAS["EDITOR_PENDENTE"]}).status_code == 403
    assert cliente.post("/usuarios/2/inativacao").status_code == 403


@nao_implementado("NI-03", "Não há operação para alterar o perfil de uma conta existente (UC07 passo 3); o contrato não define PATCH /usuarios/{id}.")
def test_ft_usr_11_alterar_perfil_de_conta_existente(contrato):
    """CF UC07 — ADMIN atribui novo perfil a usuário existente."""
    assert "patch" in contrato["paths"].get("/usuarios/{id_usuario}", {})


def test_ft_usr_12_perfil_proprio_nao_eleva_permissao(api):
    """EX — o titular altera nome, mas não consegue mudar o próprio perfil."""
    editor = api.como("EDITOR")
    assert editor.patch("/perfil", json={"nome": "Camila E. Souza"}).json()["nome"] == "Camila E. Souza"
    assert editor.patch("/perfil", json={"perfil": "ADMINISTRADOR"}).status_code == 422
    assert editor.get("/perfil").json()["perfil"] == "EDITOR"


def test_ft_usr_13_perfil_email_duplicado(api):
    """EX — trocar o próprio e-mail por um já usado: 409."""
    assert api.como("EDITOR").patch("/perfil", json={"email": CONTAS["GESTOR"]}).status_code == 409


def test_ft_usr_14_alterar_propria_senha(api):
    """CF — troca de senha exige a atual, revoga sessões e passa a valer a nova."""
    editor = api.como("EDITOR")
    assert editor.put("/perfil/senha", json={"senha_atual": "errada-123", "senha": "nova-senha-9"}).status_code == 403
    assert editor.put("/perfil/senha", json={"senha_atual": "editor-demo", "senha": "nova-senha-9"}).status_code == 200
    assert editor.get("/perfil").status_code == 401
    assert api.anon.post("/auth/login", json={"email": CONTAS["EDITOR"], "senha": "editor-demo"}).status_code == 401
    assert api.login(CONTAS["EDITOR"], "nova-senha-9").get("/perfil").status_code == 200


def test_ft_usr_15_recuperacao_de_senha(api):
    """CF — resposta neutra; link por e-mail redefine a senha uma única vez e encerra sessões."""
    sessao_antiga = api.como("GESTOR")
    conhecida = api.anon.post("/auth/recuperacao-senha", json={"email": CONTAS["GESTOR"]})
    desconhecida = api.anon.post("/auth/recuperacao-senha", json={"email": "nao.existe@example.test"})
    assert conhecida.status_code == desconhecida.status_code == 202
    assert conhecida.json() == desconhecida.json()
    token = _parametros_do_link(api.ultimo_link(CONTAS["GESTOR"]))["token"]
    assert api.anon.post("/auth/redefinicao-senha", json={"token": token, "senha": "recuperada-1"}).status_code == 200
    assert sessao_antiga.get("/perfil").status_code == 401
    assert api.login(CONTAS["GESTOR"], "recuperada-1").get("/perfil").status_code == 200
    assert api.anon.post("/auth/redefinicao-senha", json={"token": token, "senha": "outra-senha-2"}).status_code == 400
