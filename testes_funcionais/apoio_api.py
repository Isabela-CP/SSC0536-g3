"""Massa de dados e utilitários da camada de API (importados pelos testes; fixtures ficam no conftest)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

# --------------------------------------------------------------------- massa de dados
SENHAS = {"ADMINISTRADOR": "admin-demo", "GESTOR": "gestor-demo", "EDITOR": "editor-demo", "HOTEL": "hotel-demo"}
CONTAS = {
    "ADMINISTRADOR": "marina.admin@example.test",
    "GESTOR": "rafael.consulta@example.test",
    "EDITOR": "camila.editora@example.test",
    "HOTEL": "responsavel@serra-azul.example",          # vínculo: Hotel Serra Azul
    "HOTEL_IPE": "responsavel@ipe-amarelo.example",      # vínculo: Pousada Ipê Amarelo
    "HOTEL_INATIVO": "hotel.valedosol@example.test",     # vínculo: Hotel Vale do Sol (INATIVO)
    "GESTOR_INATIVO": "fernanda.gestora@example.test",   # conta INATIVA
    "EDITOR_PENDENTE": "juliana.editor@example.test",    # conta PENDENTE (sem convite aceito)
}
SERRA_AZUL = "11111111-1111-4111-8111-111111111111"   # ATIVO, aceita pesquisas
IPE_AMARELO = "22222222-2222-4222-8222-222222222222"  # ATIVO, aceita pesquisas
VALE_DO_SOL = "33333333-3333-4333-8333-333333333333"  # INATIVO, não aceita pesquisas
EM_CADASTRO = "44444444-4444-4444-8444-444444444444"  # ATIVO, aceita pesquisas
CNPJ_SERRA_AZUL = "54.839.271/0001-64"
CNPJ_LIVRE = "11.222.333/0001-81"          # válido e ausente do seed
CNPJ_LIVRE_2 = "22.333.444/0001-81"
PESQUISA_CONSOLIDADO_ABERTA = "3"          # Serra Azul já respondeu; demais pendentes
PESQUISA_EXPECTATIVA_ABERTA = "4"          # nenhuma resposta enviada
PESQUISA_ENCERRADA = "1"


def novo_estabelecimento(**extra) -> dict:
    payload = {"id_categoria": 1, "nome_fantasia": "Hotel Funcional", "razao_social": "Hotel Funcional Ltda.",
               "cnpj": CNPJ_LIVRE, "endereco": "Rua dos Testes, 100, Olímpia - SP"}
    payload.update(extra)
    return payload


def nova_pesquisa(**extra) -> dict:
    payload = {"titulo": "Pesquisa funcional", "tipo": "CONSOLIDADO", "periodo_inicio": "2026-12-01",
               "periodo_fim": "2026-12-15", "estabelecimentos": [SERRA_AZUL, IPE_AMARELO]}
    payload.update(extra)
    return payload


def erro(resposta) -> SimpleNamespace:
    corpo = resposta.json().get("error", {})
    return SimpleNamespace(code=corpo.get("code"), message=corpo.get("message"),
                           campos=[d.get("field") for d in corpo.get("details", []) or []])


def defeito(codigo: str, motivo: str):
    """Teste que evidencia defeito: falha esperada estrita (XPASS indica correção)."""
    def aplicar(func):
        func = pytest.mark.defeito(codigo)(func)
        return pytest.mark.xfail(strict=True, reason=f"{codigo}: {motivo}")(func)
    return aplicar


def nao_implementado(codigo: str, motivo: str):
    """Requisito sem funcionalidade correspondente na build avaliada."""
    def aplicar(func):
        func = pytest.mark.nao_implementado(codigo)(func)
        return pytest.mark.xfail(strict=True, reason=f"{codigo}: {motivo}")(func)
    return aplicar
