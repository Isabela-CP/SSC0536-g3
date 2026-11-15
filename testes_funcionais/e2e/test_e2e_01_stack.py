"""Stack Docker completa: proxy Nginx, limites de upload e e-mails entregues pelo worker via SMTP (Mailpit)."""
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from apoio import BASE, CONTAS, unico

DEZ_MIB = 10 * 1024 * 1024


def _link(texto: str) -> str:
    return re.search(r"https?://\S+", texto).group(0)


def _parametros(link: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(link).fragment.partition("?")[2]).items()}


@pytest.mark.uc("RNF-01")
def test_ft_stk_01_aplicacao_web_servida(stack):
    """CF RNF-01 — o navegador recebe a aplicação; rotas internas da SPA também respondem."""
    for caminho in ("/", "/qualquer/rota/interna"):
        resposta = stack.http.get(caminho)
        assert resposta.status_code == 200 and "text/html" in resposta.headers["content-type"]
        assert '<div id="root"' in resposta.text


@pytest.mark.uc("RNF-01")
def test_ft_stk_02_api_e_cabecalhos_pelo_proxy(stack):
    """CF — a API responde através do Nginx em /api e as respostas trazem cabeçalhos de segurança."""
    assert stack.http.get("/api/health").json() == {"status": "ok"}
    cabecalhos = stack.http.get("/").headers
    assert cabecalhos.get("x-content-type-options") == "nosniff"
    assert cabecalhos.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.uc("UC02", "UC12")
@pytest.mark.parametrize("tamanho,esperado", [(DEZ_MIB, 201), (DEZ_MIB + 1, 413), (13 * 1024 * 1024, 413)])
def test_ft_stk_03_limite_de_upload(stack, tamanho, esperado):
    """EX — valor limite do arquivo: 10 MiB aceito; acima disso 413 (API até 12 MiB, Nginx além), sempre em JSON."""
    hospedagem = stack.criar_hospedagem()
    conteudo = b"%PDF-1.4\n" + b"0" * (tamanho - 9)
    resposta = stack.cliente().post(f"/estabelecimentos/{hospedagem['id_estabelecimento']}/documentos",
                                    data={"tipo_documento": "ALVARA", "data_vencimento": "2030-01-01"},
                                    files={"arquivo": ("grande.pdf", conteudo, "application/pdf")})
    assert resposta.status_code == esperado
    if esperado == 413:
        assert resposta.headers["content-type"].startswith("application/json") and "error" in resposta.json()


@pytest.mark.uc("UC07")
def test_ft_stk_04_convite_entregue_por_email_ativa_conta(stack):
    """CF — o convite chega à caixa de e-mail (SMTP real), o link aponta para a aplicação e ativa a conta."""
    email = unico("convite").replace(" ", ".") + "@example.test"
    admin = stack.cliente()
    assert admin.post("/usuarios", json={"nome": "Estagiária E2E", "email": email, "perfil": "EDITOR"}).status_code == 201
    assert admin.post("/convites", json={"email": email}).status_code == 201
    link = _link(stack.esperar_email(email))
    assert link.startswith(BASE + "/#/ativar-convite")
    dados = _parametros(link)
    ativacao = stack.http.post(f"/api/convites/{dados['id']}/aceitacao", json={"token": dados["token"], "senha": "senha-e2e-123"})
    assert ativacao.status_code == 200
    assert stack.cliente(email=email, senha="senha-e2e-123").get("/perfil").json()["perfil"] == "EDITOR"


@pytest.mark.uc("UC00")
def test_ft_stk_05_recuperacao_de_senha_por_email(stack):
    """CF — conta existente recebe o link de recuperação; endereço desconhecido não gera e-mail."""
    conhecido, desconhecido = CONTAS["GESTOR"], unico("ninguem").replace(" ", ".") + "@example.test"
    antes = len(stack.emails_para(conhecido))
    for endereco in (conhecido, desconhecido):
        assert stack.http.post("/api/auth/recuperacao-senha", json={"email": endereco}).status_code == 202
    texto = stack.esperar_email(conhecido, ja_existentes=antes)
    assert _link(texto).startswith(BASE + "/#/redefinir-senha?token=")
    assert stack.emails_para(desconhecido) == []
