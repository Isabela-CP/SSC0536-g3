"""Telas do sistema no navegador (Chromium): os fluxos dos casos de uso como o usuário os executa."""
import re
from datetime import date, timedelta

import pytest

expect = pytest.importorskip("playwright.sync_api", reason="Playwright não instalado; use a imagem de testes_funcionais/e2e/Dockerfile.").expect

from apoio import CONTAS, SERRA_AZUL, cnpj_unico, escolher_opcao, ir, unico

PROIBIDO = "Seu perfil não pode acessar esta área."


def _menu(pagina) -> set[str]:
    return {link.inner_text().strip() for link in pagina.get_by_role("navigation").get_by_role("link").all()}


# ------------------------------------------------------------------ UC00
@pytest.mark.uc("UC00")
@pytest.mark.parametrize("perfil,menu", [
    ("ADMINISTRADOR", {"Início", "Inventário", "Convites", "Pesquisas", "Auditoria", "Perfil"}),
    ("EDITOR", {"Início", "Inventário", "Pesquisas", "Perfil"}),
    ("GESTOR", {"Início", "Inventário", "Pesquisas", "Perfil"}),
    ("HOTEL", {"Início", "Meu cadastro", "Perfil"})])
def test_ft_ui_01_login_mostra_funcoes_do_perfil(abrir, perfil, menu):
    """CF — após o login, o menu exibe apenas as funções permitidas ao perfil (UC00 passo 5)."""
    assert _menu(abrir(perfil)) == menu


@pytest.mark.uc("UC00")
def test_ft_ui_02_login_invalido(abrir):
    """EX 3a — credenciais inválidas: mensagem de erro e nova tentativa possível."""
    pagina = abrir(None)
    pagina.get_by_label("E-mail").fill(CONTAS["ADMINISTRADOR"])
    pagina.get_by_label("Senha").fill("senha-errada")
    pagina.get_by_role("button", name="Entrar no Sistema").click()
    expect(pagina.get_by_role("alert")).to_have_text("E-mail ou senha inválidos.")
    expect(pagina.get_by_role("button", name="Entrar no Sistema")).to_be_enabled()


@pytest.mark.uc("UC00")
@pytest.mark.parametrize("perfil,rota", [("EDITOR", "/contas"), ("GESTOR", "/auditoria"),
                                         ("GESTOR", "/estabelecimentos/novo"), ("HOTEL", "/inventario")])
def test_ft_ui_03_rota_nao_permitida(abrir, perfil, rota):
    """EX 4a — acesso direto a uma função não permitida: a tela nega e explica."""
    pagina = abrir(perfil)
    ir(pagina, rota)
    expect(pagina.get_by_role("main").get_by_role("alert")).to_have_text(PROIBIDO)


@pytest.mark.uc("UC00", "UC05")
def test_ft_ui_04_gestor_sem_acoes_de_escrita(abrir):
    """EX — o GESTOR consulta o inventário sem botões de cadastro, edição ou inativação."""
    pagina = abrir("GESTOR")
    ir(pagina, "/inventario")
    tabela = pagina.get_by_role("table", name="Inventário de hospedagens")
    expect(tabela.get_by_role("link", name="Ver detalhes").first).to_be_visible()
    for acao in ("Editar", "Inativar", "Reativar"):
        expect(tabela.get_by_role("link", name=acao, exact=True)).to_have_count(0)
    expect(pagina.get_by_role("link", name="Cadastrar Estabelecimento")).to_have_count(0)


# ------------------------------------------------------------------ UC01 / UC02
def _preencher_cadastro(pagina, nome, cnpj):
    pagina.get_by_label("Nome da Empresa").fill(nome)
    pagina.get_by_label("Razão social").fill(nome + " Ltda.")
    pagina.get_by_label("Categoria").select_option(label="Meios de hospedagem")
    pagina.get_by_label("CNPJ").fill(cnpj)
    pagina.get_by_label("Endereço").fill("Rua das Telas, 10, Olímpia - SP")


@pytest.mark.uc("UC01")
def test_ft_ui_05_cadastro_vazio_destaca_obrigatorios(abrir):
    """EX 5a — salvar sem preencher: os campos obrigatórios são apontados."""
    pagina = abrir("ADMINISTRADOR")
    ir(pagina, "/estabelecimentos/novo")
    pagina.get_by_role("button", name="Salvar", exact=True).click()
    alerta = pagina.get_by_role("main").get_by_role("alert")
    for campo in ("Categoria", "Nome da Empresa", "Razão social", "CNPJ", "Endereço"):
        expect(alerta).to_contain_text(f"{campo}: Campo obrigatório.")


@pytest.mark.uc("UC01", "UC05")
def test_ft_ui_06_cadastro_pela_tela(abrir, stack):
    """CF — ADMIN cadastra pela tela; o estabelecimento aparece no inventário como ativo."""
    nome = unico("Hotel Tela")
    pagina = abrir("ADMINISTRADOR")
    ir(pagina, "/estabelecimentos/novo")
    _preencher_cadastro(pagina, nome, cnpj_unico())
    pagina.get_by_role("button", name="Salvar", exact=True).click()
    pagina.wait_for_timeout(1500)
    encontrados = stack.buscar(nome)
    assert len(encontrados) == 1 and encontrados[0]["status"] == "ATIVO"
    ir(pagina, "/inventario")
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill(nome)
    pagina.get_by_role("button", name="Pesquisar").click()
    expect(pagina.get_by_role("row", name=re.compile(re.escape(nome)))).to_contain_text("Ativo")


@pytest.mark.uc("UC01")
def test_ft_ui_07_cancelar_cadastro_nao_grava(abrir, stack):
    """CF 4a — preencher e cancelar: nada é gravado."""
    nome = unico("Hotel Cancelado")
    pagina = abrir("ADMINISTRADOR")
    ir(pagina, "/estabelecimentos/novo")
    _preencher_cadastro(pagina, nome, cnpj_unico())
    pagina.get_by_role("button", name="Cancelar").click()
    pagina.wait_for_timeout(1000)
    assert stack.buscar(nome) == []


@pytest.mark.uc("UC01")
def test_ft_ui_08_cnpj_duplicado_na_tela(abrir, stack):
    """EX 5b — CNPJ já cadastrado: a tela avisa e nada é gravado."""
    nome = unico("Hotel Duplicado")
    pagina = abrir("ADMINISTRADOR")
    ir(pagina, "/estabelecimentos/novo")
    _preencher_cadastro(pagina, nome, "54.839.271/0001-64")
    pagina.get_by_role("button", name="Salvar", exact=True).click()
    expect(pagina.get_by_role("main").get_by_role("alert").filter(has_text="CNPJ").first).to_be_visible()
    assert stack.buscar(nome) == []


# ------------------------------------------------------------------ UC04
@pytest.mark.uc("UC04")
def test_ft_ui_09_inativacao_com_confirmacao(abrir, stack):
    """CF/EX 3a — o diálogo exige motivo; cancelar mantém ativo; confirmar inativa sem excluir."""
    hospedagem = stack.criar_hospedagem()
    nome = hospedagem["nome_fantasia"]
    pagina = abrir("ADMINISTRADOR")
    ir(pagina, "/inventario")
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill(nome)
    pagina.get_by_role("button", name="Pesquisar").click()
    linha = pagina.get_by_role("row", name=re.compile(re.escape(nome)))

    linha.get_by_role("link", name="Inativar").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_role("button", name="Cancelar").click()
    expect(dialogo).to_have_count(0)
    assert stack.buscar(nome)[0]["status"] == "ATIVO"

    ir(pagina, "/inventario")
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill(nome)
    pagina.get_by_role("button", name="Pesquisar").click()
    pagina.get_by_role("row", name=re.compile(re.escape(nome))).get_by_role("link", name="Inativar").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_role("button", name="Inativar").click()
    pagina.wait_for_timeout(800)
    expect(dialogo).to_be_visible()                     # sem motivo, o diálogo não fecha
    assert stack.buscar(nome)[0]["status"] == "ATIVO", "inativou sem motivo"
    dialogo.get_by_role("textbox").fill("Encerramento das atividades (teste de interface)")
    dialogo.get_by_role("button", name="Inativar").click()
    expect(dialogo).to_have_count(0)
    pagina.wait_for_timeout(800)
    assert stack.buscar(nome)[0]["status"] == "INATIVO"


# ------------------------------------------------------------------ UC05
@pytest.mark.uc("UC05")
def test_ft_ui_10_busca_e_sem_resultados(abrir):
    """CF/EX 3a — a busca filtra a tabela; sem resultados a tela informa."""
    pagina = abrir("EDITOR")
    ir(pagina, "/inventario")
    tabela = pagina.get_by_role("table", name="Inventário de hospedagens")
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill("Serra Azul")
    pagina.get_by_role("button", name="Pesquisar").click()
    expect(tabela.get_by_role("row")).to_have_count(2)            # cabeçalho + 1
    expect(tabela).to_contain_text("Hotel Serra Azul")
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill("zzz-nenhuma-hospedagem")
    pagina.get_by_role("button", name="Pesquisar").click()
    expect(tabela).to_contain_text("Nenhuma hospedagem encontrada.")


@pytest.mark.uc("UC05")
def test_ft_ui_11_sem_resultados_sugere_limpar_filtros(abrir):
    """EX 3a — além de informar, o sistema sugere limpar os filtros."""
    pagina = abrir("EDITOR")
    ir(pagina, "/inventario")
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill("zzz-nenhuma-hospedagem")
    pagina.get_by_role("button", name="Pesquisar").click()
    expect(pagina.get_by_role("main")).to_contain_text("Nenhuma hospedagem encontrada.")
    candidatos = pagina.get_by_role("main").get_by_text(re.compile("limpar", re.I)).all()
    candidatos += pagina.get_by_role("main").get_by_role("button", name=re.compile("limpar", re.I)).all()
    assert any(elemento.is_visible() for elemento in candidatos), "nenhuma sugestão visível de limpar os filtros"


# ------------------------------------------------------------------ UC13 / UC14
@pytest.mark.uc("UC13")
def test_ft_ui_12_editor_cria_pesquisa_pela_tela(abrir, stack):
    """CF — EDITOR prepara, confirma e disponibiliza a pesquisa para a hospedagem escolhida."""
    titulo = unico("Pesquisa Tela")
    pagina = abrir("EDITOR")
    ir(pagina, "/pesquisas")
    pagina.get_by_role("button", name="Preparar Nova Pesquisa").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Título").fill(titulo)
    dialogo.get_by_label("Tipo").select_option(label="Expectativa")
    dialogo.get_by_label("Data de início").fill("2027-03-01")
    dialogo.get_by_label("Data final").fill("2027-03-31")
    dialogo.get_by_label("Hotel Serra Azul").check()
    dialogo.get_by_role("button", name="Continuar").click()
    pagina.get_by_role("dialog", name="Confirmar pesquisa").get_by_role("button", name="Confirmar e disponibilizar").click()
    expect(pagina.get_by_role("table", name="Pesquisas de ocupação")).to_contain_text(titulo)
    pesquisas = stack.cliente("EDITOR").get("/pesquisas-ocupacao").json()["data"]
    criada = next(p for p in pesquisas if p["titulo"] == titulo)
    assert criada["status"] == "ABERTA" and criada["estabelecimentos"] == [SERRA_AZUL] and criada["tipo"] == "EXPECTATIVA"


def _pesquisa_para_serra_azul(stack) -> str:
    titulo = unico("Pesquisa E2E")
    inicio = date(2027, 5, 1) + timedelta(days=int(titulo[-2:], 16) % 60)
    resposta = stack.cliente("EDITOR").post("/pesquisas-ocupacao", json={
        "titulo": titulo, "tipo": "EXPECTATIVA", "periodo_inicio": inicio.isoformat(),
        "periodo_fim": (inicio + timedelta(days=10)).isoformat(), "estabelecimentos": [SERRA_AZUL]})
    assert resposta.status_code == 201, resposta.text
    return titulo


@pytest.mark.uc("UC14")
def test_ft_ui_13_empresario_responde_pela_tela(abrir, stack):
    """CF — o empresário escolhe a pesquisa, informa a taxa e vê a resposta registrada."""
    titulo = _pesquisa_para_serra_azul(stack)
    pagina = abrir("HOTEL")
    escolher_opcao(pagina.get_by_label("Pesquisa / período"), titulo)
    pagina.get_by_role("button", name="Enviar Resposta").click()
    dialogo = pagina.get_by_role("dialog", name=titulo)
    dialogo.get_by_label("Taxa de ocupação (%)").fill("64.5")
    dialogo.get_by_role("button", name="Continuar").click()
    confirmacao = pagina.get_by_role("dialog", name=titulo)
    expect(confirmacao).to_contain_text("64.5%")
    confirmacao.get_by_role("button", name="Confirmar e enviar").click()
    expect(pagina.get_by_role("dialog")).to_have_count(0)
    expect(pagina.get_by_label("Pesquisa / período")).not_to_contain_text(titulo)
    historico = stack.cliente(email=CONTAS["HOTEL"], senha="hotel-demo").get("/respostas-ocupacao/historico").json()["data"]
    assert 64.5 in {h["dados"]["taxa_ocupacao"] for h in historico}


@pytest.mark.uc("UC14")
@pytest.mark.parametrize("taxa", ["150", "-1"])
def test_ft_ui_14_taxa_invalida_na_tela(abrir, stack, taxa):
    """EX 4a — taxa fora de 0 a 100: a tela recusa e nada é enviado."""
    titulo = _pesquisa_para_serra_azul(stack)
    pagina = abrir("HOTEL")
    escolher_opcao(pagina.get_by_label("Pesquisa / período"), titulo)
    pagina.get_by_role("button", name="Enviar Resposta").click()
    dialogo = pagina.get_by_role("dialog", name=titulo)
    dialogo.get_by_label("Taxa de ocupação (%)").fill(taxa)
    dialogo.get_by_role("button", name="Continuar").click()
    pagina.wait_for_timeout(800)
    expect(pagina.get_by_role("button", name="Confirmar e enviar")).to_have_count(0)
    expect(dialogo).to_contain_text("Informe uma taxa entre 0 e 100%.")
    historico = stack.cliente(email=CONTAS["HOTEL"], senha="hotel-demo").get("/respostas-ocupacao/historico").json()["data"]
    pesquisas = {p["id_pesquisa"]: p["titulo"] for p in stack.cliente("EDITOR").get("/pesquisas-ocupacao").json()["data"]}
    assert all(pesquisas.get(h["id_pesquisa"]) != titulo for h in historico)


# ------------------------------------------------------------------ UC12
@pytest.mark.uc("UC12")
def test_ft_ui_15_empresario_edita_proprio_cadastro(abrir, stack):
    """CF — 'Meu cadastro' abre a própria ficha; a alteração salva aparece na API."""
    hotel_api = stack.cliente(email=CONTAS["HOTEL"], senha="hotel-demo")
    original = hotel_api.get(f"/estabelecimentos/{SERRA_AZUL}").json()["email_comercial"]
    novo = unico("contato").replace(" ", ".") + "@serra-azul.example"
    pagina = abrir("HOTEL")
    pagina.get_by_role("navigation").get_by_role("link", name="Meu cadastro").click()
    campo = pagina.get_by_label("E-mail de Contato")
    expect(campo).to_have_value(original)
    expect(pagina.get_by_label("CNPJ")).to_be_disabled()
    campo.fill(novo)
    pagina.get_by_role("button", name="Salvar Meus Dados").click()
    pagina.wait_for_timeout(1500)
    try:
        assert hotel_api.get(f"/estabelecimentos/{SERRA_AZUL}").json()["email_comercial"] == novo
    finally:
        hotel_api.patch(f"/estabelecimentos/{SERRA_AZUL}", json={"email_comercial": original})


# ------------------------------------------------------------------ UC08
@pytest.mark.uc("UC08")
def test_ft_ui_16_auditoria_mostra_alteracao(abrir, stack):
    """CF — a tela de auditoria lista a alteração recente com seu autor."""
    hospedagem = stack.criar_hospedagem()
    pagina = abrir("ADMINISTRADOR")
    ir(pagina, "/auditoria")
    principal = pagina.get_by_role("main")
    expect(principal).to_contain_text(CONTAS["ADMINISTRADOR"])
    expect(principal.get_by_text(re.compile(re.escape(hospedagem["nome_fantasia"]) + "|" + hospedagem["id_estabelecimento"])).first).to_be_visible()


# ------------------------------------------------------------------ RNF-01
@pytest.mark.uc("RNF-01")
def test_ft_ui_17_uso_em_tablet(abrir):
    """CF RNF-01 — em tablet (768x1024, toque) o inventário é utilizável sem rolagem horizontal da página."""
    pagina = abrir("EDITOR", largura=768, altura=1024, toque=True)
    ir(pagina, "/inventario")
    pagina.get_by_label("Pesquisar Nome/CNPJ").tap()
    pagina.get_by_label("Pesquisar Nome/CNPJ").fill("Serra")
    pagina.get_by_role("button", name="Pesquisar").tap()
    expect(pagina.get_by_role("table", name="Inventário de hospedagens")).to_contain_text("Hotel Serra Azul")
    largura_documento = pagina.evaluate("document.documentElement.scrollWidth")
    assert largura_documento <= 768, f"página com {largura_documento}px de largura em tela de 768px"
