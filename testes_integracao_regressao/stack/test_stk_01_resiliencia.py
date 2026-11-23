"""Integração da stack Docker real (Nginx ↔ API ↔ PostgreSQL ↔ volume ↔ worker ↔ Mailpit).

Cada cenário derruba ou reinicia um serviço e observa o sistema de fora, pelo Nginx.
Requer OTO_STACK_URL e OTO_STACK_MAILPIT (stack descartável; veja o README).
"""
from __future__ import annotations

import os
import re
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from apoio_stack import PDF, SERRA_AZUL, Stack, cnpj_unico

pytestmark = pytest.mark.skipif(not os.getenv("OTO_STACK_URL"), reason="defina OTO_STACK_URL (stack Docker descartável)")


@pytest.fixture(scope="module")
def stack():
    s = Stack()
    s.esperar_saude()
    return s


def _parametros(link):
    return {k: v[0] for k, v in parse_qs(urlsplit(link).fragment.partition("?")[2]).items()}


def _criar_conta_pendente(stack, admin, email):
    assert admin.post("/usuarios", json={"nome": "Conta Stack", "email": email, "perfil": "GESTOR"}).status_code == 201


@pytest.mark.integracao("nginx", "api", "postgresql", "volume", "worker")
def test_int_stk_01_reinicio_da_api_e_do_worker(stack):
    """CF — dados, arquivos, relatórios e a sessão em uso sobrevivem ao reinício dos processos api e worker."""
    token = stack.token("ADMINISTRADOR")
    admin = stack.http(token)
    nome = "Hotel Reinício " + uuid4().hex[:6]
    criado = admin.post("/estabelecimentos", json={"id_categoria": 1, "nome_fantasia": nome, "razao_social": nome + " Ltda.",
                                                   "cnpj": cnpj_unico(), "endereco": "Rua da Stack, 1"})
    assert criado.status_code == 201, criado.text
    documento = admin.post(f"/estabelecimentos/{SERRA_AZUL}/documentos", data={"tipo_documento": "ALVARA", "data_vencimento": "2031-01-01"},
                           files={"arquivo": ("stack.pdf", PDF, "application/pdf")}).json()
    relatorio = stack.cliente("GESTOR").post("/relatorios", json={"tipo": "OCUPACAO", "formato": "CSV"}).json()
    antes = {s: stack.iniciado_em(s) for s in ("api", "worker")}
    stack.compose("restart", "api", "worker")
    stack.esperar_saude()
    assert all(stack.iniciado_em(s) != antes[s] for s in antes), "os serviços não foram reiniciados"
    assert admin.get(f"/estabelecimentos/{criado.json()['id_estabelecimento']}").json()["nome_fantasia"] == nome
    arquivo = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert arquivo.status_code == 200 and arquivo.content == PDF
    assert stack.cliente("GESTOR").get(f"/relatorios/{relatorio['id_relatorio']}/arquivo").status_code == 200


@pytest.mark.integracao("nginx", "api", "postgresql")
def test_int_stk_02_queda_e_retorno_do_banco(stack):
    """EX — com o banco parado, o Nginx entrega 503 JSON da API; quando o banco volta, a API se recupera sozinha."""
    token = stack.token("GESTOR")
    api_antes = stack.iniciado_em("api")
    stack.compose("stop", "db")
    try:
        for resposta in (stack.http().get("/health"), stack.http(token).get("/estabelecimentos")):
            assert resposta.status_code == 503
            assert resposta.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
            assert "oto_app" not in resposta.text and "5432" not in resposta.text
    finally:
        stack.compose("start", "db")
    stack.esperar_saude()
    assert stack.iniciado_em("api") == api_antes, "a API não deve precisar de reinício"
    assert stack.http(token).get("/estabelecimentos").status_code == 200


@pytest.mark.integracao("api", "outbox", "worker", "smtp", "nginx")
def test_int_stk_03_worker_parado_e_fila_preservada(stack):
    """EX — sem worker o convite fica na fila; quando o worker volta, o e-mail chega e o link ativa a conta pelo Nginx."""
    email = f"fila.{uuid4().hex[:6]}@example.test"
    admin = stack.cliente("ADMINISTRADOR")
    _criar_conta_pendente(stack, admin, email)
    stack.compose("stop", "worker")
    try:
        assert admin.post("/convites", json={"email": email}).status_code == 201
        time.sleep(6)
        assert stack.emails_para(email) == []
        assert stack.sql(f"SELECT tentativas, enviado_em IS NULL FROM email_outbox WHERE destinatario='{email}'") == "0|t"
    finally:
        stack.compose("start", "worker")
    [mensagem] = stack.esperar_email(email)
    link = re.search(r"https?://\S+", stack.texto(mensagem)).group(0)
    assert link.startswith(stack.base + "/#/ativar-convite?")
    p = _parametros(link)
    assert stack.http().post(f"/convites/{p['id']}/aceitacao", json={"token": p["token"], "senha": "senha-stack-1"}).status_code == 200
    assert stack.http().post("/auth/login", json={"email": email, "senha": "senha-stack-1"}).status_code == 200


@pytest.mark.integracao("worker", "smtp", "outbox")
def test_int_stk_04_queda_curta_do_servidor_de_email(stack):
    """EX — o servidor de e-mail fica 15 s fora do ar: ao voltar, a mensagem pendente deve ser entregue."""
    email = f"queda.{uuid4().hex[:6]}@example.test"
    admin = stack.cliente("ADMINISTRADOR")
    _criar_conta_pendente(stack, admin, email)
    stack.compose("stop", "mailpit")
    try:
        assert admin.post("/convites", json={"email": email}).status_code == 201
        time.sleep(15)
    finally:
        stack.compose("start", "mailpit")
    entregue = stack.esperar_email(email, segundos=40)
    tentativas = stack.sql(f"SELECT tentativas FROM email_outbox WHERE destinatario='{email}'")
    assert entregue, f"não entregue após o retorno do servidor (tentativas registradas: {tentativas})"


@pytest.mark.integracao("nginx", "api", "postgresql", "volume")
def test_int_stk_05_recriacao_dos_conteineres(stack):
    """CF — `down` (sem apagar volumes) e `up`: banco e arquivos persistem nos volumes nomeados."""
    admin = stack.cliente("ADMINISTRADOR")
    documento = admin.post(f"/estabelecimentos/{SERRA_AZUL}/documentos", data={"tipo_documento": "AVCB", "data_vencimento": "2032-02-02"},
                           files={"arquivo": ("recriado.pdf", PDF + b"recriado", "application/pdf")}).json()
    stack.compose("down")
    stack.compose("up", "-d", "--wait", timeout=600)
    stack.esperar_saude()
    admin = stack.cliente("ADMINISTRADOR")
    arquivo = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert arquivo.status_code == 200 and arquivo.content == PDF + b"recriado"
    assert stack.sql("SELECT count(*) FROM application_seeds") == "1", "o seed não pode ser reaplicado"


@pytest.mark.integracao("nginx", "api", "contrato")
def test_int_stk_06_proxy_entrega_contrato_e_erros_da_api(stack):
    """CF/EX — pelo Nginx: Swagger e contrato com servidor /api; rota inexistente da API responde 404 em JSON."""
    swagger = stack.http().get("/docs")
    assert swagger.status_code == 200 and "swagger-ui" in swagger.text.lower()
    contrato = stack.http().get("/openapi.json").json()
    assert contrato["servers"][0]["url"] == "/api" and "/estabelecimentos" in contrato["paths"]
    inexistente = stack.http().get("/rota-que-nao-existe")
    assert inexistente.status_code == 404 and inexistente.headers["content-type"].startswith("application/json")
