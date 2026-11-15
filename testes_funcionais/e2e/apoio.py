"""Apoio aos testes funcionais de ponta a ponta: stack Docker completa (Nginx, API, worker, Mailpit, PostgreSQL)
e telas no navegador (Playwright/Chromium).

Configuração:
  OTO_STACK_URL     URL do frontend Nginx (ex.: http://localhost:8091) — obrigatória
  OTO_MAILPIT_URL   URL da interface do Mailpit (ex.: http://localhost:8026)
  OTO_E2E_CAPTURAS  diretório para as capturas de tela (evidência)

Os testes escrevem dados fictícios com nomes e CNPJs únicos; use somente stacks descartáveis.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

BASE = os.getenv("OTO_STACK_URL", "").rstrip("/")
MAILPIT = os.getenv("OTO_MAILPIT_URL", "").rstrip("/")
CAPTURAS = Path(os.getenv("OTO_E2E_CAPTURAS", "/tmp/oto-e2e-capturas"))
SENHAS = {"ADMINISTRADOR": "admin-demo", "GESTOR": "gestor-demo", "EDITOR": "editor-demo", "HOTEL": "hotel-demo"}
CONTAS = {"ADMINISTRADOR": "marina.admin@example.test", "GESTOR": "rafael.consulta@example.test",
          "EDITOR": "camila.editora@example.test", "HOTEL": "responsavel@serra-azul.example"}
SERRA_AZUL = "11111111-1111-4111-8111-111111111111"


# ------------------------------------------------------------------ API da stack
def unico(prefixo: str) -> str:
    return f"{prefixo} {uuid4().hex[:8]}"


def cnpj_unico() -> str:
    base = str(int(uuid4().hex[:12], 16))[-8:].zfill(8) + "0001"
    def digito(valor, pesos):
        resto = sum(int(n) * p for n, p in zip(valor, pesos)) % 11
        return str(0 if resto < 2 else 11 - resto)
    base += digito(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base + digito(base, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])


class Stack:
    def __init__(self):
        self.http = httpx.Client(base_url=BASE, timeout=30)

    def cliente(self, perfil: str = "ADMINISTRADOR", email: str | None = None, senha: str | None = None) -> httpx.Client:
        resposta = self.http.post("/api/auth/login", json={"email": email or CONTAS[perfil], "senha": senha or SENHAS[perfil]})
        assert resposta.status_code == 200, resposta.text
        return httpx.Client(base_url=BASE + "/api", timeout=60,
                            headers={"Authorization": "Bearer " + resposta.json()["access_token"]})

    def criar_hospedagem(self, **extra) -> dict:
        nome = unico("Hospedagem E2E")
        corpo = {"id_categoria": 1, "nome_fantasia": nome, "razao_social": nome + " Ltda.",
                 "cnpj": cnpj_unico(), "endereco": "Rua dos Testes E2E, 1, Olímpia - SP", **extra}
        resposta = self.cliente().post("/estabelecimentos", json=corpo)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    def buscar(self, termo: str) -> list[dict]:
        return self.cliente("GESTOR").get("/estabelecimentos", params={"busca": termo}).json()["data"]

    # Mailpit: a caixa de entrada real, alimentada pelo worker via SMTP
    def emails_para(self, endereco: str) -> list[dict]:
        resposta = httpx.get(f"{MAILPIT}/api/v1/search", params={"query": f'to:"{endereco}"'}, timeout=10)
        resposta.raise_for_status()
        return resposta.json().get("messages") or []

    def esperar_email(self, endereco: str, ja_existentes: int = 0, limite: float = 40) -> str:
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            mensagens = self.emails_para(endereco)
            if len(mensagens) > ja_existentes:
                identificador = mensagens[0]["ID"]
                return httpx.get(f"{MAILPIT}/api/v1/message/{identificador}", timeout=10).json()["Text"]
            time.sleep(1)
        raise AssertionError(f"nenhum e-mail novo para {endereco} em {limite:.0f}s")


def entrar(pagina, email: str, senha: str):
    pagina.get_by_label("E-mail").fill(email)
    pagina.get_by_label("Senha").fill(senha)
    pagina.get_by_role("button", name="Entrar no Sistema").click()


def ir(pagina, rota: str):
    pagina.goto(f"{BASE}/#{rota}")
    pagina.get_by_role("main").wait_for()


def defeito(codigo: str, motivo: str):
    """Mesmo contrato do conftest da suíte de API: xfail estrito + marcador com o código."""
    def aplicar(func):
        func = pytest.mark.defeito(codigo)(func)
        return pytest.mark.xfail(strict=True, reason=f"{codigo}: {motivo}")(func)
    return aplicar


def escolher_opcao(select, trecho: str):
    """Seleciona a opção cujo texto contém `trecho` (select_option não aceita regex nesta versão)."""
    rotulo = select.locator("option", has_text=trecho).first.inner_text()
    select.select_option(label=rotulo)
