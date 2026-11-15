"""Infraestrutura dos testes de integração do Inventário OTO.

Cada teste recebe um banco PostgreSQL próprio (clone de um modelo com migrations + seed,
ou um banco vazio quando o objeto do teste é a própria inicialização). Os componentes
são os reais: API FastAPI, PostgreSQL, SMTP (Mailpit), sistema de arquivos e o código
de serviços do frontend. Supabase Storage e Brevo usam dublês (apoio.py).
"""
from __future__ import annotations

import os
import re
import socket
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.database import Database, database  # noqa: E402
from app.document_storage import document_storage, report_storage  # noqa: E402
from app.migrate import apply_migrations, seed_development  # noqa: E402

from apoio import CHAVE_SUPABASE, CONTAS, SENHAS, Mailpit, SupabaseFalso  # noqa: E402

FIXTURES_COM_BANCO = {"sistema", "banco_vazio", "api_http"}


def pytest_configure(config):
    config.addinivalue_line("markers", "integracao(*interfaces): interfaces entre componentes exercitadas")
    config.addinivalue_line("markers", "hospedagem: integra recurso introduzido no PR #39 (fora da regressão entre versões)")
    config.addinivalue_line("markers", "defeito(codigo): teste que evidencia um defeito registrado")


def pytest_collection_modifyitems(config, items):
    """Sem banco (ou sem Mailpit, quando exigido) a coleta falha: integração não se simula."""
    usadas = {f for item in items for f in getattr(item, "fixturenames", ())}
    if usadas & FIXTURES_COM_BANCO and not os.getenv("OTO_TEST_ADMIN_URL"):
        raise pytest.UsageError("Configure OTO_TEST_ADMIN_URL com um PostgreSQL de TESTES que possa criar bancos.")
    if "mailpit" in usadas and not (os.getenv("OTO_TEST_MAILPIT_URL") and os.getenv("OTO_TEST_SMTP")):
        raise pytest.UsageError("Configure OTO_TEST_MAILPIT_URL e OTO_TEST_SMTP (Mailpit de testes).")


def limpar_caches():
    for cached in (database, main.inventory_repository, document_storage, report_storage):
        cached.cache_clear()


def _executar_admin(comando):
    with psycopg.connect(os.environ["OTO_TEST_ADMIN_URL"], autocommit=True) as conn:
        conn.execute(comando)


def _criar_banco(modelo: str | None = None) -> str:
    nome = "oto_int_" + uuid4().hex[:12]
    comando = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome))
    if modelo:
        comando = sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(nome), sql.Identifier(modelo))
    _executar_admin(comando)
    return nome


def _remover_banco(nome: str):
    _executar_admin(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))


def dsn_do_banco(nome: str, **extra) -> str:
    return make_conninfo(os.environ["OTO_TEST_ADMIN_URL"], dbname=nome, **extra)


@pytest.fixture(scope="session")
def banco_modelo():
    nome = _criar_banco()
    try:
        db = Database(dsn_do_banco(nome))
        apply_migrations(db)
        seed_development(db)
        yield nome
    finally:
        _remover_banco(nome)


class Sistema:
    """Sistema integrado sob teste: API real ligada a um banco PostgreSQL exclusivo."""

    def __init__(self, nome: str):
        self.nome = nome
        self.dsn = dsn_do_banco(nome)
        self.anon = TestClient(main.app, raise_server_exceptions=False)

    def login(self, email: str, senha: str) -> TestClient:
        resposta = self.anon.post("/auth/login", json={"email": email, "senha": senha})
        assert resposta.status_code == 200, f"login de {email}: {resposta.status_code} {resposta.text}"
        return TestClient(main.app, raise_server_exceptions=False,
                          headers={"Authorization": "Bearer " + resposta.json()["access_token"]})

    def como(self, perfil: str) -> TestClient:
        return self.login(CONTAS[perfil], SENHAS[perfil.split("_")[0]])

    def sql(self, consulta: str, params: tuple = ()) -> list[dict]:
        with psycopg.connect(self.dsn, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
            cursor = conn.execute(consulta, params)
            return cursor.fetchall() if cursor.description else []

    def ultimo_link(self, email: str) -> str:
        linhas = self.sql("SELECT corpo FROM email_outbox WHERE lower(destinatario)=%s ORDER BY id DESC LIMIT 1",
                          (email.casefold(),))
        assert linhas, f"nenhum e-mail enfileirado para {email}"
        return re.search(r"https?://\S+", linhas[0]["corpo"]).group(0)


@pytest.fixture
def sistema(banco_modelo, monkeypatch, tmp_path):
    nome = _criar_banco(banco_modelo)
    monkeypatch.setenv("OTO_DATA_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", dsn_do_banco(nome))
    monkeypatch.setenv("OTO_STORAGE_DIR", str(tmp_path / "documentos"))
    monkeypatch.setenv("OTO_REPORT_STORAGE_DIR", str(tmp_path / "relatorios"))
    for var in ("OTO_SESSION_SECONDS", "OTO_STORAGE_PROVIDER", "OTO_MAIL_PROVIDER", "OTO_SMTP_HOST", "OTO_MAILER_EMBEDDED"):
        monkeypatch.delenv(var, raising=False)
    limpar_caches()
    try:
        yield Sistema(nome)
    finally:
        limpar_caches()
        _remover_banco(nome)


@pytest.fixture
def banco_vazio(monkeypatch):
    """Banco recém-criado, sem migrations: objeto de teste da inicialização."""
    nome = _criar_banco()
    monkeypatch.setenv("OTO_DATA_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", dsn_do_banco(nome))
    limpar_caches()
    try:
        yield nome
    finally:
        limpar_caches()
        _remover_banco(nome)


@pytest.fixture
def mailpit(monkeypatch):
    caixa = Mailpit(os.environ["OTO_TEST_MAILPIT_URL"], os.environ["OTO_TEST_SMTP"])
    caixa.limpar()
    monkeypatch.setenv("OTO_MAIL_PROVIDER", "smtp")
    monkeypatch.setenv("OTO_SMTP_HOST", caixa.smtp_host)
    monkeypatch.setenv("OTO_SMTP_PORT", str(caixa.smtp_porta))
    monkeypatch.setenv("OTO_MAIL_FROM", "no-reply@oto.example.test")
    monkeypatch.setenv("OTO_PUBLIC_URL", "https://oto.example.test")
    yield caixa
    caixa.limpar()


@pytest.fixture
def supabase(sistema, monkeypatch):
    """Liga a API ao dublê da Storage API do Supabase (provedor `supabase`, como no Render)."""
    import httpx
    from app import cloud_storage as modulo

    falso = SupabaseFalso()
    original = modulo.cloud_storage

    def com_dublê(*args, **kwargs):
        storage = original(*args, **kwargs)
        storage.client = httpx.Client(transport=httpx.WSGITransport(app=falso), timeout=30, follow_redirects=False)
        return storage

    monkeypatch.setattr(modulo, "cloud_storage", com_dublê)
    monkeypatch.setenv("OTO_STORAGE_PROVIDER", "supabase")
    monkeypatch.setenv("OTO_SUPABASE_URL", "https://projeto-qa.supabase.co")
    monkeypatch.setenv("OTO_SUPABASE_SERVICE_KEY", CHAVE_SUPABASE)
    monkeypatch.setenv("OTO_STORAGE_BUCKET", "oto-arquivos")
    limpar_caches()
    yield falso
    limpar_caches()


def _porta_livre() -> int:
    with socket.create_server(("127.0.0.1", 0)) as s:
        return s.getsockname()[1]


@pytest.fixture
def api_http(sistema):
    """A mesma API servida por HTTP real (uvicorn), para clientes fora do processo (frontend em Node)."""
    import uvicorn

    porta = _porta_livre()
    servidor = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=porta, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.monotonic() + 15
    while not servidor.started and time.monotonic() < limite:
        time.sleep(0.05)
    assert servidor.started, "uvicorn não iniciou"
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        servidor.should_exit = True
        thread.join(10)


@pytest.fixture(autouse=True)
def _rastreabilidade(request, record_property):
    """Grava no JUnit XML as interfaces exercitadas e o código de defeito (evidência rastreável)."""
    interfaces = sorted({i for m in request.node.iter_markers("integracao") for i in m.args})
    record_property("interfaces", ",".join(interfaces))
    marca = request.node.get_closest_marker("defeito")
    if marca:
        record_property("defeito", marca.args[0])
