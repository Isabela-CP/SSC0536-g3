"""
Suíte de Validação: Gestão dos Estabelecimentos Turísticos (Task 1)
Disciplina: SSC0536 — Projeto e Desenvolvimento de Sistemas de Informação (Grupo 3 - OTO)
Responsável QA: Juliana Pirolla

Escopo:
    Validação funcional dos casos de uso relacionados ao ciclo de vida cadastral e à
    consulta de estabelecimentos no Inventário Turístico de Olímpia:
      - UC01 e UC02 (RF-01, RF-02): Cadastro de empresa por categoria e validação de
        campos específicos (exclusivo para perfil ADMINISTRADOR, conforme protótipos e OpenAPI).
      - UC04 (RF-04, RNF-05): Inativação lógica (soft delete) mediante justificativa,
        reativação e preservação do histórico cadastral.
      - UC05 (RF-05): Busca textual e aplicação de filtros combinados na listagem.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.main as main_module  # noqa: E402
from app.main import app  # noqa: E402
from app.inventory import JsonInventoryRepository  # noqa: E402


client = TestClient(app)

OPENAPI_FILE = ROOT_DIR / "contratos_api_oto" / "openapi.json"

_INITIAL_USERS = deepcopy(main_module.DEMO_USERS)
_INITIAL_TOKENS = deepcopy(main_module.TOKENS)


@pytest.fixture(autouse=True)
def resetar_estado_em_memoria():
    """Restaura as coleções e o repositório em memória do backend antes de cada caso de teste."""
    main_module.DEMO_USERS.clear()
    main_module.DEMO_USERS.update(deepcopy(_INITIAL_USERS))
    main_module.TOKENS.clear()
    main_module.TOKENS.update(deepcopy(_INITIAL_TOKENS))
    main_module.INVITES.clear()
    main_module.SURVEYS.clear()
    main_module.OCCUPANCY_RESPONSES.clear()
    main_module.AUDIT_LOG.clear()
    main_module.REPORTS.clear()

    repo = main_module.inventory_repository()
    repo.__init__(JsonInventoryRepository(main_module.SEED_FILE))
    yield


def cabecalho_autenticacao(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestGrupoT1ACadastroEmpresa:
    """Cenários de validação para o cadastro e edição de empresas e campos por categoria (UC01 e UC02)."""

    def test_t1_a_01_cadastro_completo_meio_de_hospedagem(self):
        """
        T1.A-01 [Caminho Feliz] — Cadastro completo de meio de hospedagem.
        Verifica se um usuário com perfil Administrador consegue cadastrar um estabelecimento na categoria
        Meios de Hospedagem informando os dados comuns e específicos (tipo, UHs e leitos), resultando
        em registro ativo na listagem.
        """
        payload = {
            "id_categoria": 1,
            "nome_fantasia": "Hotel Teste QA",
            "razao_social": "Hotel Teste QA Ltda.",
            "cnpj": "11.222.333/0001-81",
            "endereco": "Rua A, 100, Olímpia - SP",
            "telefone_comercial": "(17) 99999-0001",
            "meio_hospedagem": {
                "tipo_hospedagem": "HOTEL",
                "total_uh": 30,
                "total_leitos": 60,
            },
        }
        resposta = client.post(
            "/estabelecimentos",
            json=payload,
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 201
        dados = resposta.json()
        assert dados["status"] == "ATIVO"
        assert dados["id_categoria"] == 1
        assert dados["meio_hospedagem"]["total_uh"] == 30
        assert dados["meio_hospedagem"]["total_leitos"] == 60

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Pendência de escopo NC-02: O UC01 lista 7 categorias (incluindo 'Alimentação e Bebidas'), "
            "mas o contrato OpenAPI e o seed limitam o MVP a 'Meios de hospedagem' (id_categoria=1)."
        ),
    )
    def test_t1_a_02_cadastro_alimentacao_e_bebidas(self):
        """
        T1.A-02 [Caminho Feliz] — Cadastro de empresa de Alimentação e Bebidas.
        Verifica a disponibilidade da categoria Alimentação e Bebidas e a aceitação de seus
        respectivos campos específicos (capacidade e culinária), sem vincular atributos exclusivos
        do setor hoteleiro.
        """
        resposta_categorias = client.get(
            "/categorias-estabelecimento",
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta_categorias.status_code == 200
        nomes_categorias = [
            item["nome_categoria"].casefold() for item in resposta_categorias.json()["data"]
        ]
        assert "alimentação e bebidas" in nomes_categorias

    @pytest.mark.skip(
        reason=(
            "Bloqueado (Interface Gráfica): O fluxo de cancelamento de preenchimento depende do formulário "
            "de cadastro no frontend, que ainda não foi implementado em frontend/src/App.jsx."
        )
    )
    def test_t1_a_03_cancelamento_durante_cadastro_nao_persiste_dados(self):
        """
        T1.A-03 [Caminho Feliz] — Cancelamento durante o cadastro não persiste dados.
        Cenário de interface gráfica que verifica se o acionamento da opção 'Cancelar' descarta
        os dados preenchidos sem criar registro no banco ou entrada no log de auditoria.
        """

    def test_t1_a_04_tentativa_cadastro_campos_obrigatorios_ausentes(self):
        """
        T1.A-04 [Exceção] — Tentativa de cadastro com campos obrigatórios ausentes.
        Verifica se a submissão de um cadastro sem o campo obrigatório de nome fantasia é recusada
        com código HTTP 422 e indicação explícita do campo inválido.
        """
        payload = {
            "id_categoria": 1,
            "razao_social": "Empresa Sem Nome Fantasia Ltda.",
            "cnpj": "11.222.333/0001-81",
            "endereco": "Rua A, 100, Olímpia - SP",
        }
        resposta = client.post(
            "/estabelecimentos",
            json=payload,
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 422
        erro = resposta.json()["error"]
        assert erro["code"] == "VALIDATION_ERROR"
        campos_com_erro = [detalhe["field"] for detalhe in erro.get("details", [])]
        assert "nome_fantasia" in campos_com_erro

    def test_t1_a_05_cadastro_com_cnpj_duplicado(self):
        """
        T1.A-05 [Exceção] — Cadastro com CNPJ duplicado.
        Verifica se o sistema impede o cadastro de um estabelecimento cujo CNPJ já consta na base
        (54.839.271/0001-64 — Hotel Serra Azul), retornando conflito (HTTP 409 - CONFLICT).
        """
        payload = {
            "id_categoria": 1,
            "nome_fantasia": "Hotel Duplicado",
            "razao_social": "Hotel Duplicado Ltda.",
            "cnpj": "54.839.271/0001-64",
            "endereco": "Rua B, 200, Olímpia - SP",
        }
        resposta = client.post(
            "/estabelecimentos",
            json=payload,
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 409
        erro = resposta.json()["error"]
        assert erro["code"] == "CONFLICT"

    def test_t1_a_06_valor_invalido_em_campo_numerico(self):
        """
        T1.A-06 [Exceção] — Valor inválido em campo numérico.
        Verifica se a API rejeita o envio de conteúdo textual ('abc') no campo de Unidades
        Habitacionais (total_uh), retornando erro de validação (HTTP 422).
        """
        payload = {
            "id_categoria": 1,
            "nome_fantasia": "Hotel Formato Inválido",
            "razao_social": "Hotel Formato Inválido Ltda.",
            "cnpj": "11.222.333/0001-81",
            "endereco": "Rua A, 100, Olímpia - SP",
            "meio_hospedagem": {
                "tipo_hospedagem": "HOTEL",
                "total_uh": "abc",
                "total_leitos": 60,
            },
        }
        resposta = client.post(
            "/estabelecimentos",
            json=payload,
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 422
        assert resposta.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_t1_a_07_usuarios_sem_perfil_admin_nao_cadastram_estabelecimento(self):
        """
        T1.A-07 [Exceção] — Usuários sem perfil Administrador não realizam cadastro (Regra dos Protótipos).
        Verifica se perfis de consulta (GESTOR) e estagiários (EDITOR) recebem HTTP 403 Forbidden
        ao tentar cadastrar novo estabelecimento, garantindo que mutação cadastral é restrita a administradores.
        """
        payload = {
            "id_categoria": 1,
            "nome_fantasia": "Hotel Não Autorizado",
            "razao_social": "Hotel Não Autorizado Ltda.",
            "cnpj": "11.222.333/0001-81",
            "endereco": "Rua A, 100, Olímpia - SP",
        }
        for token in ("gestor-token", "editor-token"):
            resposta = client.post(
                "/estabelecimentos",
                json=payload,
                headers=cabecalho_autenticacao(token),
            )
            assert resposta.status_code == 403

    def test_t1_a_08_edicao_parcial_dados_estabelecimento(self):
        """
        T1.A-08 [Caminho Feliz] — Edição parcial de dados do estabelecimento via Administrador.
        Verifica se um usuário com perfil Administrador consegue atualizar dados operacionais
        (telefone comercial, total de UHs e total de leitos) de um estabelecimento existente
        via PATCH /estabelecimentos/{id_estabelecimento}.
        """
        id_estabelecimento = "11111111-1111-4111-8111-111111111111"
        payload = {
            "telefone_comercial": "+55 16 3333-2000",
            "meio_hospedagem": {
                "tipo_hospedagem": "HOTEL",
                "total_uh": 52,
                "total_leitos": 104,
            },
        }
        resposta = client.patch(
            f"/estabelecimentos/{id_estabelecimento}",
            json=payload,
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 200
        dados = resposta.json()
        assert dados["id_estabelecimento"] == id_estabelecimento
        assert dados["telefone_comercial"] == "+55 16 3333-2000"
        assert dados["meio_hospedagem"]["total_uh"] == 52
        assert dados["meio_hospedagem"]["total_leitos"] == 104


class TestGrupoT1BInativacaoEmpresa:
    """Cenários de validação para a inativação lógica e preservação do histórico cadastral (UC04)."""

    def test_t1_b_01_inativacao_empresa_ativa_com_motivo(self):
        """
        T1.B-01 [Caminho Feliz] — Inativação de empresa ativa com motivo pelo Administrador.
        Verifica se a inativação de um estabelecimento ativo altera seu status para INATIVO,
        preservando seu identificador e seus dados históricos na base.
        """
        id_estabelecimento = "11111111-1111-4111-8111-111111111111"
        motivo = "Encerramento das atividades em 10/2026"

        resposta = client.post(
            f"/estabelecimentos/{id_estabelecimento}/inativacao",
            json={"motivo_inativacao": motivo},
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 200
        dados = resposta.json()
        assert dados["id_estabelecimento"] == id_estabelecimento
        assert dados["status"] == "INATIVO"
        assert dados["motivo_inativacao"] == motivo

    @pytest.mark.skip(
        reason=(
            "Bloqueado (Interface Gráfica): O cancelamento na caixa de diálogo de confirmação "
            "depende do componente visual de inativação no frontend, ainda não implementado."
        )
    )
    def test_t1_b_02_cancelamento_da_inativacao_preserva_status(self):
        """
        T1.B-02 [Caminho Feliz] — Cancelamento da inativação preserva status.
        Cenário de interface que avalia se a desistência na tela de confirmação mantém o
        estabelecimento com status Ativo e sem novos registros no log de auditoria.
        """

    def test_t1_b_03_tentativa_inativar_empresa_ja_inativa_oferece_reativacao(self):
        """
        T1.B-03 [Exceção] — Tentativa de inativar empresa já inativa e fluxo de reativação.
        Verifica se o acionamento de inativação sobre o registro inativo (Hotel Vale do Sol)
        retorna conflito (HTTP 409 - ESTABELECIMENTO_JA_INATIVO) e se a rota de reativação
        restabelece o status ATIVO.
        """
        id_inativo = "33333333-3333-4333-8333-333333333333"

        resposta_inativacao = client.post(
            f"/estabelecimentos/{id_inativo}/inativacao",
            json={"motivo_inativacao": "Tentativa duplicada de inativação"},
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta_inativacao.status_code == 409
        assert resposta_inativacao.json()["error"]["code"] == "ESTABELECIMENTO_JA_INATIVO"

        resposta_reativacao = client.post(
            f"/estabelecimentos/{id_inativo}/reativacao",
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta_reativacao.status_code == 200
        assert resposta_reativacao.json()["status"] == "ATIVO"

    def test_t1_b_04_ausencia_de_opcao_de_exclusao_definitiva(self):
        """
        T1.B-04 [Exceção] — Ausência de opção de exclusão definitiva.
        Verifica no contrato OpenAPI e diretamente na API que nenhum perfil de usuário dispõe
        de operação HTTP DELETE para remover fisicamente um estabelecimento.
        """
        id_estabelecimento = "11111111-1111-4111-8111-111111111111"

        especificacao_openapi = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
        operacoes_item = set(
            especificacao_openapi["paths"].get("/estabelecimentos/{id_estabelecimento}", {}).keys()
        )
        assert "delete" not in operacoes_item

        for token in ("editor-token", "gestor-token", "admin-token"):
            resposta_delete = client.delete(
                f"/estabelecimentos/{id_estabelecimento}",
                headers=cabecalho_autenticacao(token),
            )
            assert resposta_delete.status_code == 405

        consulta = client.get(
            f"/estabelecimentos/{id_estabelecimento}",
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert consulta.status_code == 200
        assert consulta.json()["id_estabelecimento"] == id_estabelecimento


class TestGrupoT1CBuscaEFiltros:
    """Cenários de validação para pesquisa textual e filtragem combinada de estabelecimentos (UC05)."""

    def test_t1_c_01_busca_por_nome_retorna_resultado_correto(self):
        """
        T1.C-01 [Caminho Feliz] — Busca por nome retorna resultado correto.
        Verifica se a busca pelo nome fantasia 'Hotel Serra Azul' retorna exclusivamente o
        registro correspondente, omitindo os demais estabelecimentos da base.
        """
        resposta = client.get(
            "/estabelecimentos",
            params={"busca": "Hotel Serra Azul"},
            headers=cabecalho_autenticacao("editor-token"),
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["pagination"]["total"] == 1
        assert len(corpo["data"]) == 1
        assert corpo["data"][0]["nome_fantasia"] == "Hotel Serra Azul"
        assert corpo["data"][0]["id_estabelecimento"] == "11111111-1111-4111-8111-111111111111"

    def test_t1_c_02_filtro_combinado_categoria_e_status(self):
        """
        T1.C-02 [Caminho Feliz] — Filtro combinado: categoria + status.
        Verifica se a aplicação simultânea dos filtros id_categoria=1 e status=ATIVO retorna
        apenas os estabelecimentos que cumprem ambos os critérios, excluindo registros inativos.
        """
        resposta = client.get(
            "/estabelecimentos",
            params={"id_categoria": 1, "status": "ATIVO"},
            headers=cabecalho_autenticacao("editor-token"),
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["pagination"]["total"] == 3

        ids_retornados = {item["id_estabelecimento"] for item in corpo["data"]}
        assert "33333333-3333-4333-8333-333333333333" not in ids_retornados
        for item in corpo["data"]:
            assert item["id_categoria"] == 1
            assert item["status"] == "ATIVO"

    def test_t1_c_03_limpeza_de_filtros_restaura_listagem_completa(self):
        """
        T1.C-03 [Caminho Feliz] — Limpeza de filtros restaura listagem completa.
        Verifica se, após uma consulta restrita por filtro, uma nova requisição sem parâmetros
        de filtragem restabelece a listagem integral dos estabelecimentos cadastrados.
        """
        filtrado = client.get(
            "/estabelecimentos",
            params={"status": "INATIVO"},
            headers=cabecalho_autenticacao("editor-token"),
        ).json()
        assert filtrado["pagination"]["total"] == 1

        listagem_completa = client.get(
            "/estabelecimentos",
            headers=cabecalho_autenticacao("editor-token"),
        ).json()
        assert listagem_completa["pagination"]["total"] == 4
        assert len(listagem_completa["data"]) == 4

    def test_t1_c_04_busca_sem_resultados_retorna_colecao_vazia(self):
        """
        T1.C-04 [Exceção] — Busca sem resultados retorna coleção vazia.
        Verifica se a pesquisa por um termo inexistente na base retorna HTTP 200 com coleção
        vazia (data=[]) e total=0 na paginação, conforme o contrato OpenAPI (a exibição da
        mensagem orientativa prevista no fluxo alternativo 3a do UC05 cabe à interface gráfica).
        """
        resposta = client.get(
            "/estabelecimentos",
            params={"busca": "ZZZ_Empresa_Inexistente"},
            headers=cabecalho_autenticacao("editor-token"),
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["data"] == []
        assert corpo["pagination"]["total"] == 0
