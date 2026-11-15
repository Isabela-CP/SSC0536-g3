"""Integração frontend ↔ API: o código real da camada de serviços do React contra a API real.

`frontend/cliente_frontend.mjs` carrega frontend/src/services e frontend/src/domain pelo Vite
(como os testes unitários do time) e chama a API servida por uvicorn sobre um banco exclusivo.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest
from starlette.routing import Route

from app import main
from apoio import SERRA_AZUL
from conftest import ROOT

SCRIPT = ROOT / "testes_integracao_regressao" / "integracao" / "frontend" / "cliente_frontend.mjs"
FORA_DO_CONTRATO = {"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def executar_frontend(cenario: str, api_url: str | None = None):
    node = os.getenv("OTO_TEST_NODE", "node")
    if not shutil.which(node):
        pytest.fail(f"Node.js não encontrado ({node}); necessário para integrar o frontend.")
    if not (ROOT / "frontend" / "node_modules").exists():
        pytest.fail("Instale as dependências do frontend (npm ci em frontend/).")
    processo = subprocess.run([node, str(SCRIPT), cenario], cwd=ROOT / "frontend", capture_output=True, text=True,
                              timeout=180, env={**os.environ, "OTO_INT_API_URL": api_url or ""})
    assert processo.returncode == 0, f"frontend falhou:\n{processo.stdout[-3000:]}\n{processo.stderr[-3000:]}"
    return json.loads(processo.stdout.split("@@RESULTADO@@", 1)[1])


def _rotas_backend() -> set[tuple[str, str]]:
    """Rotas efetivas da API, inclusive as de routers incluídos (o FastAPI 0.16x os agrupa)."""
    def percorrer(rotas, prefixo=""):
        for rota in rotas:
            if isinstance(rota, Route):
                yield from ((m, prefixo + rota.path) for m in (rota.methods or ()) if m not in ("HEAD", "OPTIONS"))
            elif hasattr(rota, "original_router"):
                contexto = getattr(rota, "include_context", None)
                yield from percorrer(rota.original_router.routes, prefixo + (getattr(contexto, "prefix", "") or ""))
    return set(percorrer(main.app.routes))


def _casa(caminho: str, modelo: str) -> bool:
    return re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", modelo), caminho) is not None


@pytest.fixture(scope="module")
def chamadas_do_frontend():
    return executar_frontend("rotas")


# ------------------------------------------------------------------ contrato entre as camadas
@pytest.mark.integracao("frontend", "api", "contrato")
def test_int_fe_01_toda_chamada_do_frontend_existe_no_backend_e_no_contrato(chamadas_do_frontend, contrato):
    """CF — cada operação do cliente HTTP do frontend corresponde a uma rota implementada e documentada."""
    backend = _rotas_backend()
    documentadas = {(m.upper(), p) for p, ops in contrato["paths"].items() for m in ops if m in ("get", "post", "put", "patch", "delete")}
    assert len(chamadas_do_frontend) >= 35
    sem_backend = [c for c in chamadas_do_frontend if not any(m == c["metodo"] and _casa(c["caminho"], p) for m, p in backend)]
    sem_contrato = [c for c in chamadas_do_frontend if not any(m == c["metodo"] and _casa(c["caminho"], p) for m, p in documentadas)]
    assert sem_backend == [] and sem_contrato == []


@pytest.mark.integracao("api", "contrato")
def test_int_fe_02_backend_e_contrato_tem_as_mesmas_operacoes(contrato):
    """CF — toda operação do OpenAPI está implementada e toda rota pública da API está documentada."""
    documentadas = {(m.upper(), p) for p, ops in contrato["paths"].items() for m in ops if m in ("get", "post", "put", "patch", "delete")}
    implementadas = {(m, p) for m, p in _rotas_backend() if p not in FORA_DO_CONTRATO}
    assert documentadas - implementadas == set(), "documentadas e não implementadas"
    assert implementadas - documentadas == set(), "implementadas e não documentadas"


@pytest.fixture
def contrato():
    return json.loads((ROOT / "contratos_api_oto" / "openapi.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ código do frontend contra a API real
@pytest.mark.integracao("frontend", "api", "postgresql", "sessao")
def test_int_fe_03_sessao_e_tratamento_de_401(api_http):
    """CF/EX — login de cada perfil; após logout o 401 dispara o evento de sessão encerrada; senha errada não dispara."""
    r = executar_frontend("sessao", api_http)
    assert {p: r[p] for p in ("ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL")} == {
        "ADMINISTRADOR": "ADMINISTRADOR", "GESTOR": "GESTOR", "EDITOR": "EDITOR", "HOTEL": "HOTEL"}
    assert r["depoisDoLogout"]["status"] == 401 and r["eventosNaoAutorizado"] == 1
    assert r["semSessao"]["status"] == 401 and r["eventosSemSessao"] == 1
    assert r["senhaErrada"] == {"status": 401, "code": "INVALID_CREDENTIALS", "mensagem": "E-mail ou senha inválidos.", "campos": {}}
    assert r["eventosNoLoginErrado"] == 0


@pytest.mark.integracao("frontend", "api", "postgresql", "leitura")
def test_int_fe_04_painel_e_inventario_carregados_pelo_frontend(api_http, sistema):
    """CF — loadDashboard/loadInventory interpretam as respostas reais com os mesmos números da API."""
    r = executar_frontend("painel", api_http)
    admin = sistema.como("ADMINISTRADOR")
    assert r["indicadores"] == admin.get("/dashboard").json()["indicadores"]
    primeira = r["categorias"][0]
    total = admin.get("/estabelecimentos", params={"id_categoria": primeira}).json()["pagination"]["total"]
    assert r["total"] == total and r["itens"] == min(total, 20)
    assert r["marcadores"] >= 1
    assert r["busca"] == ["Hotel Serra Azul"]


@pytest.mark.integracao("frontend", "api", "storage-relatorios")
def test_int_fe_05_relatorio_preparado_pelo_frontend(api_http):
    """CF — prepareReport cria, acompanha e baixa CSV e PDF reais, aceitando o tipo MIME devolvido."""
    r = executar_frontend("relatorio", api_http)
    assert r["CSV"]["tipo"].startswith("text/csv") and r["CSV"]["inicio"].lstrip("﻿").startswith("Pesq")
    assert r["PDF"]["tipo"] == "application/pdf" and r["PDF"]["inicio"].startswith("%PDF")
    for formato in ("CSV", "PDF"):
        assert r[formato]["tamanho"] > 0
        assert r[formato]["nome"] == f"relatorio.{formato.lower()}"
        assert r[formato]["disposicao"] == f'attachment; filename="relatorio.{formato.lower()}"'


@pytest.mark.integracao("frontend", "api", "storage", "multipart")
def test_int_fe_06_documento_enviado_pelo_frontend(api_http, sistema):
    """CF — FormData do frontend chega à API: envio, download idêntico, substituição e edição de metadados."""
    r = executar_frontend("documento", api_http)
    assert r["validacao"] is None
    assert r["criado"]["arquivo"]["nome_arquivo"] == "alvará municipal.pdf"
    assert r["baixadoIgual"] is True
    assert r["disposicao"] == "attachment; filename*=UTF-8''alvar%C3%A1%20municipal.pdf"
    assert r["substituido"] == "%PDF-1.4\nv2\n"
    assert r["numero"] == "ALV-2031" and r["naLista"] is True
    acoes = [a["acao"] for a in sistema.como("ADMINISTRADOR").get("/auditoria").json()["data"]]
    assert {"DOCUMENTO_CRIADO", "DOCUMENTO_ARQUIVO_SUBSTITUIDO", "DOCUMENTO_ATUALIZADO"} <= set(acoes)


@pytest.mark.integracao("frontend", "api", "erros")
def test_int_fe_07_codigos_de_erro_viram_mensagens_especificas(api_http, sistema):
    """EX — cada código de erro emitido pela API é reconhecido pelo frontend e vira a mensagem prevista."""
    r = executar_frontend("erros", api_http)
    esperadas = {
        "INVALID_CREDENTIALS": (401, "E-mail ou senha inválidos."),
        "INVITE_NOT_FOUND": (404, "Convite não encontrado ou expirado."),
        "SURVEY_CLOSED": (409, "Esta pesquisa está encerrada."),
        "RESPONSE_ALREADY_SENT": (409, "A resposta desta hospedagem já foi enviada."),
        "FORBIDDEN": (403, "Seu perfil não tem permissão para esta ação."),
    }
    for codigo, (status, mensagem) in esperadas.items():
        assert (r[codigo]["status"], r[codigo]["mensagem"]) == (status, mensagem), codigo
    assert r["EMAIL_ALREADY_EXISTS"]["status"] == 409
    assert r["EMAIL_ALREADY_EXISTS"]["campos"]["email"] == "Já existe uma conta com esse e-mail."
    assert r["VALIDATION_ERROR"]["status"] == 422 and "cnpj" in r["VALIDATION_ERROR"]["campos"]
    assert r["contaCriada"] == {"email": "front@example.test", "convite": "PENDENTE"}
    assert sistema.sql("SELECT count(*) AS n FROM email_outbox WHERE destinatario='front@example.test'")[0]["n"] == 1


@pytest.mark.integracao("frontend", "api", "postgresql", "pesquisas")
def test_int_fe_08_empresario_responde_pelo_frontend(api_http):
    """CF — o empresário lista pendências, responde 64,5% e a resposta aparece no histórico; validação local recusa 150%."""
    r = executar_frontend("empresario", api_http)
    assert r["pendentes"] == ["4"]
    assert r["validacaoFront"]["taxa150"] and not r["validacaoFront"]["taxa64"]
    assert r["resposta"] == {"id_pesquisa": "4", "estabelecimento": SERRA_AZUL}
    assert r["noHistorico"] is True and r["pendentesDepois"] == []
