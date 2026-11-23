"""UC11 — Autenticar empresário (RF-08) e UC12 — Atualizar dados do próprio estabelecimento (RF-08).

Na build avaliada o empresário é a conta de perfil HOTEL, vinculada a um único estabelecimento.
"""
import pytest

from apoio_api import CNPJ_LIVRE, CNPJ_SERRA_AZUL, CONTAS, IPE_AMARELO, SERRA_AZUL

pytestmark = pytest.mark.uc("UC11")


def test_ft_emp_01_ve_somente_o_proprio_estabelecimento(api):
    """CF UC11 — listagem e ficha restritas ao estabelecimento vinculado."""
    hotel = api.como("HOTEL")
    lista = hotel.get("/estabelecimentos").json()
    assert lista["pagination"]["total"] == 1 and lista["data"][0]["id_estabelecimento"] == SERRA_AZUL
    assert hotel.get("/estabelecimentos", params={"busca": "Ipê"}).json()["data"] == []
    assert hotel.get(f"/estabelecimentos/{SERRA_AZUL}").status_code == 200


@pytest.mark.uc("UC12")
@pytest.mark.parametrize("operacao", ["ficha", "documentos", "edicao", "upload"])
def test_ft_emp_02_nao_acessa_outra_empresa(api, operacao):
    """EX UC12 *a — o empresário nunca vê nem edita dados de outra empresa."""
    hotel = api.como("HOTEL")
    base = f"/estabelecimentos/{IPE_AMARELO}"
    resposta = {
        "ficha": lambda: hotel.get(base),
        "documentos": lambda: hotel.get(base + "/documentos"),
        "edicao": lambda: hotel.patch(base, json={"telefone_comercial": "+55 0"}),
        "upload": lambda: hotel.post(base + "/documentos", data={"tipo_documento": "ALVARA", "data_vencimento": "2030-01-01"},
                                     files={"arquivo": ("a.pdf", b"%PDF-1.4 x", "application/pdf")}),
    }[operacao]()
    assert resposta.status_code == 403
    assert api.como("ADMINISTRADOR").get(base).json()["telefone_comercial"] != "+55 0"


@pytest.mark.uc("UC12")
def test_ft_emp_03_atualiza_propria_ficha_com_auditoria(api):
    """CF UC12 — empresário edita a própria ficha; alteração gravada e auditada com seu usuário."""
    hotel = api.como("HOTEL")
    resposta = hotel.patch(f"/estabelecimentos/{SERRA_AZUL}", json={"email_comercial": "reservas@serra-azul.example"})
    assert resposta.status_code == 200
    assert hotel.get(f"/estabelecimentos/{SERRA_AZUL}").json()["email_comercial"] == "reservas@serra-azul.example"
    registros = [r for r in api.auditoria("ESTABELECIMENTO_ATUALIZADO") if r["id_entidade"] == SERRA_AZUL]
    assert registros[0]["usuario"] == CONTAS["HOTEL"]


@pytest.mark.uc("UC12")
@pytest.mark.parametrize("corpo", [{"cnpj": CNPJ_LIVRE}, {"razao_social": "Outra Ltda."}, {"meio_hospedagem": {"total_uh": "dez"}}])
def test_ft_emp_04_edicao_invalida_ou_protegida(api, corpo):
    """EX UC12 4a — campo protegido (403) ou dado inválido (422); nada é alterado."""
    hotel = api.como("HOTEL")
    antes = hotel.get(f"/estabelecimentos/{SERRA_AZUL}").json()
    resposta = hotel.patch(f"/estabelecimentos/{SERRA_AZUL}", json=corpo)
    assert resposta.status_code in (403, 422)
    assert hotel.get(f"/estabelecimentos/{SERRA_AZUL}").json() == antes


@pytest.mark.parametrize("rota", ["/dashboard", "/usuarios", "/auditoria"])
def test_ft_emp_05_sem_acesso_a_areas_internas(api, rota):
    """EX — o empresário não acessa áreas da equipe da prefeitura."""
    assert api.como("HOTEL").get(rota).status_code == 403


def test_ft_emp_06_login_com_cnpj_e_senha(api):
    """CF UC11 — autenticação do empresário por CNPJ e senha."""
    resposta = api.anon.post("/auth/login", json={"cnpj": CNPJ_SERRA_AZUL, "senha": "hotel-demo"})
    assert resposta.status_code == 200
    assert resposta.json()["usuario"]["id_estabelecimento"] == SERRA_AZUL


def test_ft_emp_07_empresa_inativa_nao_autentica(api):
    """EX UC11 3b — empresa inativa: o sistema nega o acesso."""
    resposta = api.anon.post("/auth/login", json={"email": CONTAS["HOTEL_INATIVO"], "senha": "hotel-demo"})
    assert resposta.status_code in (401, 403)


def test_ft_emp_08_inativacao_encerra_acesso_do_empresario(api):
    """EX UC11 3b — inativar a empresa deve encerrar o acesso de quem já estava logado."""
    hotel = api.como("HOTEL")
    api.como("ADMINISTRADOR").post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json={"motivo_inativacao": "Fechou"})
    assert hotel.patch(f"/estabelecimentos/{SERRA_AZUL}", json={"telefone_comercial": "+55 9"}).status_code in (401, 403)
