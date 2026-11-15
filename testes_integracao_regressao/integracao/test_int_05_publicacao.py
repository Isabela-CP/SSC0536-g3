"""Integração da API com o ambiente de publicação: CORS, proxy (root_path), entrada hospedada e bootstrap."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg
import pytest

from app.database import Database, persistent
from app.migrate import apply_migrations
from conftest import ROOT, dsn_do_banco

PAGES = "https://isabela-cp.github.io"
BACKEND = ROOT / "backend"

SONDA_HTTP = r"""
import json, os, sys
from fastapi.testclient import TestClient
from app import main
c = TestClient(main.app)
saida = {}
for origem in json.loads(sys.argv[1]):
    pre = c.options("/auth/login", headers={"Origin": origem, "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "authorization,content-type"})
    get = c.get("/health", headers={"Origin": origem})
    saida[origem] = {"preflight": pre.status_code, "allow_origin": pre.headers.get("access-control-allow-origin"),
                     "credenciais": pre.headers.get("access-control-allow-credentials"),
                     "get_allow_origin": get.headers.get("access-control-allow-origin"),
                     "expostos": get.headers.get("access-control-expose-headers", "")}
saida["servers"] = c.get("/openapi.json").json()["servers"]
print("@@" + json.dumps(saida))
"""


def _sondar(origens, **env):
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("OTO_")}
    ambiente.update({"OTO_DATA_BACKEND": "memory", "PYTHONPATH": str(BACKEND), **env})
    processo = subprocess.run([sys.executable, "-c", SONDA_HTTP, json.dumps(origens)], cwd=BACKEND,
                              capture_output=True, text=True, timeout=60, env=ambiente)
    assert processo.returncode == 0, processo.stderr[-2000:]
    return json.loads(processo.stdout.split("@@", 1)[1])


# ------------------------------------------------------------------ navegador ↔ API
@pytest.mark.hospedagem
@pytest.mark.integracao("navegador", "api", "cors")
def test_int_pub_01_cors_da_origem_publicada(tmp_path):
    """CF/EX — só a origem do Pages é autorizada, sem credenciais; Content-Disposition fica legível no navegador."""
    r = _sondar([PAGES, "https://site-malicioso.example", "http://localhost:5173"], OTO_CORS_ORIGINS=PAGES)
    assert r[PAGES]["preflight"] == 200 and r[PAGES]["allow_origin"] == PAGES
    assert r[PAGES]["credenciais"] is None
    assert "content-disposition" in r[PAGES]["expostos"].lower()
    for estranha in ("https://site-malicioso.example", "http://localhost:5173"):
        assert r[estranha]["allow_origin"] is None and r[estranha]["get_allow_origin"] is None


@pytest.mark.hospedagem
@pytest.mark.integracao("navegador", "api", "cors")
def test_int_pub_02_cors_padrao_do_desenvolvimento():
    """CF — sem configuração, a API aceita o Vite local (localhost e 127.0.0.1:5173) e nenhuma outra origem."""
    r = _sondar(["http://localhost:5173", "http://127.0.0.1:5173", PAGES])
    assert r["http://localhost:5173"]["allow_origin"] == "http://localhost:5173"
    assert r["http://127.0.0.1:5173"]["allow_origin"] == "http://127.0.0.1:5173"
    assert r[PAGES]["allow_origin"] is None


@pytest.mark.integracao("proxy", "api", "contrato")
@pytest.mark.parametrize("root_path,esperado", [("/api", "/api"), ("", "/")])
def test_int_pub_03_root_path_do_proxy_no_contrato(root_path, esperado):
    """CF — atrás do Nginx (/api) o Swagger aponta para /api; no Render (raiz), para /."""
    r = _sondar([], OTO_ROOT_PATH=root_path)
    assert r["servers"][0]["url"] == esperado


# ------------------------------------------------------------------ inicialização hospedada
def _config_hospedada(dsn: str) -> dict:
    return {"OTO_DATA_BACKEND": "postgres", "OTO_ENV": "production", "DATABASE_URL": dsn,
            "OTO_SUPABASE_URL": "https://projeto-qa.supabase.co", "OTO_SUPABASE_SERVICE_KEY": "sb_secret_qa",
            "OTO_STORAGE_BUCKET": "oto-arquivos", "OTO_STORAGE_PROVIDER": "supabase",
            "OTO_PUBLIC_URL": "https://isabela-cp.github.io/SSC0536-g3", "OTO_CORS_ORIGINS": PAGES,
            "OTO_BREVO_API_KEY": "xkeysib-qa", "OTO_MAIL_PROVIDER": "brevo", "OTO_MAIL_FROM": "oto@example.test"}


@pytest.mark.hospedagem
@pytest.mark.integracao("configuracao", "start")
@pytest.mark.parametrize("ajuste", [
    {}, {"OTO_PUBLIC_URL": "http://isabela-cp.github.io/SSC0536-g3"}, {"OTO_CORS_ORIGINS": PAGES + "/SSC0536-g3"},
    {"OTO_CORS_ORIGINS": "http://localhost:5173"}, {"OTO_STORAGE_PROVIDER": "local"}, {"OTO_MAIL_PROVIDER": "smtp"},
    {"OTO_ENV": "development"}, {"OTO_BREVO_API_KEY": ""}, {"DATABASE_URL": ""}, {"OTO_SUPABASE_SERVICE_KEY": ""},
], ids=["completa", "url-http", "cors-com-caminho", "cors-http", "storage-local", "smtp", "nao-producao",
        "sem-brevo", "sem-banco", "sem-chave-supabase"])
def test_int_pub_04_validacao_da_configuracao_hospedada(monkeypatch, ajuste):
    """CF/EX — a entrada hospedada só aceita a combinação completa e segura de serviços."""
    from app.start import validate_hosted_config

    for chave, valor in {**_config_hospedada("postgresql://qa@h/db"), **ajuste}.items():
        monkeypatch.setenv(chave, valor)
    if not ajuste:
        validate_hosted_config()
    else:
        with pytest.raises(RuntimeError):
            validate_hosted_config()


@pytest.mark.hospedagem
@pytest.mark.integracao("start", "postgresql", "api")
def test_int_pub_05_primeiro_administrador_uma_unica_vez(banco_vazio, monkeypatch):
    """CF/EX — base vazia cria o admin do segredo; reinícios (inclusive simultâneos) não criam outro nem trocam a senha."""
    from app.start import bootstrap_admin

    db = Database(dsn_do_banco(banco_vazio))
    apply_migrations(db)
    monkeypatch.setenv("OTO_BOOTSTRAP_ADMIN_EMAIL", "curto@example.test")
    monkeypatch.setenv("OTO_BOOTSTRAP_ADMIN_PASSWORD", "curta")
    with pytest.raises(RuntimeError, match="12"):
        bootstrap_admin(db)
    monkeypatch.setenv("OTO_BOOTSTRAP_ADMIN_EMAIL", " Admin.Prefeitura@Example.TEST ")
    monkeypatch.setenv("OTO_BOOTSTRAP_ADMIN_PASSWORD", "senha-inicial-segura")
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: bootstrap_admin(db), range(4)))
    monkeypatch.setenv("OTO_BOOTSTRAP_ADMIN_PASSWORD", "outra-senha-diferente")
    bootstrap_admin(db)
    with psycopg.connect(db.dsn) as conn:
        usuarios = conn.execute("SELECT email, perfil, status FROM usuarios").fetchall()
    assert usuarios == [("admin.prefeitura@example.test", "ADMINISTRADOR", "ATIVO")]
    from fastapi.testclient import TestClient
    from app import main
    cliente = TestClient(main.app)
    assert cliente.post("/auth/login", json={"email": "admin.prefeitura@example.test", "senha": "senha-inicial-segura"}).status_code == 200
    assert cliente.post("/auth/login", json={"email": "admin.prefeitura@example.test", "senha": "outra-senha-diferente"}).status_code == 401


@pytest.mark.hospedagem
@pytest.mark.integracao("start", "uvicorn", "postgresql", "api")
def test_int_pub_06_entrada_hospedada_sobe_e_atende(banco_vazio, tmp_path):
    """CF — `python -m app.start` (comando do Render) aplica migrations, cria o admin, sobe e atende HTTP."""
    with socket.create_server(("127.0.0.1", 0)) as s:
        porta = s.getsockname()[1]
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("OTO_")}
    ambiente.update(_config_hospedada(dsn_do_banco(banco_vazio)))
    ambiente.update({"PORT": str(porta), "OTO_MAILER_EMBEDDED": "false", "PYTHONPATH": str(BACKEND),
                     "OTO_BOOTSTRAP_ADMIN_EMAIL": "admin@prefeitura.example", "OTO_BOOTSTRAP_ADMIN_PASSWORD": "senha-do-render-123"})
    log = open(tmp_path / "start.log", "w")
    processo = subprocess.Popen([sys.executable, "-m", "app.start"], cwd=BACKEND, env=ambiente, stdout=log, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{porta}"
        for _ in range(100):
            try:
                if httpx.get(base + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.fail("a entrada hospedada não respondeu: " + (tmp_path / "start.log").read_text()[-1500:])
        login = httpx.post(base + "/auth/login", json={"email": "admin@prefeitura.example", "senha": "senha-do-render-123"})
        assert login.status_code == 200
        assert httpx.get(base + "/usuarios", headers={"Authorization": "Bearer " + login.json()["access_token"]}).json()["data"][0]["perfil"] == "ADMINISTRADOR"
        semente = httpx.post(base + "/auth/login", json={"email": "marina.admin@example.test", "senha": "admin-demo"})
        assert semente.status_code == 401, "produção não pode conter as contas públicas do seed"
        preflight = httpx.options(base + "/auth/login", headers={"Origin": PAGES, "Access-Control-Request-Method": "POST"})
        assert preflight.headers.get("access-control-allow-origin") == PAGES
    finally:
        processo.terminate()
        processo.wait(15)
        log.close()


@pytest.mark.integracao("migrate", "postgresql", "configuracao")
def test_int_pub_07_seed_bloqueado_fora_do_desenvolvimento(banco_vazio):
    """EX — `python -m app.migrate --seed` em produção falha e não grava contas de demonstração."""
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("OTO_")}
    ambiente.update({"DATABASE_URL": dsn_do_banco(banco_vazio), "OTO_ENV": "production", "PYTHONPATH": str(BACKEND)})
    processo = subprocess.run([sys.executable, "-m", "app.migrate", "--seed"], cwd=BACKEND, env=ambiente,
                              capture_output=True, text=True, timeout=120)
    assert processo.returncode != 0 and "Seed permitido apenas em desenvolvimento" in processo.stderr
    with psycopg.connect(dsn_do_banco(banco_vazio)) as conn:
        assert conn.execute("SELECT count(*) FROM usuarios").fetchone()[0] == 0


@pytest.mark.integracao("configuracao", "api")
def test_int_pub_08_modo_simulado_proibido_em_producao(monkeypatch):
    """EX — OTO_DATA_BACKEND=memory é recusado com OTO_ENV=production (sem fallback silencioso para mocks)."""
    monkeypatch.setenv("OTO_DATA_BACKEND", "memory")
    monkeypatch.setenv("OTO_ENV", "production")
    with pytest.raises(RuntimeError, match="produção"):
        persistent()
    monkeypatch.setenv("OTO_DATA_BACKEND", "json")
    monkeypatch.delenv("OTO_ENV")
    with pytest.raises(RuntimeError):
        persistent()
