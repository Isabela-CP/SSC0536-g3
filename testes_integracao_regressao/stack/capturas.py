"""Capturas de tela (evidências) da integração, tiradas na stack descartável com o Playwright.

Uso (imagem oto-qa-playwright, rede do host):
  python3 testes_integracao_regressao/stack/capturas.py normal       # Mailpit, Swagger, telas com dados integrados
  python3 testes_integracao_regressao/stack/capturas.py banco_fora   # rodar com o serviço db parado
Variáveis: OTO_STACK_URL, OTO_STACK_MAILPIT, OTO_CAPTURAS (diretório de saída).
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ["OTO_STACK_URL"].rstrip("/")
MAILPIT = os.environ["OTO_STACK_MAILPIT"].rstrip("/")
SAIDA = Path(os.environ.get("OTO_CAPTURAS", "capturas"))
SERRA_AZUL = "11111111-1111-4111-8111-111111111111"


def entrar(pagina, email="marina.admin@example.test", senha="admin-demo", esperar=True):
    pagina.goto(BASE + "/")
    pagina.get_by_label("E-mail").fill(email)
    pagina.get_by_label("Senha").fill(senha)
    pagina.get_by_role("button", name="Entrar no Sistema").click()
    if esperar:
        pagina.get_by_role("button", name="↪ Sair").wait_for()


def normal(navegador):
    pagina = navegador.new_page(viewport={"width": 1280, "height": 800})
    pagina.goto(MAILPIT + "/")
    pagina.get_by_text("Ative seu acesso ao OTO").first.wait_for()
    pagina.screenshot(path=SAIDA / "int_mailpit_caixa.png")
    pagina.get_by_text("Ative seu acesso ao OTO").first.click()
    pagina.get_by_text("Ative seu acesso pelo link").first.wait_for()
    pagina.screenshot(path=SAIDA / "int_mailpit_convite.png")

    pagina.goto(BASE + "/api/docs")
    pagina.locator(".swagger-ui .information-container").wait_for()
    pagina.screenshot(path=SAIDA / "int_swagger_nginx.png")

    entrar(pagina)
    pagina.goto(f"{BASE}/#/estabelecimentos/{SERRA_AZUL}/editar")
    secao = pagina.locator("section[aria-labelledby='documents-title']")
    expect(secao).to_contain_text("recriado.pdf", timeout=20000)
    secao.scroll_into_view_if_needed()
    secao.screenshot(path=SAIDA / "int_documentos_apos_recriacao.png")
    secao.get_by_role("button", name="Baixar Alvará").first.click()      # documento do seed (DF-11)
    secao.get_by_role("alert").first.wait_for(timeout=15000)
    secao.screenshot(path=SAIDA / "int_df11_baixar_documento_seed.png")

    pagina.goto(BASE + "/#/contas")
    expect(pagina.get_by_role("main")).to_contain_text("Equipe Interna", timeout=20000)
    for _ in range(10):                      # a lista é paginada; avança até a conta ativada pelo e-mail
        if pagina.get_by_text("fila.", exact=False).count():
            break
        pagina.get_by_role("button", name="Próximo ›").first.click()
    expect(pagina.get_by_role("main")).to_contain_text("fila.")
    pagina.get_by_text("fila.", exact=False).first.scroll_into_view_if_needed()
    pagina.screenshot(path=SAIDA / "int_conta_ativada_por_email.png", full_page=False)


def banco_fora(navegador):
    pagina = navegador.new_page(viewport={"width": 1280, "height": 800})
    entrar(pagina, esperar=False)
    pagina.get_by_role("alert").first.wait_for(timeout=20000)
    pagina.screenshot(path=SAIDA / "int_login_banco_indisponivel.png")


if __name__ == "__main__":
    SAIDA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            {"normal": normal, "banco_fora": banco_fora}[sys.argv[1]](navegador)
        finally:
            navegador.close()
    print("capturas em", SAIDA)
