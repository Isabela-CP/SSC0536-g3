"""Integração API ↔ PostgreSQL ↔ armazenamento de arquivos (disco local e Supabase Storage).

Os mesmos cenários rodam nos dois provedores: o local (Docker) e o Supabase (Render),
este por meio de um dublê da Storage API (apoio.SupabaseFalso).
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.postgres_portal import PostgresPortal
from apoio import PDF_MINIMO, SERRA_AZUL, defeito, enviar_documento
from conftest import limpar_caches

CSV_INICIO = "Pesquisa"


def _local():
    docs, rels = Path(os.environ["OTO_STORAGE_DIR"]), Path(os.environ["OTO_REPORT_STORAGE_DIR"])
    listar = lambda raiz: {p.name for p in raiz.glob("*") if p.is_file()} if raiz.exists() else set()  # noqa: E731
    return SimpleNamespace(nome="local", documentos=lambda: listar(docs), relatorios=lambda: listar(rels),
                           remover=lambda chave: (docs / chave).unlink(), falso=None)


def _supabase(falso):
    so_chave = lambda prefixo: {k.split("/", 1)[1] for k in falso.chaves(prefixo)}  # noqa: E731
    return SimpleNamespace(nome="supabase", documentos=lambda: so_chave("documentos"),
                           relatorios=lambda: so_chave("relatorios"),
                           remover=lambda chave: falso.objetos.pop(f"documentos/{chave}"), falso=falso)


@pytest.fixture(params=["local", pytest.param("supabase", marks=pytest.mark.hospedagem)])
def storage(request, sistema):
    if request.param == "local":
        return _local()
    return _supabase(request.getfixturevalue("supabase"))


def _chave_no_banco(sistema, id_documento):
    return sistema.sql("SELECT caminho_storage FROM documentos_controle WHERE id_documento=%s", (id_documento,))[0]["caminho_storage"]


def _falhar_auditoria(monkeypatch, acao):
    original = PostgresPortal.audit

    def falha(self, actor, action, *args, **kwargs):
        if action == acao:
            raise RuntimeError("falha simulada na auditoria")
        return original(self, actor, action, *args, **kwargs)

    monkeypatch.setattr(PostgresPortal, "audit", falha)


def _documentos_no_banco(sistema):
    return sistema.sql("SELECT count(*) AS n FROM documentos_controle")[0]["n"]


# ------------------------------------------------------------------ envio e download
@pytest.mark.integracao("api", "postgresql", "storage")
def test_int_arq_01_envio_e_download_integro(sistema, storage):
    """CF — o binário vai ao storage com chave gerada no servidor; o banco guarda só metadados e a referência."""
    admin = sistema.como("ADMINISTRADOR")
    conteudo = PDF_MINIMO + os.urandom(2048)
    resposta = enviar_documento(admin, conteudo, nome="..\\..\\alvara final.pdf")
    assert resposta.status_code == 201, resposta.text
    documento = resposta.json()
    assert documento["arquivo"]["nome_arquivo"] == "alvara final.pdf"
    assert documento["arquivo"]["tamanho_bytes"] == len(conteudo)
    chave = _chave_no_banco(sistema, documento["id_documento"])
    assert storage.documentos() == {chave}
    baixado = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert baixado.status_code == 200 and baixado.content == conteudo
    assert baixado.headers["content-type"] == "application/octet-stream"      # contrato OpenAPI
    assert baixado.headers["content-disposition"] == "attachment; filename*=UTF-8''alvara%20final.pdf"
    visoes = [resposta.text, admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos").text,
              admin.get(f"/estabelecimentos/{SERRA_AZUL}").text, admin.get("/auditoria").text]
    assert not any(chave in v for v in visoes), "a chave interna do storage não pode ser exposta"


@pytest.mark.integracao("api", "postgresql", "storage", "auditoria")
def test_int_arq_02_falha_apos_gravar_arquivo_nao_deixa_orfao(sistema, storage, monkeypatch):
    """EX — a auditoria falha depois de o arquivo ser gravado: nem registro, nem arquivo órfão."""
    antes = _documentos_no_banco(sistema)
    _falhar_auditoria(monkeypatch, "DOCUMENTO_CRIADO")
    assert enviar_documento(sistema.como("ADMINISTRADOR")).status_code == 500
    assert _documentos_no_banco(sistema) == antes
    assert storage.documentos() == set()


@pytest.mark.integracao("api", "postgresql", "storage")
def test_int_arq_03_substituicao_remove_o_arquivo_anterior(sistema, storage):
    """CF — substituir o arquivo grava o novo, aponta o banco para ele e remove o antigo do storage."""
    admin = sistema.como("ADMINISTRADOR")
    documento = enviar_documento(admin, PDF_MINIMO + b"v1").json()
    antiga = _chave_no_banco(sistema, documento["id_documento"])
    url = f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo"
    resposta = admin.put(url, files={"arquivo": ("v2.png", b"\x89PNG\r\n\x1a\nconteudo-v2", "image/png")})
    assert resposta.status_code == 200, resposta.text
    nova = _chave_no_banco(sistema, documento["id_documento"])
    assert nova != antiga and storage.documentos() == {nova}
    assert admin.get(url).content == b"\x89PNG\r\n\x1a\nconteudo-v2"


@pytest.mark.integracao("api", "postgresql", "storage", "auditoria")
def test_int_arq_04_substituicao_com_falha_preserva_o_anterior(sistema, storage, monkeypatch):
    """EX — se a substituição falha na auditoria, o arquivo anterior continua íntegro e o novo é descartado."""
    admin = sistema.como("ADMINISTRADOR")
    documento = enviar_documento(admin, PDF_MINIMO + b"original").json()
    antiga = _chave_no_banco(sistema, documento["id_documento"])
    _falhar_auditoria(monkeypatch, "DOCUMENTO_ARQUIVO_SUBSTITUIDO")
    url = f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo"
    assert admin.put(url, files={"arquivo": ("novo.pdf", PDF_MINIMO + b"novo", "application/pdf")}).status_code == 500
    assert _chave_no_banco(sistema, documento["id_documento"]) == antiga
    assert storage.documentos() == {antiga}
    assert admin.get(url).content == PDF_MINIMO + b"original"


@pytest.mark.integracao("api", "postgresql", "storage")
def test_int_arq_05_arquivo_ausente_no_storage(sistema, storage):
    """EX — arquivo removido do storage por fora: download responde 404, sem erro interno."""
    admin = sistema.como("ADMINISTRADOR")
    documento = enviar_documento(admin).json()
    storage.remover(_chave_no_banco(sistema, documento["id_documento"]))
    resposta = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert resposta.status_code == 404 and resposta.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.integracao("api", "postgresql", "storage")
@defeito("DF-11", "Documento do seed tem caminho_storage fora do formato UUID: o storage lança ValueError e o "
                  "download responde 500, e não 404 como documenta o backend/README.md.")
def test_int_arq_06_documento_do_seed_sem_binario(sistema, storage):
    """EX — metadados do seed sem binário: download 404 (o sistema não fabrica arquivos)."""
    admin = sistema.como("ADMINISTRADOR")
    documentos = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos").json()["data"]
    assert documentos
    for documento in documentos:
        resposta = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
        assert resposta.status_code == 404


@pytest.mark.integracao("api", "storage", "configuracao")
def test_int_arq_07_limite_configurado_de_upload(sistema, storage, monkeypatch):
    """EX — OTO_UPLOAD_MAX_BYTES chega ao storage: no limite aceita; um byte acima, 413 sem gravar nada."""
    monkeypatch.setenv("OTO_UPLOAD_MAX_BYTES", "1024")
    limpar_caches()
    admin = sistema.como("ADMINISTRADOR")
    antes = _documentos_no_banco(sistema)
    acima = enviar_documento(admin, b"%PDF" + b"x" * 1021)
    assert acima.status_code == 413 and acima.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert storage.documentos() == set() and _documentos_no_banco(sistema) == antes
    assert enviar_documento(admin, b"%PDF" + b"x" * 1020).status_code == 201


@pytest.mark.integracao("api", "storage", "processo")
def test_int_arq_08_arquivos_sobrevivem_a_novo_processo(sistema, storage):
    """CF — depois de recriar conexões e storage (novo processo da API), o download continua idêntico."""
    admin = sistema.como("ADMINISTRADOR")
    documento = enviar_documento(admin, PDF_MINIMO + b"persistente").json()
    limpar_caches()
    resposta = sistema.como("EDITOR").get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert resposta.content == PDF_MINIMO + b"persistente"


# ------------------------------------------------------------------ relatórios
@pytest.mark.integracao("api", "postgresql", "storage-relatorios")
@pytest.mark.parametrize("formato,tipo", [("CSV", "text/csv"), ("PDF", "application/pdf")])
def test_int_arq_09_relatorio_gravado_e_baixado(sistema, storage, formato, tipo):
    """CF — relatório gerado vai ao storage de relatórios e o download devolve exatamente o arquivo gravado."""
    gestor = sistema.como("GESTOR")
    relatorio = gestor.post("/relatorios", json={"tipo": "OCUPACAO", "formato": formato})
    assert relatorio.status_code == 202 and relatorio.json()["status"] == "CONCLUIDO"
    assert len(storage.relatorios()) == 1 and storage.documentos() == set()
    arquivo = gestor.get(f"/relatorios/{relatorio.json()['id_relatorio']}/arquivo")
    assert arquivo.status_code == 200 and arquivo.headers["content-type"].startswith(tipo)
    assert arquivo.headers["content-disposition"] == f'attachment; filename="relatorio.{formato.lower()}"'
    assert len(arquivo.content) == relatorio.json()["arquivo"]["tamanho_bytes"]
    if formato == "CSV":
        assert arquivo.content.decode("utf-8-sig").startswith(CSV_INICIO)
    else:
        assert arquivo.content.startswith(b"%PDF")


@pytest.mark.integracao("api", "postgresql", "storage-relatorios", "auditoria")
def test_int_arq_10_relatorio_com_falha_no_banco_nao_deixa_arquivo(sistema, storage, monkeypatch):
    """EX — se o registro do relatório falha, o arquivo já gravado é removido do storage."""
    antes = sistema.sql("SELECT count(*) AS n FROM relatorios")[0]["n"]
    _falhar_auditoria(monkeypatch, "RELATORIO_GERADO")
    assert sistema.como("GESTOR").post("/relatorios", json={"tipo": "OCUPACAO", "formato": "CSV"}).status_code == 500
    assert storage.relatorios() == set()
    assert sistema.sql("SELECT count(*) AS n FROM relatorios")[0]["n"] == antes


# ------------------------------------------------------------------ só Supabase (hospedagem)
@pytest.mark.hospedagem
@pytest.mark.integracao("api", "postgresql", "supabase")
def test_int_arq_11_supabase_indisponivel(sistema, supabase):
    """EX — Storage fora do ar: 503 genérico, nenhum registro nem auditoria; download também 503."""
    admin = sistema.como("ADMINISTRADOR")
    documento = enviar_documento(admin).json()
    antes = _documentos_no_banco(sistema)
    supabase.falhar = {"POST", "GET"}
    resposta = enviar_documento(admin)
    assert resposta.status_code == 503 and resposta.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert "supabase" not in resposta.text.lower() and "falha interna simulada" not in resposta.text
    assert _documentos_no_banco(sistema) == antes
    assert len(admin.get("/auditoria", params={"acao": "DOCUMENTO_CRIADO"}).json()["data"]) == 1
    download = admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert download.status_code == 503


@pytest.mark.hospedagem
@pytest.mark.integracao("storage", "supabase", "configuracao")
@pytest.mark.parametrize("chave,autorizacao", [("sb_secret_qa_nova", False), ("eyJhbGciOiJIUzI1NiJ9.legada.qa", True)])
def test_int_arq_12_cabecalhos_por_tipo_de_chave(sistema, supabase, monkeypatch, chave, autorizacao):
    """CF — chave nova (sb_secret_) vai só em `apikey`; a legada (service_role JWT) também em Authorization."""
    monkeypatch.setenv("OTO_SUPABASE_SERVICE_KEY", chave)
    supabase.chave = chave
    limpar_caches()
    admin = sistema.como("ADMINISTRADOR")
    documento = enviar_documento(admin).json()
    admin.get(f"/estabelecimentos/{SERRA_AZUL}/documentos/{documento['id_documento']}/arquivo")
    assert {r.metodo for r in supabase.requisicoes} >= {"POST", "GET"}
    for requisicao in supabase.requisicoes:
        assert requisicao.cabecalhos["apikey"] == chave
        assert ("authorization" in requisicao.cabecalhos) is autorizacao
        assert "/oto-arquivos/documentos/" in requisicao.caminho


@pytest.mark.integracao("api", "postgresql", "storage-relatorios", "seguranca")
def test_int_arq_13_relatorio_neutraliza_formulas_e_marcacao(sistema, storage):
    """EX — textos digitados nos cadastros chegam ao CSV sem virar fórmula (OWASP) e ao PDF sem virar marcação."""
    admin, editor = sistema.como("ADMINISTRADOR"), sistema.como("EDITOR")
    titulos = ["=HYPERLINK(\"http://x.example\")", "+SOMA(1;2)", "-2+3", "@cmd", "<b>negrito</b> & cia"]
    for i, titulo in enumerate(titulos):
        pesquisa = editor.post("/pesquisas-ocupacao", json={"titulo": titulo, "tipo": "EXPECTATIVA",
                               "periodo_inicio": f"2027-0{i + 1}-01", "periodo_fim": f"2027-0{i + 1}-20",
                               "estabelecimentos": [SERRA_AZUL]})
        assert pesquisa.status_code == 201, pesquisa.text
        assert sistema.como("HOTEL").post(f"/pesquisas-ocupacao/{pesquisa.json()['id_pesquisa']}/respostas",
                                          json={"taxa_ocupacao": 10 + i}).status_code == 201
    gestor = sistema.como("GESTOR")
    csv_id = gestor.post("/relatorios", json={"tipo": "OCUPACAO", "formato": "CSV"}).json()["id_relatorio"]
    texto = gestor.get(f"/relatorios/{csv_id}/arquivo").content.decode("utf-8-sig")
    import csv
    celulas = [linha[0] for linha in csv.reader(texto.splitlines())]
    for titulo in titulos[:4]:
        assert "'" + titulo in celulas, f"fórmula não neutralizada: {titulo}"
        assert titulo not in celulas
    pdf_id = gestor.post("/relatorios", json={"tipo": "OCUPACAO", "formato": "PDF"}).json()
    assert pdf_id["status"] == "CONCLUIDO"        # marcação escapada: o PDF é gerado sem erro de parsing


@pytest.mark.hospedagem
@pytest.mark.integracao("api", "postgresql", "supabase", "auditoria")
def test_int_arq_14_falha_dupla_auditoria_e_limpeza(sistema, supabase, monkeypatch):
    """EX — auditoria falha e o Storage também recusa a limpeza: o cliente recebe erro e o banco fica sem registro."""
    antes = _documentos_no_banco(sistema)
    _falhar_auditoria(monkeypatch, "DOCUMENTO_CRIADO")
    supabase.falhar = {"DELETE"}
    resposta = enviar_documento(sistema.como("ADMINISTRADOR"))
    assert resposta.status_code >= 500
    assert _documentos_no_banco(sistema) == antes
