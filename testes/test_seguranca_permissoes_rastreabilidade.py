"""
Suíte de Validação: Segurança, Permissões e Rastreabilidade (Task 2)
Disciplina: SSC0536 — Projeto e Desenvolvimento de Sistemas de Informação (Grupo 3 - OTO)
Responsável QA: Juliana Pirolla

Escopo:
    Validação funcional e não funcional dos mecanismos de controle de acesso por perfil,
    autenticação, integridade transacional do log de auditoria e isolamento de dados do
    Painel do Empresário:
      - UC00 (RF-06, RNF-01, RNF-02): Autenticação de usuários internos e restrição de rotas.
      - UC07 (RF-06, RF-07, RNF-02): Gestão de contas e perfis pelo Administrador e proteção
        do último administrador do sistema.
      - UC03 e UC08 (RF-03, RNF-05): Rastreabilidade de alterações no Audit Log, imutabilidade
        e atomicidade transacional.
      - UC11 (RF-08): Autenticação do empresário via CNPJ/senha, bloqueio por inatividade ou
        tentativas excessivas e isolamento estrito entre estabelecimentos.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch

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

_INITIAL_USERS = deepcopy(main_module.DEMO_USERS)
_INITIAL_TOKENS = deepcopy(main_module.TOKENS)


@pytest.fixture(autouse=True)
def resetar_estado_em_memoria():
    """Restaura as coleções em memória do backend antes de cada caso de teste."""
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


class TestGrupoT2AAutenticacaoUsuariosInternos:
    """Cenários de validação para autenticação e controle de sessão de usuários internos (UC00)."""

    def test_t2_a_01_login_bem_sucedido_e_carregamento_de_perfil_correto(self):
        """
        T2.A-01 [Caminho Feliz] — Login bem-sucedido e carregamento de perfil correto.
        Verifica se um usuário com perfil Editor autentica-se com sucesso, recebe seu token de
        sessão com o perfil correspondente e permanece impedido de acessar recursos exclusivos
        de perfis superiores (gestão de usuários e log de auditoria).
        """
        resposta = client.post(
            "/auth/login",
            json={"email": "camila.editora@example.test", "senha": "editor-demo"},
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["access_token"] == "editor-token"
        assert corpo["token_type"] == "Bearer"
        assert corpo["usuario"]["perfil"] == "EDITOR"
        assert corpo["usuario"]["ativo"] is True

        headers = cabecalho_autenticacao(corpo["access_token"])
        assert client.get("/usuarios", headers=headers).status_code == 403
        assert client.get("/auditoria", headers=headers).status_code == 403

    def test_t2_a_02_credenciais_invalidas_senha_incorreta(self):
        """
        T2.A-02 [Exceção] — Credenciais inválidas: senha incorreta.
        Verifica se a tentativa de login com senha incorreta é rejeitada com HTTP 401 e retorna
        mensagem genérica idêntica à exibida para e-mail inexistente, prevenindo enumeração de contas.
        """
        resposta_senha_incorreta = client.post(
            "/auth/login",
            json={"email": "camila.editora@example.test", "senha": "senha-incorreta"},
        )
        resposta_email_inexistente = client.post(
            "/auth/login",
            json={"email": "nao.cadastrado@example.test", "senha": "senha-incorreta"},
        )
        assert resposta_senha_incorreta.status_code == 401
        assert resposta_email_inexistente.status_code == 401
        assert "access_token" not in resposta_senha_incorreta.json()

        erro_senha = resposta_senha_incorreta.json()["error"]
        erro_email = resposta_email_inexistente.json()["error"]
        assert erro_senha["code"] == "INVALID_CREDENTIALS"
        assert erro_senha["message"] == erro_email["message"] == "E-mail ou senha inválidos."

    def test_t2_a_03_acesso_negado_a_funcionalidade_de_perfil_superior(self):
        """
        T2.A-03 [Exceção] — Acesso negado a funcionalidade de perfil superior.
        Verifica se o perfil somente leitura (GESTOR / Visualização) tem qualquer tentativa de
        execução de operações de escrita bloqueada com HTTP 403 Forbidden.
        """
        login = client.post(
            "/auth/login",
            json={"email": "rafael.consulta@example.test", "senha": "gestor-demo"},
        )
        assert login.status_code == 200
        headers_visualizacao = cabecalho_autenticacao(login.json()["access_token"])

        resposta_pesquisa = client.post(
            "/pesquisas-ocupacao",
            json={
                "titulo": "Pesquisa Não Autorizada",
                "tipo": "MENSAL",
                "periodo_inicio": "2026-11-01",
                "periodo_fim": "2026-11-30",
                "estabelecimentos": ["11111111-1111-4111-8111-111111111111"],
            },
            headers=headers_visualizacao,
        )
        assert resposta_pesquisa.status_code == 403
        assert client.post("/usuarios", json={}, headers=headers_visualizacao).status_code == 403
        assert client.post("/convites", json={"email": "x@example.test"}, headers=headers_visualizacao).status_code == 403

    def test_t2_a_04_acesso_sem_autenticacao_bloqueado_nas_rotas_internas(self):
        """
        T2.A-04 [Exceção] — Acesso sem autenticação exige login prévio.
        Verifica se requisições desprovidas de cabeçalho Authorization são barradas com HTTP 401
        em todas as rotas internas do sistema, impedindo exposição de dados antes da autenticação.
        """
        rotas_internas = (
            "/perfil",
            "/usuarios",
            "/auditoria",
            "/dashboard",
            "/estabelecimentos",
            "/estabelecimentos/11111111-1111-4111-8111-111111111111",
        )
        for rota in rotas_internas:
            resposta = client.get(rota)
            assert resposta.status_code == 401, (
                f"A rota interna {rota} retornou status {resposta.status_code} sem autenticação."
            )


class TestGrupoT2BGerenciamentoPerfisAcesso:
    """Cenários de validação para criação e manutenção de perfis de acesso de usuários (UC07)."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-07: Embora POST /usuarios crie a conta e registre a ação no log, "
            "o login posterior do novo usuário falha com exceção não tratada (StopIteration em "
            "backend/app/main.py, linha 171) porque o dicionário TOKENS é estático e não aloca "
            "credencial de sessão para usuários recém-cadastrados."
        ),
    )
    def test_t2_b_01_administrador_cria_novo_usuario_com_perfil_editor(self):
        """
        T2.B-01 [Caminho Feliz] — Administrador cria novo usuário com perfil Editor.
        Verifica o fluxo completo de criação de conta com perfil Editor pelo Administrador,
        registro no log de auditoria, ativação via convite e autenticação subsequente do novo usuário.
        """
        headers_admin = cabecalho_autenticacao("admin-token")

        criacao = client.post(
            "/usuarios",
            json={"nome": "Beatriz Silva", "email": "beatriz.silva@example.test", "perfil": "EDITOR"},
            headers=headers_admin,
        )
        assert criacao.status_code == 201
        assert criacao.json()["perfil"] == "EDITOR"

        listagem = client.get("/usuarios", headers=headers_admin).json()["data"]
        assert any(u["email"] == "beatriz.silva@example.test" and u["perfil"] == "EDITOR" for u in listagem)

        logs = client.get("/auditoria", params={"acao": "USUARIO_CRIADO"}, headers=headers_admin).json()["data"]
        assert len(logs) == 1
        assert logs[0]["depois"]["perfil"] == "EDITOR"

        convite = client.post("/convites", json={"email": "beatriz.silva@example.test"}, headers=headers_admin)
        assert convite.status_code == 201
        id_convite = convite.json()["id_convite"]
        token_convite = next(item["token"] for item in main_module.INVITES if item["id_convite"] == id_convite)

        aceitacao = client.post(
            f"/convites/{id_convite}/aceitacao",
            json={"token": token_convite, "senha": "senha-editor-123"},
        )
        assert aceitacao.status_code == 200

        login_novo_usuario = client.post(
            "/auth/login",
            json={"email": "beatriz.silva@example.test", "senha": "senha-editor-123"},
        )
        assert login_novo_usuario.status_code == 200

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-08: Não há rota PATCH /usuarios/{id_usuario} implementada em "
            "backend/app/main.py para permitir ao Administrador alterar o perfil de um usuário existente."
        ),
    )
    def test_t2_b_02_administrador_altera_perfil_de_usuario_existente(self):
        """
        T2.B-02 [Caminho Feliz] — Administrador altera perfil de usuário existente.
        Verifica a atualização do perfil de um usuário de Visualização (GESTOR) para Editor
        pelo Administrador.
        """
        resposta = client.patch(
            "/usuarios/2",
            json={"perfil": "EDITOR"},
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 200
        assert resposta.json()["perfil"] == "EDITOR"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-08 / Pendência NC-09: Ausência de endpoint de remoção ou alteração "
            "de perfil de usuários em backend/app/main.py (DELETE /usuarios/1 retorna HTTP 404), "
            "tornando ainda não verificável a regra de proteção do último Administrador (UC07 3a)."
        ),
    )
    def test_t2_b_03_bloqueio_de_remocao_do_ultimo_administrador(self):
        """
        T2.B-03 [Exceção] — Bloqueio de remoção do último administrador.
        Verifica se o sistema impede a remoção ou alteração de perfil quando há apenas um
        usuário com perfil Administrador cadastrado.
        """
        resposta = client.delete(
            "/usuarios/1",
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code in {400, 409, 422}
        assert "error" in resposta.json()

    def test_t2_b_04_usuario_nao_administrador_nao_acessa_gestao_de_usuarios(self):
        """
        T2.B-04 [Exceção] — Usuário não-administrador não acessa gestão de usuários.
        Verifica se um usuário autenticado com perfil Editor recebe HTTP 403 Forbidden ao
        acessar diretamente as rotas de listagem e criação de usuários.
        """
        headers_editor = cabecalho_autenticacao("editor-token")
        assert client.get("/usuarios", headers=headers_editor).status_code == 403
        assert client.post(
            "/usuarios",
            json={"nome": "Teste", "email": "teste@example.test", "perfil": "EDITOR"},
            headers=headers_editor,
        ).status_code == 403


class TestGrupoT2CIntegridadeAuditLog:
    """Cenários de validação para rastreabilidade, consulta, imutabilidade e atomicidade do Audit Log (UC03 e UC08)."""

    def test_t2_c_01_audit_log_registra_criacao_de_empresa(self):
        """
        T2.C-01 [Caminho Feliz] — Audit log registra criação de empresa.
        Verifica se o cadastro de um novo estabelecimento pelo Administrador gera exatamente uma
        entrada no log de auditoria com a ação ESTABELECIMENTO_CRIADO.
        """
        payload = {
            "id_categoria": 1,
            "nome_fantasia": "Hotel Teste Audit",
            "razao_social": "Hotel Teste Audit Ltda.",
            "cnpj": "11.222.333/0001-81",
            "endereco": "Rua A, 100, Olímpia - SP",
        }
        resposta = client.post(
            "/estabelecimentos",
            json=payload,
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 201
        id_criado = resposta.json()["id_estabelecimento"]

        logs = client.get("/auditoria", headers=cabecalho_autenticacao("admin-token")).json()["data"]
        assert any(
            registro["entidade"] == "ESTABELECIMENTO"
            and registro["acao"] == "ESTABELECIMENTO_CRIADO"
            and registro["id_entidade"] == id_criado
            for registro in logs
        )

    def test_t2_c_02_audit_log_registra_inativacao_de_empresa(self):
        """
        T2.C-02 [Caminho Feliz] — Audit log registra inativação de empresa.
        Verifica se a inativação de um estabelecimento grava no log a ação ESTABELECIMENTO_INATIVADO
        com autor, entidade e identificador da empresa.
        """
        id_estabelecimento = "11111111-1111-4111-8111-111111111111"
        resposta = client.post(
            f"/estabelecimentos/{id_estabelecimento}/inativacao",
            json={"motivo_inativacao": "Encerramento das atividades em 10/2026"},
            headers=cabecalho_autenticacao("admin-token"),
        )
        assert resposta.status_code == 200
        logs = client.get("/auditoria", headers=cabecalho_autenticacao("admin-token")).json()["data"]
        assert any(
            registro["entidade"] == "ESTABELECIMENTO"
            and registro["acao"] == "ESTABELECIMENTO_INATIVADO"
            and registro["id_entidade"] == id_estabelecimento
            for registro in logs
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-08: Ausência do endpoint PATCH /usuarios/{id_usuario} impede a "
            "alteração de perfil de usuário e o consequente registro da mudança no Audit Log."
        ),
    )
    def test_t2_c_03_audit_log_registra_alteracao_de_perfil_de_usuario(self):
        """
        T2.C-03 [Caminho Feliz] — Audit log registra alteração de perfil de usuário.
        Verifica se a mudança de perfil de um usuário gera entrada de auditoria contendo o
        perfil anterior e o novo perfil atribuído.
        """
        client.patch("/usuarios/2", json={"perfil": "EDITOR"}, headers=cabecalho_autenticacao("admin-token"))
        logs = client.get("/auditoria", headers=cabecalho_autenticacao("admin-token")).json()["data"]
        assert any(
            registro["entidade"] == "USUARIO"
            and registro.get("antes", {}).get("perfil") == "GESTOR"
            and registro.get("depois", {}).get("perfil") == "EDITOR"
            for registro in logs
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-10: O endpoint GET /auditoria aceita filtragem por autor (id_usuario) "
            "e intervalo de datas, mas não implementa o filtro por estabelecimento/entidade (id_entidade) "
            "exigido pelo UC08."
        ),
    )
    def test_t2_c_04_consulta_ao_audit_log_com_filtros(self):
        """
        T2.C-04 [Caminho Feliz] — Consulta ao audit log com filtros.
        Verifica a filtragem de registros de auditoria por autor, período e estabelecimento.
        """
        headers_admin = cabecalho_autenticacao("admin-token")
        headers_editor = cabecalho_autenticacao("editor-token")

        client.post(
            "/pesquisas-ocupacao",
            json={
                "titulo": "Pesquisa Outubro",
                "tipo": "MENSAL",
                "periodo_inicio": "2026-10-01",
                "periodo_fim": "2026-10-31",
                "estabelecimentos": ["11111111-1111-4111-8111-111111111111"],
            },
            headers=headers_editor,
        )
        client.patch("/perfil", json={"nome": "Marina Admin Atualizada"}, headers=headers_admin)

        por_autor = client.get("/auditoria", params={"id_usuario": 3}, headers=headers_admin).json()["data"]
        assert len(por_autor) == 1
        assert por_autor[0]["id_usuario"] == 3

        por_periodo_valido = client.get(
            "/auditoria",
            params={
                "data_inicio": "2000-01-01T00:00:00+00:00",
                "data_fim": "2099-12-31T23:59:59+00:00",
            },
            headers=headers_admin,
        ).json()["data"]
        assert len(por_periodo_valido) == 2

        por_periodo_futuro = client.get(
            "/auditoria",
            params={"data_inicio": "2099-01-01T00:00:00+00:00"},
            headers=headers_admin,
        ).json()["data"]
        assert por_periodo_futuro == []

        por_entidade = client.get(
            "/auditoria",
            params={"id_entidade": "11111111-1111-4111-8111-111111111111"},
            headers=headers_admin,
        ).json()["data"]
        assert all(
            item["id_entidade"] == "11111111-1111-4111-8111-111111111111" for item in por_entidade
        )

    def test_t2_c_05_audit_log_nao_e_editavel_por_nenhum_perfil(self):
        """
        T2.C-05 [Exceção] — Audit log não é editável por nenhum perfil.
        Verifica que nenhuma conta (incluindo Administrador) dispõe de rotas HTTP de escrita,
        edição ou exclusão sobre os registros de auditoria.
        """
        headers_admin = cabecalho_autenticacao("admin-token")
        client.patch("/perfil", json={"nome": "Marina Teste Imutabilidade"}, headers=headers_admin)

        registros = client.get("/auditoria", headers=headers_admin).json()["data"]
        assert len(registros) == 1
        id_log = registros[0]["id"]

        for token in ("admin-token", "editor-token", "gestor-token"):
            headers = cabecalho_autenticacao(token)
            assert client.put("/auditoria", json={}, headers=headers).status_code == 405
            assert client.patch("/auditoria", json={}, headers=headers).status_code == 405
            assert client.delete("/auditoria", headers=headers).status_code == 405
            assert client.delete(f"/auditoria/{id_log}", headers=headers).status_code in {404, 405}

        registros_apos = client.get("/auditoria", headers=headers_admin).json()["data"]
        assert len(registros_apos) == 1
        assert registros_apos[0]["id"] == id_log

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-11 (Integridade Transacional): Em backend/app/main.py, a persistência "
            "em memória ocorre antes da chamada a audit() sem mecanismo de rollback. Caso a gravação "
            "do log falhe, a alteração de negócio permanece efetivada sem rastreabilidade, violando "
            "o fluxo alternativo 3a do UC03 e o requisito RNF-05."
        ),
    )
    def test_t2_c_06_falha_no_log_desfaz_a_operacao(self):
        """
        T2.C-06 [Exceção] — Falha no log desfaz a operação.
        Simula uma falha na função de gravação do log de auditoria durante o cadastro de um
        usuário e verifica se a operação principal é revertida (rollback).
        """
        headers_admin = cabecalho_autenticacao("admin-token")
        total_usuarios_antes = len(main_module.DEMO_USERS)

        with patch.object(
            main_module,
            "audit",
            side_effect=RuntimeError("Falha simulada na persistência do log de auditoria"),
        ):
            try:
                client.post(
                    "/usuarios",
                    json={"nome": "Usuário Sem Log", "email": "semlog@example.test", "perfil": "EDITOR"},
                    headers=headers_admin,
                )
            except RuntimeError:
                pass

        assert len(main_module.DEMO_USERS) == total_usuarios_antes
        assert "semlog@example.test" not in main_module.DEMO_USERS

    def test_t2_c_07_usuario_nao_coordenadora_nao_acessa_o_audit_log(self):
        """
        T2.C-07 [Exceção] — Perfis de Edição e Visualização não acessam o audit log.
        Verifica que usuários com perfil Editor e Visualização (GESTOR) recebem HTTP 403 Forbidden
        ao tentar consultar o endpoint /auditoria.
        """
        for token in ("editor-token", "gestor-token"):
            resposta = client.get("/auditoria", headers=cabecalho_autenticacao(token))
            assert resposta.status_code == 403


class TestGrupoT2DIsolamentoPainelEmpresario:
    """Cenários de validação para autenticação externa e isolamento de dados do Painel do Empresário (UC11)."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-12: O login por CNPJ e senha para contas do Painel do Empresário "
            "(UC11 / RF-08) e o filtro de isolamento por estabelecimento para o perfil HOTEL ainda "
            "não foram implementados em backend/app/main.py."
        ),
    )
    def test_t2_d_01_empresario_autentica_com_cnpj_e_senha_e_ve_apenas_seus_dados(self):
        """
        T2.D-01 [Caminho Feliz] — Empresário autentica com CNPJ e senha e vê apenas seus dados.
        Verifica se o responsável por um estabelecimento consegue autenticar-se informando CNPJ
        e senha e se a consulta subsequente retorna exclusivamente a ficha de sua empresa.
        """
        resposta = client.post(
            "/auth/login",
            json={"cnpj": "54.839.271/0001-64", "senha": "hotel-demo"},
        )
        assert resposta.status_code == 200
        token = resposta.json()["access_token"]

        estabelecimentos = client.get("/estabelecimentos", headers=cabecalho_autenticacao(token)).json()["data"]
        assert len(estabelecimentos) == 1
        assert estabelecimentos[0]["cnpj"] == "54.839.271/0001-64"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-12: Autenticação do Painel do Empresário e bloqueio de acesso para "
            "estabelecimentos com status INATIVO não implementados em backend/app/main.py."
        ),
    )
    def test_t2_d_02_login_do_empresario_com_empresa_inativa_e_bloqueado(self):
        """
        T2.D-02 [Exceção] — Login do empresário com empresa inativa é bloqueado.
        Verifica se a tentativa de acesso ao Painel do Empresário vinculada a um estabelecimento
        inativo (CNPJ 81.937.462/0001-31 — Hotel Vale do Sol) é negada.
        """
        resposta = client.post(
            "/painel-empresario/login",
            json={"cnpj": "81.937.462/0001-31", "senha": "hotel-inativo-senha"},
        )
        assert resposta.status_code in {401, 403}
        assert "error" in resposta.json()

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Não-conformidade NC-12: Ausência do endpoint de autenticação por CNPJ para o Painel do "
            "Empresário em backend/app/main.py."
        ),
    )
    def test_t2_d_03_mensagem_de_erro_nao_revela_qual_campo_esta_incorreto(self):
        """
        T2.D-03 [Exceção] — Mensagem de erro não revela qual campo está incorreto.
        Verifica se tentativas de login no Painel do Empresário com CNPJ não cadastrado ou com
        senha incorreta produzem exatamente a mesma mensagem genérica de erro, evitando a
        enumeração de CNPJs existentes na base.
        """
        tentativa_cnpj_invalido = client.post(
            "/painel-empresario/login",
            json={"cnpj": "00.000.000/0001-00", "senha": "qualquer-senha"},
        )
        tentativa_senha_invalida = client.post(
            "/painel-empresario/login",
            json={"cnpj": "54.839.271/0001-64", "senha": "senha-incorreta"},
        )
        assert tentativa_cnpj_invalido.status_code == 401
        assert tentativa_senha_invalida.status_code == 401
        assert (
            tentativa_cnpj_invalido.json()["error"]["message"]
            == tentativa_senha_invalida.json()["error"]["message"]
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Observação exploratória NC-13 / Pendência NC-12: O requisito de bloqueio após 5 "
            "tentativas inválidas (UC11 3c) refere-se ao login do empresário (não implementado, NC-12). "
            "Na sondagem do endpoint interno /auth/login, a 6ª tentativa com senha válida retorna HTTP 200."
        ),
    )
    def test_t2_d_04_bloqueio_temporario_apos_multiplas_tentativas_invalidas(self):
        """
        T2.D-04 [Exceção] — Bloqueio temporário após múltiplas tentativas inválidas.
        Verifica se cinco tentativas seguidas de autenticação com senha incorreta provocam o
        bloqueio temporário da conta, recusando inclusive credenciais válidas durante o período
        de bloqueio.
        """
        for _ in range(5):
            tentativa = client.post(
                "/auth/login",
                json={"email": "marina.admin@example.test", "senha": "senha-errada"},
            )
            assert tentativa.status_code == 401

        tentativa_durante_bloqueio = client.post(
            "/auth/login",
            json={"email": "marina.admin@example.test", "senha": "admin-demo"},
        )
        assert tentativa_durante_bloqueio.status_code in {423, 429}

