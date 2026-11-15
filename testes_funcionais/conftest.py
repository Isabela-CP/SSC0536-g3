"""Infraestrutura dos testes funcionais do Inventário OTO.

Cada teste recebe um banco PostgreSQL novo, clonado de um modelo preparado uma única
vez por sessão (migrations + seed de desenvolvimento). A API é exercitada somente pela
sua interface HTTP pública; o acesso direto ao banco (`api.sql`) serve apenas para
preparar estados difíceis de obter pela interface (ex.: sessão expirada) e para ler a
caixa de e-mails capturada (`email_outbox`), que substitui o Mailpit.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:  # o backend só é necessário nos testes de API; os de ponta a ponta (e2e/) rodam sem ele
    import psycopg  # noqa: E402
    from psycopg import sql  # noqa: E402
    from psycopg.conninfo import make_conninfo  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402

    from app import main  # noqa: E402
    from app.database import Database, database  # noqa: E402
    from app.document_storage import document_storage, report_storage  # noqa: E402
    from app.migrate import apply_migrations, seed_development  # noqa: E402
    BACKEND_DISPONIVEL = True
except ImportError:
    BACKEND_DISPONIVEL = False

from apoio_api import CONTAS, SENHAS  # noqa: E402  (massa de dados em apoio_api.py)


# --------------------------------------------------------------------- pytest
def pytest_configure(config):
    config.addinivalue_line("markers", "uc(*ids): casos de uso cobertos pelo teste")
    config.addinivalue_line("markers", "defeito(codigo): teste que evidencia um defeito registrado")
    config.addinivalue_line("markers", "nao_implementado(codigo): requisito sem funcionalidade na build")


def pytest_collection_modifyitems(config, items):
    """Os testes de API exigem banco real: falham na coleta (não pulam) se ele não estiver configurado."""
    if not any("api" in getattr(item, "fixturenames", ()) for item in items):
        return
    if not BACKEND_DISPONIVEL:
        raise pytest.UsageError("Instale backend/requirements.txt para executar os testes de API.")
    if not os.getenv("OTO_TEST_ADMIN_URL"):
        raise pytest.UsageError("Configure OTO_TEST_ADMIN_URL com uma conexão PostgreSQL de TESTES que possa "
                                "criar bancos (ex.: postgresql://postgres@127.0.0.1:5432/postgres). Os testes "
                                "funcionais de API não rodam sem banco real.")


@pytest.fixture(scope="session")
def banco_modelo():
    admin = os.environ["OTO_TEST_ADMIN_URL"]
    nome = "oto_func_modelo_" + uuid4().hex[:10]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    try:
        db = Database(make_conninfo(admin, dbname=nome))
        apply_migrations(db)
        seed_development(db)
        yield admin, nome
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))


def _limpar_caches():
    for cached in (database, main.inventory_repository, document_storage, report_storage):
        cached.cache_clear()


class Api:
    """Fachada da API: um cliente anônimo e clientes autenticados por perfil."""

    def __init__(self, db: Database):
        self.db = db
        self.anon = TestClient(main.app)

    def login(self, email: str, senha: str) -> TestClient:
        resposta = self.anon.post("/auth/login", json={"email": email, "senha": senha})
        assert resposta.status_code == 200, f"login de {email} falhou: {resposta.status_code} {resposta.text}"
        return TestClient(main.app, headers={"Authorization": "Bearer " + resposta.json()["access_token"]})

    def como(self, perfil: str) -> TestClient:
        chave = perfil
        senha = SENHAS[perfil.split("_")[0]]
        return self.login(CONTAS[chave], senha)

    def sql(self, query: str, params: tuple = ()) -> list[dict]:
        with self.db.transaction() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else []

    def ultimo_link(self, email: str) -> str:
        """Lê o link enviado ao destinatário na fila de e-mails capturada."""
        linhas = self.sql("SELECT corpo FROM email_outbox WHERE lower(destinatario)=%s ORDER BY id DESC LIMIT 1",
                          (email.casefold(),))
        assert linhas, f"nenhum e-mail enfileirado para {email}"
        return re.search(r"https?://\S+", linhas[0]["corpo"]).group(0)

    def auditoria(self, acao: str | None = None) -> list[dict]:
        params = {"acao": acao} if acao else {}
        resposta = self.como("ADMINISTRADOR").get("/auditoria", params=params)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["data"]


@pytest.fixture
def api(banco_modelo, monkeypatch, tmp_path):
    admin, modelo = banco_modelo
    nome = "oto_func_" + uuid4().hex[:12]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(nome), sql.Identifier(modelo)))
    monkeypatch.setenv("OTO_DATA_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", make_conninfo(admin, dbname=nome))
    monkeypatch.setenv("OTO_STORAGE_DIR", str(tmp_path / "documentos"))
    monkeypatch.setenv("OTO_REPORT_STORAGE_DIR", str(tmp_path / "relatorios"))
    monkeypatch.delenv("OTO_SESSION_SECONDS", raising=False)
    _limpar_caches()
    try:
        yield Api(database())
    finally:
        _limpar_caches()
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))


@pytest.fixture
def contrato() -> dict:
    import json
    return json.loads((ROOT / "contratos_api_oto" / "openapi.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _rastreabilidade(request, record_property):
    """Grava no JUnit XML os casos de uso e códigos de defeito de cada teste (evidência rastreável)."""
    ucs = sorted({uc for marca in request.node.iter_markers("uc") for uc in marca.args})
    record_property("casos_de_uso", ",".join(ucs))
    for nome in ("defeito", "nao_implementado"):
        marca = request.node.get_closest_marker(nome)
        if marca:
            record_property(nome, marca.args[0])
