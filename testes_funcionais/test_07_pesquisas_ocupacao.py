"""UC13 — Criar pesquisa de taxa de ocupação e UC14 — Responder pesquisa (RF-09)."""
import pytest

from apoio_api import (EM_CADASTRO, IPE_AMARELO, PESQUISA_CONSOLIDADO_ABERTA, PESQUISA_ENCERRADA,
                      PESQUISA_EXPECTATIVA_ABERTA, SERRA_AZUL, VALE_DO_SOL, nova_pesquisa)

INEXISTENTE = "99999999-9999-4999-8999-999999999999"


def _pendentes(cliente):
    return {p["id_pesquisa"] for p in cliente.get("/pesquisas-ocupacao/pendentes").json()["data"]}


# ------------------------------------------------------------------ UC13
@pytest.mark.uc("UC13")
def test_ft_pes_01_criar_publica_para_destinatarios(api):
    """CF — EDITOR cria pesquisa; ela aparece só no painel dos estabelecimentos participantes."""
    resposta = api.como("EDITOR").post("/pesquisas-ocupacao", json=nova_pesquisa(estabelecimentos=[SERRA_AZUL]))
    assert resposta.status_code == 201, resposta.text
    pesquisa = resposta.json()
    assert pesquisa["status"] == "ABERTA" and pesquisa["estabelecimentos"] == [SERRA_AZUL]
    assert pesquisa["id_pesquisa"] in _pendentes(api.como("HOTEL"))
    assert pesquisa["id_pesquisa"] not in _pendentes(api.como("HOTEL_IPE"))


@pytest.mark.uc("UC13")
@pytest.mark.parametrize("destinatarios", [[VALE_DO_SOL], [INEXISTENTE], []])
def test_ft_pes_02_destinatarios_invalidos(api, destinatarios):
    """EX — empresa inativa/que não aceita pesquisas, inexistente ou lista vazia: 422."""
    resposta = api.como("EDITOR").post("/pesquisas-ocupacao", json=nova_pesquisa(estabelecimentos=destinatarios))
    assert resposta.status_code == 422


@pytest.mark.uc("UC13")
@pytest.mark.parametrize("campo,valor", [("tipo", "MENSAL"), ("periodo_fim", "2026-11-30"),
                                         ("periodo_inicio", "2026-02-30"), ("titulo", "  ")])
def test_ft_pes_03_dados_invalidos(api, campo, valor):
    """EX — tipo fora de Expectativa/Consolidado, período invertido, data inexistente, título vazio: 422."""
    assert api.como("EDITOR").post("/pesquisas-ocupacao", json=nova_pesquisa(**{campo: valor})).status_code == 422


@pytest.mark.uc("UC13")
@pytest.mark.parametrize("perfil", ["GESTOR", "HOTEL"])
def test_ft_pes_04_perfis_sem_permissao(api, perfil):
    """EX — GESTOR e HOTEL não criam pesquisas."""
    assert api.como(perfil).post("/pesquisas-ocupacao", json=nova_pesquisa()).status_code == 403


@pytest.mark.uc("UC13")
def test_ft_pes_05_pesquisa_duplicada(api):
    """EX 2a — mesma combinação tipo + período deve ser recusada."""
    editor = api.como("EDITOR")
    assert editor.post("/pesquisas-ocupacao", json=nova_pesquisa()).status_code == 201
    assert editor.post("/pesquisas-ocupacao", json=nova_pesquisa(titulo="Outra")).status_code == 409


@pytest.mark.uc("UC13")
def test_ft_pes_06_editar_e_encerrar(api):
    """CF — pesquisa aberta pode ser editada e encerrada; depois de encerrada, não."""
    editor = api.como("EDITOR")
    pesquisa = editor.post("/pesquisas-ocupacao", json=nova_pesquisa()).json()
    url = f"/pesquisas-ocupacao/{pesquisa['id_pesquisa']}"
    assert editor.patch(url, json={"titulo": "Dezembro"}).json()["titulo"] == "Dezembro"
    assert editor.post(url + "/encerramento").json()["status"] == "ENCERRADA"
    assert editor.post(url + "/encerramento").status_code == 409
    assert editor.patch(url, json={"titulo": "Outra"}).status_code == 409
    assert pesquisa["id_pesquisa"] not in _pendentes(api.como("HOTEL"))


@pytest.mark.uc("UC13")
def test_ft_pes_07_nao_remove_quem_ja_respondeu(api):
    """EX — participante que já respondeu não pode ser retirado da pesquisa."""
    resposta = api.como("EDITOR").patch(f"/pesquisas-ocupacao/{PESQUISA_CONSOLIDADO_ABERTA}",
                                        json={"estabelecimentos": [IPE_AMARELO, EM_CADASTRO]})
    assert resposta.status_code == 409


# ------------------------------------------------------------------ UC14
@pytest.mark.uc("UC14")
def test_ft_res_01_responder_pesquisa(api):
    """CF — empresário informa a taxa; resposta vinculada à empresa e ao período, sai das pendências."""
    hotel = api.como("HOTEL_IPE")
    assert PESQUISA_CONSOLIDADO_ABERTA in _pendentes(hotel)
    resposta = hotel.post(f"/pesquisas-ocupacao/{PESQUISA_CONSOLIDADO_ABERTA}/respostas", json={"taxa_ocupacao": 75})
    assert resposta.status_code == 201
    assert resposta.json()["id_estabelecimento"] == IPE_AMARELO
    assert PESQUISA_CONSOLIDADO_ABERTA not in _pendentes(hotel)
    historico = hotel.get("/respostas-ocupacao/historico").json()["data"]
    assert {(h["id_pesquisa"], h["dados"]["taxa_ocupacao"]) for h in historico} >= {(PESQUISA_CONSOLIDADO_ABERTA, 75.0)}
    assert all(h["id_estabelecimento"] == IPE_AMARELO for h in historico)


@pytest.mark.uc("UC14")
@pytest.mark.parametrize("taxa,esperado", [(-1, 422), (0, 201), (55.5, 201), (100, 201), (100.01, 422),
                                           (101, 422), ("75", 422), (True, 422), (None, 422)])
def test_ft_res_02_limites_da_taxa(api, taxa, esperado):
    """EX 4a — percentual entre 0 e 100; texto, booleano e nulo são recusados."""
    resposta = api.como("HOTEL").post(f"/pesquisas-ocupacao/{PESQUISA_EXPECTATIVA_ABERTA}/respostas",
                                      json={"taxa_ocupacao": taxa})
    assert resposta.status_code == esperado


@pytest.mark.uc("UC14")
def test_ft_res_03_corrigir_resposta_com_pesquisa_aberta(api):
    """EX 3a — empresário já respondeu: o sistema permite corrigir enquanto a pesquisa estiver aberta."""
    hotel = api.como("HOTEL")   # Serra Azul já respondeu a pesquisa 3 (72,92%)
    resposta = hotel.post(f"/pesquisas-ocupacao/{PESQUISA_CONSOLIDADO_ABERTA}/respostas", json={"taxa_ocupacao": 80})
    assert resposta.status_code in (200, 201)
    historico = hotel.get("/respostas-ocupacao/historico").json()["data"]
    assert {h["dados"]["taxa_ocupacao"] for h in historico if h["id_pesquisa"] == PESQUISA_CONSOLIDADO_ABERTA} == {80.0}


@pytest.mark.uc("UC14")
def test_ft_res_04_pesquisa_encerrada_nao_aceita_resposta(api):
    """EX — pesquisa encerrada: 409."""
    editor = api.como("EDITOR")
    pesquisa = editor.post("/pesquisas-ocupacao", json=nova_pesquisa()).json()
    editor.post(f"/pesquisas-ocupacao/{pesquisa['id_pesquisa']}/encerramento")
    resposta = api.como("HOTEL").post(f"/pesquisas-ocupacao/{pesquisa['id_pesquisa']}/respostas", json={"taxa_ocupacao": 50})
    assert resposta.status_code == 409


@pytest.mark.uc("UC14")
def test_ft_res_05_pesquisa_de_outro_ou_inexistente(api):
    """EX — pesquisa não destinada à empresa: 403; inexistente: 404."""
    pesquisa = api.como("EDITOR").post("/pesquisas-ocupacao", json=nova_pesquisa(estabelecimentos=[IPE_AMARELO])).json()
    hotel = api.como("HOTEL")
    assert hotel.post(f"/pesquisas-ocupacao/{pesquisa['id_pesquisa']}/respostas", json={"taxa_ocupacao": 50}).status_code == 403
    assert hotel.post("/pesquisas-ocupacao/987654/respostas", json={"taxa_ocupacao": 50}).status_code == 404


@pytest.mark.uc("UC14")
@pytest.mark.parametrize("perfil", ["ADMINISTRADOR", "EDITOR", "GESTOR"])
def test_ft_res_06_equipe_interna_nao_responde(api, perfil):
    """EX — somente o empresário responde pesquisas."""
    resposta = api.como(perfil).post(f"/pesquisas-ocupacao/{PESQUISA_EXPECTATIVA_ABERTA}/respostas", json={"taxa_ocupacao": 50})
    assert resposta.status_code == 403


@pytest.mark.uc("UC14")
def test_ft_res_07_sem_pendencias(api):
    """EX 1a — depois de responder tudo, não há pendências."""
    hotel = api.como("HOTEL")
    assert _pendentes(hotel) == {PESQUISA_EXPECTATIVA_ABERTA}
    hotel.post(f"/pesquisas-ocupacao/{PESQUISA_EXPECTATIVA_ABERTA}/respostas", json={"taxa_ocupacao": 60})
    assert _pendentes(hotel) == set()


@pytest.mark.uc("UC14")
def test_ft_res_08_respostas_isoladas_por_empresa(api):
    """EX — o histórico do empresário não contém respostas de outras empresas."""
    historico = api.como("HOTEL").get("/respostas-ocupacao/historico").json()["data"]
    assert historico and {h["id_estabelecimento"] for h in historico} == {SERRA_AZUL}
    assert PESQUISA_ENCERRADA in {h["id_pesquisa"] for h in historico}
