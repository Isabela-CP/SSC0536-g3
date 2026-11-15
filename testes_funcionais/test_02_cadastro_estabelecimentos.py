"""UC01 — Cadastrar empresa por categoria (RF-01) e UC02 — Campos específicos (RF-02).

Decisão documentada (protótipos e OpenAPI): o cadastro é exclusivo do ADMINISTRADOR;
EDITOR edita a ficha, exceto CNPJ e razão social; HOTEL edita apenas a própria ficha.
"""
import pytest

from apoio_api import CNPJ_LIVRE, CNPJ_SERRA_AZUL, SERRA_AZUL, defeito, erro, novo_estabelecimento

pytestmark = pytest.mark.uc("UC01")


@pytest.mark.uc("UC02")
def test_ft_cad_01_cadastro_hospedagem_completo(api):
    """CF — ADMIN cadastra hotel com campos comuns e específicos; registro ativo e persistido."""
    admin = api.como("ADMINISTRADOR")
    payload = novo_estabelecimento(telefone_comercial="+55 17 3333-0000",
                                   meio_hospedagem={"tipo_hospedagem": "HOTEL", "total_uh": 30, "total_leitos": 60})
    resposta = admin.post("/estabelecimentos", json=payload)
    assert resposta.status_code == 201, resposta.text
    criado = resposta.json()
    assert criado["status"] == "ATIVO" and criado["id_categoria"] == 1
    ficha = admin.get(f"/estabelecimentos/{criado['id_estabelecimento']}").json()
    assert ficha["nome_fantasia"] == "Hotel Funcional"
    assert ficha["meio_hospedagem"]["total_uh"] == 30 and ficha["meio_hospedagem"]["total_leitos"] == 60
    assert admin.get("/estabelecimentos", params={"busca": "Hotel Funcional"}).json()["pagination"]["total"] == 1


@pytest.mark.uc("UC02")
def test_ft_cad_02_cadastro_outra_categoria(api):
    """CF — categoria 2 (alimentação e bebidas) aceita seu bloco específico."""
    admin = api.como("ADMINISTRADOR")
    categorias = {c["id_categoria"]: c["nome_categoria"] for c in admin.get("/categorias-estabelecimento").json()["data"]}
    assert "alimentação" in categorias[2].casefold()
    resposta = admin.post("/estabelecimentos", json=novo_estabelecimento(
        id_categoria=2, nome_fantasia="Restaurante Funcional", alimentacao_bebidas={"capacidade": 80}))
    assert resposta.status_code == 201, resposta.text
    ficha = admin.get(f"/estabelecimentos/{resposta.json()['id_estabelecimento']}").json()
    assert ficha["id_categoria"] == 2 and ficha["alimentacao_bebidas"]["capacidade"] == 80


@pytest.mark.parametrize("campo", ["nome_fantasia", "razao_social", "cnpj", "endereco"])
def test_ft_cad_03_campo_obrigatorio_ausente(api, campo):
    """EX 5a — obrigatório ausente: 422 indicando o campo; nada é gravado."""
    payload = novo_estabelecimento()
    del payload[campo]
    admin = api.como("ADMINISTRADOR")
    resposta = admin.post("/estabelecimentos", json=payload)
    assert resposta.status_code == 422
    assert campo in " ".join(erro(resposta).campos)
    assert admin.get("/estabelecimentos").json()["pagination"]["total"] == 4


@pytest.mark.parametrize("cnpj", [CNPJ_SERRA_AZUL, "54839271000164"])
def test_ft_cad_04_cnpj_duplicado(api, cnpj):
    """EX 5b — CNPJ já cadastrado (com ou sem máscara): 409 e nenhum registro novo."""
    admin = api.como("ADMINISTRADOR")
    resposta = admin.post("/estabelecimentos", json=novo_estabelecimento(cnpj=cnpj))
    assert resposta.status_code == 409
    assert admin.get("/estabelecimentos").json()["pagination"]["total"] == 4


@defeito("DF-02", "A resposta 409 de CNPJ duplicado não identifica o registro existente para abri-lo (UC01 5b).")
def test_ft_cad_05_duplicidade_oferece_registro_existente(api):
    """EX 5b — o sistema deve oferecer abrir o registro existente (resposta referencia o id)."""
    resposta = api.como("ADMINISTRADOR").post("/estabelecimentos", json=novo_estabelecimento(cnpj=CNPJ_SERRA_AZUL))
    assert SERRA_AZUL in resposta.text


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-82", "11111111111111", "123"])
def test_ft_cad_06_cnpj_invalido(api, cnpj):
    """EX 5a — CNPJ com dígito verificador errado, repetido ou curto: 422."""
    resposta = api.como("ADMINISTRADOR").post("/estabelecimentos", json=novo_estabelecimento(cnpj=cnpj))
    assert resposta.status_code == 422


@pytest.mark.uc("UC02")
@pytest.mark.parametrize("campo,valor", [("total_uh", "abc"), ("total_leitos", -1), ("total_uh", 2.5)])
def test_ft_cad_07_formato_invalido_campo_especifico(api, campo, valor):
    """EX UC02 4a — texto, negativo ou fração em campo inteiro de hospedagem: 422."""
    payload = novo_estabelecimento(meio_hospedagem={"tipo_hospedagem": "HOTEL", campo: valor})
    assert api.como("ADMINISTRADOR").post("/estabelecimentos", json=payload).status_code == 422


def test_ft_cad_08_categoria_inexistente(api):
    """EX — categoria que não existe: 422."""
    assert api.como("ADMINISTRADOR").post("/estabelecimentos", json=novo_estabelecimento(id_categoria=99)).status_code == 422


@pytest.mark.parametrize("perfil", ["EDITOR", "GESTOR", "HOTEL"])
def test_ft_cad_09_somente_admin_cadastra(api, perfil):
    """EX — perfis sem permissão de cadastro recebem 403; nada é gravado."""
    assert api.como(perfil).post("/estabelecimentos", json=novo_estabelecimento()).status_code == 403
    assert api.como("ADMINISTRADOR").get("/estabelecimentos").json()["pagination"]["total"] == 4


def test_ft_cad_10_editor_edita_ficha(api):
    """CF — EDITOR atualiza telefone e leitos; alteração persistida."""
    editor = api.como("EDITOR")
    resposta = editor.patch(f"/estabelecimentos/{SERRA_AZUL}",
                            json={"telefone_comercial": "+55 17 99999-1234", "meio_hospedagem": {"total_leitos": 130}})
    assert resposta.status_code == 200, resposta.text
    ficha = editor.get(f"/estabelecimentos/{SERRA_AZUL}").json()
    assert ficha["telefone_comercial"] == "+55 17 99999-1234"
    assert ficha["meio_hospedagem"]["total_leitos"] == 130


@pytest.mark.parametrize("campo,valor", [("cnpj", CNPJ_LIVRE), ("razao_social", "Outra Razão Ltda.")])
def test_ft_cad_11_editor_nao_altera_campos_protegidos(api, campo, valor):
    """EX — CNPJ e razão social são exclusivos do ADMIN: 403 e ficha inalterada."""
    editor = api.como("EDITOR")
    antes = editor.get(f"/estabelecimentos/{SERRA_AZUL}").json()[campo]
    assert editor.patch(f"/estabelecimentos/{SERRA_AZUL}", json={campo: valor}).status_code == 403
    assert editor.get(f"/estabelecimentos/{SERRA_AZUL}").json()[campo] == antes


def test_ft_cad_12_admin_altera_campo_protegido(api):
    """CF — ADMIN altera razão social."""
    admin = api.como("ADMINISTRADOR")
    resposta = admin.patch(f"/estabelecimentos/{SERRA_AZUL}", json={"razao_social": "Serra Azul Turismo Ltda."})
    assert resposta.status_code == 200
    assert admin.get(f"/estabelecimentos/{SERRA_AZUL}").json()["razao_social"] == "Serra Azul Turismo Ltda."


def test_ft_cad_13_gestor_nao_edita(api):
    """EX — GESTOR é somente leitura."""
    assert api.como("GESTOR").patch(f"/estabelecimentos/{SERRA_AZUL}", json={"telefone_comercial": "1"}).status_code == 403
