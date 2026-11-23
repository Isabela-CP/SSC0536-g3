"""UC15 — Relatório consolidado de ocupação (RF-10) e tela inicial com totalizadores (RF Home)."""
import csv
from io import StringIO

import pytest

from apoio_api import (PESQUISA_CONSOLIDADO_ABERTA, PESQUISA_EXPECTATIVA_ABERTA, SERRA_AZUL,
                      nova_pesquisa, novo_estabelecimento)


def _gerar(cliente, formato, id_pesquisa=None):
    corpo = {"tipo": "OCUPACAO", "formato": formato, **({"id_pesquisa": id_pesquisa} if id_pesquisa else {})}
    return cliente.post("/relatorios", json=corpo)


def _linhas_csv(cliente, relatorio) -> list[list[str]]:
    arquivo = cliente.get(f"/relatorios/{relatorio['id_relatorio']}/arquivo")
    assert arquivo.status_code == 200 and arquivo.headers["content-type"].startswith("text/csv")
    return list(csv.reader(StringIO(arquivo.content.decode("utf-8-sig"))))


# ------------------------------------------------------------------ UC15
@pytest.mark.uc("UC15")
def test_ft_rel_01_csv_consolidado_da_pesquisa(api):
    """CF — GESTOR gera CSV de uma pesquisa com hospedagem, período e taxa de cada resposta."""
    gestor = api.como("GESTOR")
    resposta = _gerar(gestor, "CSV", PESQUISA_CONSOLIDADO_ABERTA)
    assert resposta.status_code == 202 and resposta.json()["status"] == "CONCLUIDO"
    linhas = _linhas_csv(gestor, resposta.json())
    assert linhas[0][1] == "Hospedagem" and "Ocupação (%)" in linhas[0]
    assert ["Hotel Serra Azul", "72.92"] == [linhas[1][1], linhas[1][4]]
    assert linhas[1][2:4] == ["2026-11-01", "2026-11-15"]


@pytest.mark.uc("UC15")
def test_ft_rel_02_pdf_para_download(api):
    """CF 5 — o relatório PDF é um arquivo único disponível para download."""
    admin = api.como("ADMINISTRADOR")
    relatorio = _gerar(admin, "PDF").json()
    arquivo = admin.get(f"/relatorios/{relatorio['id_relatorio']}/arquivo")
    assert arquivo.status_code == 200 and arquivo.content.startswith(b"%PDF")
    assert "attachment" in arquivo.headers["content-disposition"]
    assert admin.get(f"/relatorios/{relatorio['id_relatorio']}").json()["arquivo"]["tamanho_bytes"] == len(arquivo.content)


@pytest.mark.uc("UC15")
def test_ft_rel_03_participante_sem_resposta_aparece(api):
    """EX *a — Pousada Ipê Amarelo participa da pesquisa 3 e não respondeu."""
    gestor = api.como("GESTOR")
    linhas = _linhas_csv(gestor, _gerar(gestor, "CSV", PESQUISA_CONSOLIDADO_ABERTA).json())
    ipe = [linha for linha in linhas if linha[1] == "Pousada Ipê Amarelo"]
    assert ipe and "sem resposta" in " ".join(ipe[0]).casefold()


@pytest.mark.uc("UC15")
def test_ft_rel_04_periodo_sem_respostas_avisa(api):
    """EX 3a — nenhuma resposta: o sistema avisa (não gera arquivo vazio)."""
    resposta = _gerar(api.como("GESTOR"), "CSV", PESQUISA_EXPECTATIVA_ABERTA)
    assert resposta.status_code in (404, 409, 422)


@pytest.mark.uc("UC15")
@pytest.mark.parametrize("corpo,esperado", [({"tipo": "OCUPACAO", "formato": "XLSX"}, 422),
                                            ({"tipo": "INVALIDO", "formato": "PDF"}, 422),
                                            ({"tipo": "OCUPACAO", "formato": "CSV", "id_pesquisa": "987654"}, 404)])
def test_ft_rel_05_parametros_invalidos(api, corpo, esperado):
    """EX — formato/tipo não suportado: 422; pesquisa inexistente: 404."""
    assert api.como("GESTOR").post("/relatorios", json=corpo).status_code == esperado


@pytest.mark.uc("UC15")
@pytest.mark.parametrize("perfil", ["EDITOR", "HOTEL"])
def test_ft_rel_06_perfis_sem_permissao(api, perfil):
    """EX — relatórios restritos a ADMINISTRADOR e GESTOR."""
    cliente = api.como(perfil)
    assert _gerar(cliente, "CSV").status_code == 403
    relatorio = _gerar(api.como("GESTOR"), "CSV").json()
    assert cliente.get(f"/relatorios/{relatorio['id_relatorio']}/arquivo").status_code == 403


@pytest.mark.uc("UC15")
def test_ft_rel_07_csv_neutraliza_formulas(api):
    """EX segurança — título iniciado por '=' não vira fórmula no CSV aberto em planilha."""
    pesquisa = api.como("EDITOR").post("/pesquisas-ocupacao", json=nova_pesquisa(
        titulo="=HYPERLINK(\"http://x\")", estabelecimentos=[SERRA_AZUL])).json()
    api.como("HOTEL").post(f"/pesquisas-ocupacao/{pesquisa['id_pesquisa']}/respostas", json={"taxa_ocupacao": 40})
    gestor = api.como("GESTOR")
    linhas = _linhas_csv(gestor, _gerar(gestor, "CSV", pesquisa["id_pesquisa"]).json())
    assert linhas[1][0].startswith("'=")


@pytest.mark.uc("UC15")
def test_ft_rel_08_filtro_por_periodo_e_categoria(contrato):
    """CF 2 — selecionar período e, opcionalmente, categoria."""
    campos = contrato["components"]["schemas"]["RelatorioCreate"]["properties"]
    assert {"periodo_inicio", "periodo_fim"} <= campos.keys() or "periodo" in campos


# ------------------------------------------------------------------ Tela inicial (Home)
@pytest.mark.uc("HOME")
def test_ft_dsh_01_totalizadores_conferem_com_o_inventario(api):
    """CF — totais do painel coincidem com o inventário e as pesquisas."""
    gestor = api.como("GESTOR")
    indicadores = gestor.get("/dashboard").json()["indicadores"]
    fichas = [gestor.get(f"/estabelecimentos/{i['id_estabelecimento']}").json()
              for i in gestor.get("/estabelecimentos").json()["data"]]
    leitos = [(f.get("meio_hospedagem") or {}).get("total_leitos") for f in fichas]
    assert indicadores["total_empresas"] == 4 and indicadores["estabelecimentos_ativos"] == 3
    assert indicadores["total_leitos"] == sum(v for v in leitos if v is not None)
    assert indicadores["leitos_nao_informados"] == sum(v is None for v in leitos)
    assert indicadores["pesquisas_abertas"] == 2
    assert indicadores["respostas_recebidas"] == len(api.sql("SELECT id FROM respostas_ocupacao WHERE status='ENVIADA'"))


@pytest.mark.uc("HOME")
def test_ft_dsh_02_totalizadores_refletem_alteracoes(api):
    """CF — novo hotel com 60 leitos e uma inativação atualizam os totais."""
    admin = api.como("ADMINISTRADOR")
    antes = admin.get("/dashboard").json()["indicadores"]
    admin.post("/estabelecimentos", json=novo_estabelecimento(meio_hospedagem={"tipo_hospedagem": "HOTEL", "total_leitos": 60}))
    admin.post(f"/estabelecimentos/{SERRA_AZUL}/inativacao", json={"motivo_inativacao": "Fechou"})
    depois = admin.get("/dashboard").json()["indicadores"]
    assert depois["total_empresas"] == antes["total_empresas"] + 1
    assert depois["total_leitos"] == antes["total_leitos"] + 60
    assert depois["estabelecimentos_ativos"] == antes["estabelecimentos_ativos"]


@pytest.mark.uc("HOME")
def test_ft_dsh_03_empresas_cadastradas_no_mes(api):
    """CF — totalizador de empresas cadastradas no mês corrente."""
    api.como("ADMINISTRADOR").post("/estabelecimentos", json=novo_estabelecimento())
    indicadores = api.como("GESTOR").get("/dashboard").json()["indicadores"]
    chaves = [k for k in indicadores if "mes" in k.casefold() or "mês" in k.casefold()]
    assert chaves, f"indicadores disponíveis: {sorted(indicadores)}"
    assert indicadores[chaves[0]] >= 1


@pytest.mark.uc("HOME")
def test_ft_dsh_04_empresario_nao_ve_painel_interno(api):
    """EX — o painel da prefeitura não é exibido ao empresário."""
    assert api.como("HOTEL").get("/dashboard").status_code == 403
