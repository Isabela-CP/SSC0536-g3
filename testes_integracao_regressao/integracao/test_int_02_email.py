"""Integração API ↔ outbox (PostgreSQL) ↔ dispatcher ↔ SMTP real (Mailpit) ou Brevo."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import mailer, main
from app.database import database
from app.postgres_portal import PostgresPortal
from apoio import CONTAS, BrevoFalso, porta_fechada

PUBLICA = "https://oto.example.test"


def _parametros(link: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(link).fragment.partition("?")[2]).items()}


def _criar_conta(sistema, admin, email, perfil="GESTOR"):
    resposta = admin.post("/usuarios", json={"nome": "Conta Integração", "email": email, "perfil": perfil})
    assert resposta.status_code == 201, resposta.text


def _convidar(sistema, email):
    admin = sistema.como("ADMINISTRADOR")
    _criar_conta(sistema, admin, email)
    assert admin.post("/convites", json={"email": email}).status_code == 201


def _fila(sistema, email):
    return sistema.sql("SELECT * FROM email_outbox WHERE lower(destinatario)=%s ORDER BY id", (email.casefold(),))


def _despachar_tudo():
    while mailer.dispatch_one(database()):
        pass


# ------------------------------------------------------------------ fluxo principal
@pytest.mark.integracao("api", "outbox", "dispatcher", "smtp")
def test_int_mail_01_convite_entregue_por_smtp(sistema, mailpit):
    """CF — convite entra na outbox, o dispatcher entrega por SMTP e o link recebido ativa a conta."""
    _convidar(sistema, "convite.smtp@example.test")
    assert [m["enviado_em"] for m in _fila(sistema, "convite.smtp@example.test")] == [None]
    _despachar_tudo()
    [mensagem] = mailpit.esperar("convite.smtp@example.test")
    assert mensagem["From"]["Address"] == "no-reply@oto.example.test"
    assert mensagem["Subject"] == "Ative seu acesso ao OTO"
    link = next(p for p in mailpit.texto(mensagem).split() if p.startswith("http"))
    assert link.startswith(PUBLICA + "/#/ativar-convite?")
    [fila] = _fila(sistema, "convite.smtp@example.test")
    assert fila["enviado_em"] is not None and fila["corpo"] == "" and fila["tentativas"] == 1
    p = _parametros(link)
    assert sistema.anon.post(f"/convites/{p['id']}/aceitacao", json={"token": p["token"], "senha": "senha-via-smtp"}).status_code == 200
    assert sistema.login("convite.smtp@example.test", "senha-via-smtp").get("/perfil").status_code == 200


@pytest.mark.integracao("api", "outbox", "dispatcher", "smtp")
def test_int_mail_02_recuperacao_entregue_e_conta_desconhecida_sem_envio(sistema, mailpit):
    """CF — recuperação chega por SMTP e o link redefine a senha; e-mail desconhecido não gera mensagem."""
    assert sistema.anon.post("/auth/recuperacao-senha", json={"email": CONTAS["GESTOR"]}).status_code == 202
    assert sistema.anon.post("/auth/recuperacao-senha", json={"email": "nao.existe@example.test"}).status_code == 202
    _despachar_tudo()
    [mensagem] = mailpit.esperar(CONTAS["GESTOR"])
    assert len(mailpit.mensagens()) == 1
    link = next(p for p in mailpit.texto(mensagem).split() if p.startswith("http"))
    assert link.startswith(PUBLICA + "/#/redefinir-senha?token=")
    token = _parametros(link)["token"]
    assert sistema.anon.post("/auth/redefinicao-senha", json={"token": token, "senha": "senha-recuperada"}).status_code == 200
    assert sistema.login(CONTAS["GESTOR"], "senha-recuperada").get("/perfil").status_code == 200


# ------------------------------------------------------------------ atomicidade
@pytest.mark.integracao("api", "outbox", "postgresql")
def test_int_mail_03_outbox_na_mesma_transacao(sistema, mailpit, monkeypatch):
    """EX — se a operação falha depois de enfileirar (falha na auditoria), não sobra convite nem e-mail."""
    admin = sistema.como("ADMINISTRADOR")
    _criar_conta(sistema, admin, "atomico@example.test")
    original = PostgresPortal.audit

    def auditoria_falha(self, actor, action, *args, **kwargs):
        if action == "CONVITE_CRIADO":
            raise RuntimeError("falha simulada na auditoria")
        return original(self, actor, action, *args, **kwargs)

    monkeypatch.setattr(PostgresPortal, "audit", auditoria_falha)
    assert admin.post("/convites", json={"email": "atomico@example.test"}).status_code == 500
    assert _fila(sistema, "atomico@example.test") == []
    assert sistema.sql("SELECT count(*) AS n FROM convites WHERE email_destinatario=%s", ("atomico@example.test",))[0]["n"] == 0
    _despachar_tudo()
    assert mailpit.mensagens() == []


# ------------------------------------------------------------------ falhas do transporte
@pytest.mark.integracao("dispatcher", "smtp", "outbox")
def test_int_mail_04_smtp_fora_do_ar_e_reenvio(sistema, mailpit, monkeypatch):
    """EX — SMTP indisponível: tentativa registrada sem vazar o link; quando volta, a mesma mensagem é entregue."""
    _convidar(sistema, "reenvio@example.test")
    monkeypatch.setenv("OTO_SMTP_PORT", str(porta_fechada()))
    assert mailer.dispatch_one(database()) is True
    [fila] = _fila(sistema, "reenvio@example.test")
    assert fila["enviado_em"] is None and fila["tentativas"] == 1
    assert fila["ultimo_erro"].startswith("Falha no transporte")     # genérico: sem link, token ou resposta do servidor
    assert "token" not in fila["ultimo_erro"] and "token" in fila["corpo"]                       # link preservado para a próxima tentativa
    monkeypatch.setenv("OTO_SMTP_PORT", str(mailpit.smtp_porta))
    _despachar_tudo()
    assert len(mailpit.esperar("reenvio@example.test")) == 1
    [fila] = _fila(sistema, "reenvio@example.test")
    assert fila["enviado_em"] is not None and fila["tentativas"] == 2 and fila["ultimo_erro"] is None


@pytest.mark.integracao("dispatcher", "smtp", "outbox")
def test_int_mail_05_limite_de_dez_tentativas(sistema, mailpit, monkeypatch):
    """EX — após dez falhas a mensagem sai da fila automática (exige inspeção), mesmo com o SMTP de volta."""
    _convidar(sistema, "limite@example.test")
    monkeypatch.setenv("OTO_SMTP_PORT", str(porta_fechada()))
    tentativas = 0
    while mailer.dispatch_one(database()):
        tentativas += 1
        assert tentativas <= 10
    assert tentativas == 10
    monkeypatch.setenv("OTO_SMTP_PORT", str(mailpit.smtp_porta))
    assert mailer.dispatch_one(database()) is False
    assert mailpit.mensagens() == []
    assert _fila(sistema, "limite@example.test")[0]["tentativas"] == 10


@pytest.mark.integracao("dispatcher", "smtp", "outbox", "locks")
def test_int_mail_06_dispatchers_concorrentes_sem_duplicar(sistema, mailpit):
    """EX — quatro dispatchers simultâneos (SKIP LOCKED) entregam doze convites exatamente uma vez cada."""
    admin = sistema.como("ADMINISTRADOR")
    emails = [f"lote{i:02d}@example.test" for i in range(12)]
    for email in emails:
        _criar_conta(sistema, admin, email)
        assert admin.post("/convites", json={"email": email}).status_code == 201

    def trabalhar(_):
        enviados = 0
        while mailer.dispatch_one(database()):
            enviados += 1
        return enviados

    with ThreadPoolExecutor(4) as pool:
        por_worker = list(pool.map(trabalhar, range(4)))
    assert sum(por_worker) == 12
    time.sleep(0.5)
    destinos = sorted(t["Address"] for m in mailpit.mensagens() for t in m["To"])
    assert destinos == emails
    assert {r["tentativas"] for r in sistema.sql("SELECT tentativas FROM email_outbox WHERE destinatario LIKE 'lote%%'")} == {1}


@pytest.mark.integracao("dispatcher", "configuracao")
def test_int_mail_07_sem_servidor_configurado_nao_envia(sistema, mailpit, monkeypatch):
    """EX — sem OTO_SMTP_HOST o worker não envia nem consome tentativas; a mensagem aguarda configuração."""
    _convidar(sistema, "sem.host@example.test")
    monkeypatch.delenv("OTO_SMTP_HOST")
    assert mailer.dispatch_one(database()) is False
    [fila] = _fila(sistema, "sem.host@example.test")
    assert fila["enviado_em"] is None and fila["tentativas"] == 0


@pytest.mark.hospedagem
@pytest.mark.integracao("dispatcher", "configuracao")
def test_int_mail_07b_provedor_desconhecido_recusado(sistema, monkeypatch):
    """EX — provedor de e-mail fora de smtp/brevo é recusado em vez de descartar mensagens em silêncio."""
    monkeypatch.setenv("OTO_MAIL_PROVIDER", "sendgrid")
    with pytest.raises(RuntimeError, match="OTO_MAIL_PROVIDER"):
        mailer.dispatch_one(database())


# ------------------------------------------------------------------ hospedagem (PR #39)
@pytest.mark.hospedagem
@pytest.mark.integracao("api", "lifespan", "dispatcher", "smtp")
def test_int_mail_08_dispatcher_embutido_na_api(sistema, mailpit, monkeypatch):
    """CF — com OTO_MAILER_EMBEDDED (Render), a própria API entrega a fila e encerra a thread ao parar."""
    monkeypatch.setenv("OTO_MAILER_EMBEDDED", "true")
    _criar_conta(sistema, sistema.como("ADMINISTRADOR"), "embutido@example.test")
    token = sistema.anon.post("/auth/login", json={"email": CONTAS["ADMINISTRADOR"], "senha": "admin-demo"}).json()["access_token"]
    with TestClient(main.app, headers={"Authorization": "Bearer " + token}) as cliente:
        assert any(t.name == "oto-mailer" and t.is_alive() for t in threading.enumerate())
        assert cliente.post("/convites", json={"email": "embutido@example.test"}).status_code == 201
        assert len(mailpit.esperar("embutido@example.test", segundos=15)) == 1
    assert not any(t.name == "oto-mailer" and t.is_alive() for t in threading.enumerate())


@pytest.mark.hospedagem
@pytest.mark.integracao("dispatcher", "brevo", "outbox")
def test_int_mail_09_brevo_falha_e_entrega(sistema, mailpit, monkeypatch):
    """CF/EX — provedor Brevo: chamada HTTPS com a chave do servidor; erro 500 conta tentativa; depois entrega."""
    brevo = BrevoFalso()
    monkeypatch.setattr(mailer.send_brevo, "__defaults__", (brevo,))
    monkeypatch.setenv("OTO_MAIL_PROVIDER", "brevo")
    monkeypatch.setenv("OTO_BREVO_API_KEY", "xkeysib-qa-segredo")
    monkeypatch.delenv("OTO_SMTP_HOST")
    assert sistema.anon.post("/auth/recuperacao-senha", json={"email": CONTAS["EDITOR"]}).status_code == 202
    brevo.status = 500
    assert mailer.dispatch_one(database()) is True
    [fila] = _fila(sistema, CONTAS["EDITOR"])
    assert fila["enviado_em"] is None and fila["tentativas"] == 1
    assert "xkeysib" not in (fila["ultimo_erro"] or "")
    brevo.status = 201
    assert mailer.dispatch_one(database()) is True
    chamada = brevo.chamadas[-1]
    assert chamada["url"] == "https://api.brevo.com/v3/smtp/email"
    assert chamada["headers"]["api-key"] == "xkeysib-qa-segredo"
    assert chamada["json"]["to"] == [{"email": CONTAS["EDITOR"]}]
    assert chamada["json"]["sender"]["email"] == "no-reply@oto.example.test"
    assert PUBLICA + "/#/redefinir-senha?token=" in chamada["json"]["textContent"]
    assert _fila(sistema, CONTAS["EDITOR"])[0]["corpo"] == ""
    assert mailpit.mensagens() == []                       # nada vai ao SMTP quando o provedor é Brevo
