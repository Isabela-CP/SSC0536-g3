"""Documentos de controle da ficha (UC02/UC12) e requisitos sem funcionalidade na build (UC06, UC09, UC10, RF de exportação)."""
from datetime import datetime, timedelta, timezone

import pytest

from apoio_api import IPE_AMARELO, SERRA_AZUL, nao_implementado

PDF = b"%PDF-1.4\n% documento funcional\n"


def _enviar(cliente, estabelecimento=SERRA_AZUL, vencimento="2030-01-01", arquivo=("alvara.pdf", PDF, "application/pdf")):
    return cliente.post(f"/estabelecimentos/{estabelecimento}/documentos",
                        data={"tipo_documento": "ALVARA", "data_vencimento": vencimento}, files={"arquivo": arquivo})


# ------------------------------------------------------------------ Documentos
@pytest.mark.uc("UC02", "UC12")
def test_ft_doc_01_envio_e_download(api):
    """CF — EDITOR anexa PDF; GESTOR baixa exatamente o mesmo conteúdo."""
    resposta = _enviar(api.como("EDITOR"))
    assert resposta.status_code == 201, resposta.text
    documento = resposta.json()
    download = api.como("GESTOR").get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert download.status_code == 200 and download.content == PDF
    listados = api.como("GESTOR").get(f"/estabelecimentos/{SERRA_AZUL}/documentos").json()["data"]
    assert documento["id_documento"] in {d["id_documento"] for d in listados}


@pytest.mark.uc("UC02")
@pytest.mark.parametrize("dias,status", [(-1, "VENCIDO"), (0, "A_VENCER"), (30, "A_VENCER"), (31, "REGULAR")])
def test_ft_doc_02_status_pelo_vencimento(api, dias, status):
    """EX — valor limite da situação do documento (janela de 30 dias, data UTC)."""
    vencimento = (datetime.now(timezone.utc).date() + timedelta(days=dias)).isoformat()
    assert _enviar(api.como("EDITOR"), vencimento=vencimento).json()["status"] == status


@pytest.mark.uc("UC02")
@pytest.mark.parametrize("arquivo,esperado", [(("nota.txt", b"texto", "text/plain"), 415),
                                              (("falso.pdf", b"x", "image/png"), 415),
                                              (("vazio.pdf", b"", "application/pdf"), 422)])
def test_ft_doc_03_arquivo_invalido(api, arquivo, esperado):
    """EX — tipo não permitido ou MIME incompatível com a extensão: 415; vazio: 422."""
    assert _enviar(api.como("EDITOR"), arquivo=arquivo).status_code == esperado


@pytest.mark.uc("UC02", "UC12")
def test_ft_doc_04_permissoes(api):
    """EX — GESTOR não envia; HOTEL envia só para a própria empresa."""
    assert _enviar(api.como("GESTOR")).status_code == 403
    assert _enviar(api.como("HOTEL"), estabelecimento=IPE_AMARELO).status_code == 403
    assert _enviar(api.como("HOTEL")).status_code == 201


@pytest.mark.uc("UC02")
def test_ft_doc_05_substituir_arquivo_mantem_documento(api):
    """CF — substituição troca o binário e preserva o identificador do documento."""
    editor = api.como("EDITOR")
    documento = _enviar(editor).json()
    url = f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo"
    novo = b"%PDF-1.4\n% versao 2\n"
    resposta = editor.put(url, files={"arquivo": ("alvara-v2.pdf", novo, "application/pdf")})
    assert resposta.status_code == 200 and resposta.json()["id_documento"] == documento["id_documento"]
    assert editor.get(url).content == novo


# ------------------------------------------------------------------ Requisitos sem funcionalidade
def _operacoes(contrato) -> str:
    return " ".join(f"{metodo} {caminho} {op.get('summary', '')}".casefold()
                    for caminho, ops in contrato["paths"].items() for metodo, op in ops.items() if metodo != "parameters")


@pytest.mark.uc("UC06")
@nao_implementado("NI-06", "Não há importação da base Excel/LibreOffice (UC06, HU-06).")
def test_ft_aus_01_importacao_da_base_excel(contrato):
    """CF UC06 — importar a base de empresas a partir do arquivo Excel/LibreOffice."""
    assert "import" in _operacoes(contrato)


@pytest.mark.uc("UC09", "UC10")
@nao_implementado("NI-07", "Não há backup diário nem restauração de até 30 dias acionável pelo sistema (UC09, UC10, RNF-03/04).")
def test_ft_aus_02_backup_e_restauracao(contrato):
    """CF UC09/UC10 — backup diário e restauração de uma data dos últimos 30 dias."""
    texto = _operacoes(contrato)
    assert "backup" in texto or "restaura" in texto


@pytest.mark.uc("UC05")
@nao_implementado("NI-08", "Não há exportação da lista filtrada de estabelecimentos ('Boletim do Inventário' em PDF/Excel).")
def test_ft_aus_03_exportar_lista_de_estabelecimentos(contrato):
    """CF RF — exportar a lista filtrada de estabelecimentos (Boletim do Inventário)."""
    tipos = contrato["components"]["schemas"]["RelatorioCreate"]["properties"]["tipo"]["enum"]
    assert any(tipo != "OCUPACAO" for tipo in tipos)
