"""Fixtures dos testes de ponta a ponta (ver apoio.py para configuração)."""
from __future__ import annotations

import os
import re

import pytest

from apoio import BASE, CAPTURAS, CONTAS, SENHAS, Stack, entrar


def pytest_collection_modifyitems(config, items):
    if BASE:
        return
    pular = pytest.mark.skip(reason="Defina OTO_STACK_URL (stack Docker descartável) para os testes de ponta a ponta.")
    for item in items:
        if "/e2e/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(pular)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultado = (yield).get_result()
    if resultado.when == "call":
        item.resultado_chamada = resultado


@pytest.fixture(scope="session")
def stack() -> Stack:
    from apoio import MAILPIT
    assert MAILPIT, "Defina OTO_MAILPIT_URL junto com OTO_STACK_URL."
    return Stack()


# ------------------------------------------------------------------ navegador
@pytest.fixture(scope="session")
def navegador():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def abrir(navegador, request):
    """abrir(perfil) -> página autenticada pela tela de login. Captura de tela de cada página ao final."""
    paginas = []

    def _abrir(perfil: str | None = "ADMINISTRADOR", *, largura=1280, altura=900, toque=False, email=None, senha=None):
        contexto = navegador.new_context(viewport={"width": largura, "height": altura}, has_touch=toque, locale="pt-BR")
        pagina = contexto.new_page()
        pagina.set_default_timeout(15000)
        paginas.append(pagina)
        pagina.goto(BASE + "/")
        if perfil or email:
            entrar(pagina, email or CONTAS[perfil], senha or SENHAS[perfil])
            pagina.get_by_role("button", name=re.compile("Sair")).wait_for()
        return pagina

    yield _abrir
    resultado = getattr(request.node, "resultado_chamada", None)
    situacao = "falha" if resultado is not None and resultado.failed else "ok"
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    nome = re.sub(r"[^\w.-]+", "_", request.node.name)[:80]
    for i, pagina in enumerate(paginas):
        try:
            pagina.screenshot(path=str(CAPTURAS / f"{nome}_{i}_{situacao}.png"), full_page=True)
        finally:
            pagina.context.close()
