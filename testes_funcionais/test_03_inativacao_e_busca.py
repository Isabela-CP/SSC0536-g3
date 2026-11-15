"""UC04 — Inativar empresa (RF-04, RNF-05) e UC05 — Buscar e filtrar empresas (RF-05)."""
import pytest

from apoio_api import EM_CADASTRO, IPE_AMARELO, SERRA_AZUL, VALE_DO_SOL, defeito, nao_implementado

INEXISTENTE = "99999999-9999-4999-8999-999999999999"


# ------------------------------------------------------------------ UC04
@pytest.mark.uc("UC04")
def test_ft_ina_01_inativar_com_motivo(api):
    """CF — inativação muda o status, guarda o motivo e preserva o registro."""
    admin = api.como("ADMINISTRADOR")
    resposta = admin.post(f"/estabelecimentos/{SERRA_AZUL}/inativacao",
                          json={"motivo_inativacao": "Encerramento das atividades"})
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "INATIVO"
    ficha = admin.get(f"/estabelecimentos/{SERRA_AZUL}").json()
    assert ficha["status"] == "INATIVO" and ficha["motivo_inativacao"] == "Encerramento das atividades"
    assert ficha["nome_fantasia"] == "Hotel Serra Azul"
    inativos = admin.get("/estabelecimentos", params={"status": "INATIVO"}).json()["data"]
    assert SERRA_AZUL in {item["id_estabelecimento"] for item in inativos}


@pytest.mark.uc("UC04")
@pytest.mark.parametrize("motivo,esperado", [
    (None, 422), ("ab", 422), ("abc", 200), ("x" * 500, 200), ("x" * 501, 422)])
def test_ft_ina_02_limites_do_motivo(api, motivo, esperado):
    """EX — valor limite do motivo (3 a 500 caracteres)."""
    corpo = {} if motivo is None else {"motivo_inativacao": motivo}
    resposta = api.como("ADMINISTRADOR").post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json=corpo)
    assert resposta.status_code == esperado


@pytest.mark.uc("UC04")
@defeito("DF-03", "Motivo de inativação composto só por espaços é aceito e gravado; a empresa fica inativa sem motivo (UC04 passo 2).")
def test_ft_ina_02b_motivo_em_branco(api):
    """EX — motivo só com espaços deve ser recusado como motivo ausente (422)."""
    resposta = api.como("ADMINISTRADOR").post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json={"motivo_inativacao": "   "})
    assert resposta.status_code == 422


@pytest.mark.uc("UC04")
def test_ft_ina_03_empresa_ja_inativa_e_reativacao(api):
    """EX 5a — inativar empresa já inativa: 409; reativar restaura ATIVO e limpa o motivo."""
    admin = api.como("ADMINISTRADOR")
    repetida = admin.post(f"/estabelecimentos/{VALE_DO_SOL}/inativacao", json={"motivo_inativacao": "De novo"})
    assert repetida.status_code == 409
    reativada = admin.post(f"/estabelecimentos/{VALE_DO_SOL}/reativacao")
    assert reativada.status_code == 200
    ficha = admin.get(f"/estabelecimentos/{VALE_DO_SOL}").json()
    assert ficha["status"] == "ATIVO" and ficha["motivo_inativacao"] is None
    assert admin.post(f"/estabelecimentos/{VALE_DO_SOL}/reativacao").status_code == 409


@pytest.mark.uc("UC04")
@pytest.mark.parametrize("perfil", ["EDITOR", "GESTOR", "HOTEL"])
def test_ft_ina_04_somente_admin_altera_status(api, perfil):
    """EX — demais perfis não inativam nem reativam."""
    cliente = api.como(perfil)
    assert cliente.post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json={"motivo_inativacao": "Teste"}).status_code == 403
    assert cliente.post(f"/estabelecimentos/{VALE_DO_SOL}/reativacao").status_code == 403


@pytest.mark.uc("UC04")
@pytest.mark.parametrize("perfil", ["ADMINISTRADOR", "EDITOR", "GESTOR", "HOTEL"])
def test_ft_ina_05_sem_exclusao_definitiva(api, perfil):
    """EX *a — não existe exclusão física de empresas para nenhum perfil."""
    assert api.como(perfil).delete(f"/estabelecimentos/{SERRA_AZUL}").status_code == 405
    assert api.como("ADMINISTRADOR").get(f"/estabelecimentos/{SERRA_AZUL}").status_code == 200


@pytest.mark.uc("UC04")
def test_ft_ina_06_estabelecimento_inexistente(api):
    """EX — inativar/consultar id inexistente: 404."""
    admin = api.como("ADMINISTRADOR")
    assert admin.post(f"/estabelecimentos/{INEXISTENTE}/inativacao", json={"motivo_inativacao": "Teste"}).status_code == 404
    assert admin.get(f"/estabelecimentos/{INEXISTENTE}").status_code == 404


# ------------------------------------------------------------------ UC05
@pytest.mark.uc("UC05")
@pytest.mark.parametrize("termo", ["Serra Azul", "serra azul", "SERRA", "54.839.271", "54839271000164"])
def test_ft_bus_01_busca_por_nome_ou_cnpj(api, termo):
    """CF — busca parcial, sem diferenciar maiúsculas, por nome ou CNPJ (com/sem máscara)."""
    corpo = api.como("EDITOR").get("/estabelecimentos", params={"busca": termo}).json()
    assert [item["id_estabelecimento"] for item in corpo["data"]] == [SERRA_AZUL]


@pytest.mark.uc("UC05")
def test_ft_bus_02_filtros_combinados(api):
    """CF — categoria + status + aceita pesquisas são aplicados em conjunto (interseção)."""
    gestor = api.como("GESTOR")
    ativos = gestor.get("/estabelecimentos", params={"id_categoria": 1, "status": "ATIVO"}).json()
    assert {i["id_estabelecimento"] for i in ativos["data"]} == {SERRA_AZUL, IPE_AMARELO, EM_CADASTRO}
    cruzado = gestor.get("/estabelecimentos", params={"status": "INATIVO", "aceita_pesquisas": "false"}).json()
    assert [i["id_estabelecimento"] for i in cruzado["data"]] == [VALE_DO_SOL]
    vazio = gestor.get("/estabelecimentos", params={"status": "INATIVO", "aceita_pesquisas": "true"}).json()
    assert vazio["data"] == []


@pytest.mark.uc("UC05")
def test_ft_bus_03_limpar_filtros(api):
    """CF 2a — sem filtros, todas as empresas voltam a ser listadas."""
    gestor = api.como("GESTOR")
    assert gestor.get("/estabelecimentos", params={"status": "INATIVO"}).json()["pagination"]["total"] == 1
    assert gestor.get("/estabelecimentos").json()["pagination"]["total"] == 4


@pytest.mark.uc("UC05")
def test_ft_bus_04_sem_resultados(api):
    """EX 3a — nenhum resultado: lista vazia com total zero (mensagem cabe à interface)."""
    corpo = api.como("GESTOR").get("/estabelecimentos", params={"busca": "inexistente-xyz"}).json()
    assert corpo["data"] == [] and corpo["pagination"]["total"] == 0


@pytest.mark.uc("UC05")
def test_ft_bus_05_paginacao_e_ordenacao(api):
    """CF — páginas não se sobrepõem e a ordenação por nome é respeitada."""
    gestor = api.como("GESTOR")
    p1 = gestor.get("/estabelecimentos", params={"page_size": 2, "page": 1}).json()
    p2 = gestor.get("/estabelecimentos", params={"page_size": 2, "page": 2}).json()
    nomes = [i["nome_fantasia"] for i in p1["data"] + p2["data"]]
    assert len(set(nomes)) == 4 and nomes == sorted(nomes, key=str.casefold)
    assert p1["pagination"]["total_pages"] == 2
    desc = gestor.get("/estabelecimentos", params={"ordem": "desc"}).json()["data"]
    assert [i["nome_fantasia"] for i in desc] == sorted(nomes, key=str.casefold, reverse=True)


@pytest.mark.uc("UC05")
@pytest.mark.parametrize("params", [{"page_size": 0}, {"page_size": 101}, {"status": "FECHADO"},
                                    {"busca": "x" * 121}, {"id_categoria": 0}, {"page": 0}])
def test_ft_bus_06_parametros_invalidos(api, params):
    """EX — parâmetros fora do domínio: 400 com corpo de erro."""
    resposta = api.como("GESTOR").get("/estabelecimentos", params=params)
    assert resposta.status_code == 400 and "error" in resposta.json()


@pytest.mark.uc("UC05")
@nao_implementado("NI-01", "Não há filtro por capacidade (ex.: 'Hotéis + Ativos + com mais de 50 leitos', RF de busca cruzada).")
def test_ft_bus_07_filtro_por_numero_de_leitos(contrato):
    """CF RF — busca cruzada por capacidade de leitos deve existir na listagem."""
    parametros = {p["name"] for p in contrato["paths"]["/estabelecimentos"]["get"].get("parameters", []) if "name" in p}
    assert any("leito" in nome for nome in parametros)
