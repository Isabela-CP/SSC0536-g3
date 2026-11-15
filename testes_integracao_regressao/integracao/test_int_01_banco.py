"""Integração API ↔ PostgreSQL: migrations, seed, papéis, RLS, concorrência e indisponibilidade."""
from __future__ import annotations

import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from app import migrate
from app.database import Database
from apoio import (CNPJ_LIVRE, CONTAS, PESQUISA_EXPECTATIVA_ABERTA, SENHAS, SERRA_AZUL, ProxyTCP,
                   enviar_documento, nova_pesquisa, novo_estabelecimento)
from conftest import ROOT, dsn_do_banco, limpar_caches

MIGRATIONS = sorted(p.name for p in (ROOT / "db" / "migrations").glob("*.sql"))


def _aplicadas(dsn):
    with psycopg.connect(dsn) as conn:
        return dict(conn.execute("SELECT name, checksum FROM schema_migrations ORDER BY name").fetchall())


# ------------------------------------------------------------------ migrations e seed
@pytest.mark.integracao("migrate", "postgresql", "api")
def test_int_bd_01_migrations_em_banco_vazio_e_reexecucao(banco_vazio):
    """CF — banco vazio recebe todas as migrations com checksum; reexecutar não reaplica nada; /health responde."""
    from fastapi.testclient import TestClient
    from app import main

    dsn = dsn_do_banco(banco_vazio)
    apply = lambda: migrate.apply_migrations(Database(dsn))  # noqa: E731
    apply()
    primeira = _aplicadas(dsn)
    assert list(primeira) == MIGRATIONS
    for nome, checksum in primeira.items():
        conteudo = (ROOT / "db" / "migrations" / nome).read_text()
        assert checksum == hashlib.sha256(conteudo.encode()).hexdigest()
    apply()
    assert _aplicadas(dsn) == primeira
    assert TestClient(main.app).get("/health").json() == {"status": "ok"}


@pytest.mark.integracao("migrate", "postgresql")
def test_int_bd_02_migration_alterada_e_recusada(banco_vazio, tmp_path, monkeypatch):
    """EX — alterar uma migration já aplicada interrompe o runner sem tocar no schema."""
    dsn = dsn_do_banco(banco_vazio)
    migrate.apply_migrations(Database(dsn))
    copia = tmp_path / "raiz"
    shutil.copytree(ROOT / "db", copia / "db")
    alvo = copia / "db" / "migrations" / MIGRATIONS[0]
    alvo.write_text(alvo.read_text() + "\n-- alteração indevida\n")
    monkeypatch.setattr(migrate, "ROOT", copia)
    with pytest.raises(RuntimeError, match="modificada"):
        migrate.apply_migrations(Database(dsn))
    assert list(_aplicadas(dsn)) == MIGRATIONS


@pytest.mark.integracao("migrate", "postgresql")
def test_int_bd_03_runners_concorrentes(banco_vazio):
    """EX — duas instâncias iniciando juntas (ex.: api e migrate) aplicam cada migration uma única vez."""
    dsn = dsn_do_banco(banco_vazio)
    with ThreadPoolExecutor(4) as pool:
        resultados = list(pool.map(lambda _: migrate.apply_migrations(Database(dsn)), range(4)))
    assert resultados == [None] * 4
    assert list(_aplicadas(dsn)) == MIGRATIONS


@pytest.mark.integracao("migrate", "postgresql", "api")
def test_int_bd_04_seed_unico_preserva_senha_alterada(sistema):
    """CF — o seed só roda uma vez: reiniciar (novo seed) não redefine a senha alterada pelo usuário."""
    editor = sistema.como("EDITOR")
    assert editor.put("/perfil/senha", json={"senha_atual": "editor-demo", "senha": "senha-nova-123"}).status_code == 200
    antes = sistema.sql("SELECT count(*) AS n FROM estabelecimentos")[0]["n"]
    migrate.seed_development(Database(sistema.dsn))
    migrate.apply_migrations(Database(sistema.dsn))
    assert sistema.anon.post("/auth/login", json={"email": CONTAS["EDITOR"], "senha": "editor-demo"}).status_code == 401
    assert sistema.login(CONTAS["EDITOR"], "senha-nova-123").get("/perfil").status_code == 200
    assert sistema.sql("SELECT count(*) AS n FROM estabelecimentos")[0]["n"] == antes


# ------------------------------------------------------------------ papel da aplicação e RLS
@pytest.fixture
def papel_app(sistema, monkeypatch):
    """Cria o papel restrito da aplicação (como o serviço `migrate` do Compose) e liga a API a ele."""
    nome = "oto_app_" + uuid4().hex[:8]
    monkeypatch.setenv("OTO_APP_USER", nome)
    monkeypatch.setenv("OTO_APP_PASSWORD", "senha-do-papel-qa")
    migrate.configure_application_role(Database(sistema.dsn))
    dsn_app = dsn_do_banco(sistema.nome, user=nome, password="senha-do-papel-qa")
    yield nome, dsn_app
    limpar_caches()
    with psycopg.connect(sistema.dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(nome)))
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(nome)))


@pytest.mark.integracao("api", "postgresql", "papel-oto_app", "storage-local", "outbox")
def test_int_bd_05_fluxo_completo_com_papel_restrito(sistema, papel_app, monkeypatch):
    """CF — a API conectada como papel sem privilégio de dono executa todos os fluxos de escrita."""
    _, dsn_app = papel_app
    monkeypatch.setenv("DATABASE_URL", dsn_app)
    limpar_caches()
    assert sistema.sql("SELECT rolsuper FROM pg_roles WHERE rolname=%s", (papel_app[0],))[0]["rolsuper"] is False
    admin = sistema.como("ADMINISTRADOR")
    criado = admin.post("/estabelecimentos", json=novo_estabelecimento())
    assert criado.status_code == 201, criado.text
    id_novo = criado.json()["id_estabelecimento"]
    assert admin.patch(f"/estabelecimentos/{id_novo}", json={"site": "https://hotel.example"}).status_code == 200
    assert enviar_documento(admin).status_code == 201
    assert admin.post("/usuarios", json={"nome": "Papel", "email": "papel@example.test", "perfil": "GESTOR"}).status_code == 201
    assert admin.post("/convites", json={"email": "papel@example.test"}).status_code == 201
    pesquisa = sistema.como("EDITOR").post("/pesquisas-ocupacao", json=nova_pesquisa())
    assert pesquisa.status_code == 201
    assert sistema.como("HOTEL").post(f"/pesquisas-ocupacao/{PESQUISA_EXPECTATIVA_ABERTA}/respostas",
                                      json={"taxa_ocupacao": 61}).status_code == 201
    relatorio = sistema.como("GESTOR").post("/relatorios", json={"tipo": "OCUPACAO", "formato": "CSV"})
    assert relatorio.status_code == 202
    assert admin.post(f"/estabelecimentos/{id_novo}/inativacao", json={"motivo_inativacao": "Encerrou"}).status_code == 200
    assert len(admin.get("/auditoria").json()["data"]) >= 7
    assert admin.post("/auth/logout").status_code == 204


@pytest.mark.integracao("postgresql", "papel-oto_app")
@pytest.mark.parametrize("comando", [
    "UPDATE auditoria_logs SET acao='ADULTERADA'",
    "DELETE FROM auditoria_logs",
    "TRUNCATE auditoria_logs",
    "INSERT INTO schema_migrations(name, checksum) VALUES ('999_falsa.sql', 'x')",
    "DELETE FROM schema_migrations",
    "CREATE TABLE intrusa(id int)",
])
def test_int_bd_06_papel_da_aplicacao_nao_altera_log_nem_schema(sistema, papel_app, comando):
    """EX — mesmo com a credencial da API, o banco recusa adulterar auditoria, migrations ou o schema."""
    with psycopg.connect(papel_app[1], autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(comando)


@pytest.mark.hospedagem
@pytest.mark.integracao("postgresql", "rls-supabase")
def test_int_bd_07_rls_bloqueia_papeis_publicos(sistema):
    """EX — papel público com GRANT (como anon/authenticated do Supabase) não lê nem grava dados da aplicação."""
    publico = "anon_qa_" + uuid4().hex[:6]
    tabelas = [r["relname"] for r in sistema.sql(
        "SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' ORDER BY relname")]
    with psycopg.connect(sistema.dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(publico)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(publico)))
        conn.execute(sql.SQL("GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(publico)))
    try:
        visiveis = {}
        with psycopg.connect(sistema.dsn) as conn:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(publico)))
            for tabela in tabelas:
                visiveis[tabela] = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(tabela))).fetchone()[0]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("INSERT INTO email_outbox(destinatario, assunto, corpo) VALUES ('alvo@example.test', 'falso', 'phishing')")
        expostas = {t: n for t, n in visiveis.items() if n and t not in ("application_seeds",)}
        assert expostas == {}, f"linhas visíveis a papel público: {expostas}"
    finally:
        with psycopg.connect(sistema.dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(publico)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(publico)))


# ------------------------------------------------------------------ indisponibilidade
@pytest.mark.integracao("api", "postgresql", "rede")
def test_int_bd_08_queda_e_retorno_do_banco(sistema, monkeypatch):
    """EX — sem banco: 503 genérico, sem vazar DSN; com o retorno, a API se recupera sem reinício e a sessão persiste."""
    destino = conninfo_to_dict(sistema.dsn)
    proxy = ProxyTCP((destino.get("host", "127.0.0.1"), int(destino.get("port", 5432))))
    monkeypatch.setenv("DATABASE_URL", dsn_do_banco(sistema.nome, host="127.0.0.1", port=proxy.porta))
    limpar_caches()
    try:
        sessao = sistema.como("GESTOR")
        assert sessao.get("/estabelecimentos").status_code == 200
        proxy.derrubar()
        for resposta in (sistema.anon.get("/health"), sessao.get("/estabelecimentos"),
                         sistema.anon.post("/auth/login", json={"email": CONTAS["GESTOR"], "senha": "gestor-demo"})):
            assert resposta.status_code == 503
            assert resposta.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
            for segredo in (str(proxy.porta), sistema.nome, "127.0.0.1", "password", "postgres"):
                assert segredo not in resposta.text
        proxy.restaurar()
        assert sistema.anon.get("/health").status_code == 200
        assert sessao.get("/estabelecimentos").status_code == 200
    finally:
        proxy.fechar()


# ------------------------------------------------------------------ concorrência
@pytest.mark.integracao("api", "postgresql", "indice-unico")
def test_int_bd_09_cadastros_simultaneos_mesmo_cnpj(sistema):
    """EX — oito cadastros simultâneos do mesmo CNPJ: exatamente um criado e auditado; os demais, 409."""
    admin = sistema.como("ADMINISTRADOR")
    with ThreadPoolExecutor(8) as pool:
        codigos = sorted(pool.map(lambda i: admin.post("/estabelecimentos",
                                                      json=novo_estabelecimento(nome_fantasia=f"Hotel {i}")).status_code, range(8)))
    assert codigos == [201] + [409] * 7
    assert sistema.sql("SELECT count(*) AS n FROM estabelecimentos WHERE cnpj=%s", (CNPJ_LIVRE,))[0]["n"] == 1
    criados = [a for a in admin.get("/auditoria", params={"acao": "ESTABELECIMENTO_CRIADO"}).json()["data"]]
    assert len(criados) == 1


@pytest.mark.integracao("api", "postgresql", "locks")
def test_int_bd_10_edicoes_simultaneas_sem_perda(sistema):
    """EX — dois perfis editam campos diferentes da mesma ficha ao mesmo tempo: nenhuma alteração se perde."""
    admin, editor = sistema.como("ADMINISTRADOR"), sistema.como("EDITOR")

    def editar(i):
        cliente, campo, valor = (admin, "site", f"https://s{i}.example") if i % 2 else (editor, "observacoes", f"obs {i}")
        assert cliente.patch(f"/estabelecimentos/{SERRA_AZUL}", json={campo: valor}).status_code == 200
        return campo, valor

    with ThreadPoolExecutor(6) as pool:
        feitas = list(pool.map(editar, range(12)))
    ficha = admin.get(f"/estabelecimentos/{SERRA_AZUL}").json()
    ultimos = {campo for campo, _ in feitas}
    assert ultimos == {"site", "observacoes"}
    assert ficha["site"] in {v for c, v in feitas if c == "site"}
    assert ficha["observacoes"] in {v for c, v in feitas if c == "observacoes"}
    atualizacoes = admin.get("/auditoria", params={"acao": "ESTABELECIMENTO_ATUALIZADO"}).json()["data"]
    assert len(atualizacoes) == 12


@pytest.mark.integracao("api", "postgresql", "locks")
def test_int_bd_11_respostas_simultaneas_da_mesma_empresa(sistema):
    """EX — o empresário envia a mesma resposta seis vezes ao mesmo tempo: uma gravada, cinco recusadas."""
    hotel = sistema.como("HOTEL")
    url = f"/pesquisas-ocupacao/{PESQUISA_EXPECTATIVA_ABERTA}/respostas"
    with ThreadPoolExecutor(6) as pool:
        respostas = list(pool.map(lambda _: hotel.post(url, json={"taxa_ocupacao": 70}), range(6)))
    assert sorted(r.status_code for r in respostas) == [201] + [409] * 5
    assert {r.json()["error"]["code"] for r in respostas if r.status_code == 409} == {"RESPONSE_ALREADY_SENT"}
    assert sistema.sql("SELECT count(*) AS n FROM respostas_ocupacao WHERE id_pesquisa=%s AND id_estabelecimento=%s",
                       (int(PESQUISA_EXPECTATIVA_ABERTA), SERRA_AZUL))[0]["n"] == 1


@pytest.mark.integracao("api", "postgresql", "configuracao")
def test_int_bd_12_validade_da_sessao_configuravel(sistema, monkeypatch):
    """CF — OTO_SESSION_SECONDS chega ao token e ao registro da sessão no banco."""
    monkeypatch.setenv("OTO_SESSION_SECONDS", "120")
    corpo = sistema.anon.post("/auth/login", json={"email": CONTAS["GESTOR"], "senha": SENHAS["GESTOR"]}).json()
    assert corpo["expires_in"] == 120
    expira = sistema.sql("SELECT max(expira_em) AS e FROM sessoes")[0]["e"]
    restante = (expira - datetime.now(timezone.utc)).total_seconds()
    assert 100 <= restante <= 125
