# QA — Sistema de Inventário Turístico de Olímpia (OTO)

Esta pasta reúne a validação de QA das duas tarefas da Sprint:

| Tarefa | Script |
| :--- | :--- |
| `[QA] Validar as funcionalidades de gestão dos estabelecimentos` | [`test_gestao_estabelecimentos.py`](test_gestao_estabelecimentos.py) |
| `[QA] Validar segurança, permissões e rastreabilidade` | [`test_seguranca_permissoes_rastreabilidade.py`](test_seguranca_permissoes_rastreabilidade.py) |

Os testes foram executados contra a implementação atual do backend (`backend/app/main.py`), alinhada ao contrato OpenAPI (`contratos_api_oto/openapi.json`) e aos protótipos de interface, sem modificar nenhum código da aplicação. Cada teste possui um identificador rastreável (`T1.A-01`, `T2.C-04` etc.) referenciado neste documento e no código dos testes.

## 1. Resumo da execução

| Tarefa | Cenários | PASS | FAIL | Não implementado | BLOCKED | Pendente / a revisar |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Gestão dos estabelecimentos (T1) | 16 | 13 | 0 | 0 | 2 | 1 |
| Segurança, permissões e rastreabilidade (T2) | 19 | 9 | 3 | 6 | 0 | 1 |
| **Total** | **35** | **22** | **3** | **6** | **2** | **2** |

Como cada resultado aparece no `pytest`: **22 `passed`**, **2 `skipped`** e **11 `xfailed`** (3 FAIL + 6 não implementado + 2 pendentes).

**Significado das classificações**

| Classificação | Quando é usada |
| :--- | :--- |
| **PASS** | O teste executou e o comportamento atende plenamente ao critério de aceite e ao contrato. |
| **FAIL** | O teste executou a rota implementada, mas o comportamento diverge do requisito de negócio. |
| **Não implementado** | A rota necessária ainda não existe no backend (`404`/`405`). O critério de aceite não pôde ser avaliado na prática. |
| **BLOCKED** | O cenário depende da interface gráfica (`frontend/src/App.jsx`), que ainda não possui as telas construídas. |
| **Pendente / a revisar** | O resultado depende de definição de escopo (T1.A-02) ou de requisito que não se aplica ao endpoint executado (T2.D-04). Não entra na contagem de falhas confirmadas. |

**Principais conclusões**

- **Gestão de Estabelecimentos (Task 1):** O ciclo completo de cadastro (`POST /estabelecimentos`), edição parcial (`PATCH`), inativação com justificativa (`POST .../inativacao`), reativação e consultas com filtros combinados está **totalmente funcional e aprovado**. As mutações cadastrais são restritas com sucesso ao perfil `ADMINISTRADOR`, e tentativas de criação por `EDITOR` (estagiário) e `GESTOR` recebem `403 Forbidden`, confirmando a modelagem dos protótipos.
- **Rastreabilidade e Auditoria (Task 2):** As criações e inativações de estabelecimentos agora são devidamente registradas no log de auditoria com autor, data/hora e identificadores (`T2.C-01` e `T2.C-02` passam). O audit log é protegido contra alterações (`T2.C-05`) e contra acesso de usuários não autorizados (`T2.C-07`).
- **Segurança da API:** Os endpoints de leitura do inventário exigem autenticação obrigatória via Bearer Token, retornando `401 Unauthorized` para requisições anônimas (`T2.A-04` passa).
- **Defeitos confirmados na execução (FAIL):**
  1. Falha de login para usuários recém-criados e ativados via convite (`HTTP 500` / `StopIteration` em `main.py`, linha 202 - NC-07).
  2. O endpoint `/auditoria` ignora a filtragem por empresa (`id_entidade`), devolvendo todos os registros (NC-10).
  3. Falha simulada na gravação do log de auditoria não realiza rollback da entidade em memória (NC-11).
- **Funcionalidades pendentes de desenvolvimento:** Gestão administrativa de usuários (`PATCH|DELETE /usuarios/{id}`) e o Painel do Empresário (login por CNPJ e isolamento).

## 2. Como os testes foram feitos

**Testes automatizados de API.** Desenvolvidos com `pytest` e `TestClient` (FastAPI/Starlette). Para assegurar isolamento completo entre os testes, a fixture `resetar_estado_em_memoria` (`autouse`) restaura as coleções (`DEMO_USERS`, `TOKENS`, `INVITES`, `AUDIT_LOG` etc.) e reinicializa a instância do repositório de estabelecimentos (`MemoryInventoryRepository`) a partir do `seed-data.json` antes de cada execução.

**Por que testar a API e não a interface.** O frontend ainda não possui telas completas. A API concentra as regras de negócio, autorização por perfil e auditoria (*Shift-Left Testing*). Cenários que dependem estritamente de componentes visuais (cancelamento em modal ou formulário) foram marcados como `BLOCKED` (`@pytest.mark.skip`).

**Inspeção estática.** Apenas o teste `T1.B-04` inspeciona diretamente o `openapi.json` dentro do teste para verificar a ausência de métodos `DELETE` sobre estabelecimentos. As demais análises estáticas referem-se a itens de documentação comparados na Seção 5.

**Como as falhas conhecidas são registradas.** Cenários que falham ou que aguardam implementação utilizam `@pytest.mark.xfail(strict=True, reason="...")`:
- `XFAIL`: falhou conforme a não conformidade documentada.
- `XPASS` com `strict=True`: o teste passou inesperadamente, gerando falha no pytest para sinalizar que o item foi corrigido e que a marcação deve ser removida.

**Decisões e premissas de teste.** Quando um caso de uso descreve uma regra em texto mas o contrato ainda não detalha o comportamento técnico da rota, adotei convenções para viabilizar a automação:
- **Códigos de status HTTP:** para cenários sem especificação exata no contrato, os testes aceitam códigos padronizados para o caso (`423` ou `429` para bloqueio de login por tentativas em T2.D-04; `401` ou `403` para empresa inativa em T2.D-02; `400`, `409` ou `422` para proteção do último administrador em T2.B-03).
- **Rotas de usuários e empresário:** como o contrato ainda não define endpoints de edição/exclusão de usuários nem login específico de empresário por CNPJ, utilizei rotas REST convencionais (`PATCH|DELETE /usuarios/{id}` e `/painel-empresario/login`) até que a equipe formalize essas operações.
- **Credencial de teste de empresário:** utilizei a senha fictícia `hotel-demo` em T2.D-01 porque o arquivo de seed não traz senhas cadastradas para as contas de empresários.

## 3. Dados e perfis

Os testes utilizam as contas e entidades do seed oficial do projeto:

| Conta / token | Perfil na API | Papel no Inventário |
| :--- | :--- | :--- |
| `marina.admin@example.test` / `admin-token` | `ADMINISTRADOR` | Administrador com permissão total (cadastro, inativação, auditoria, usuários). |
| `camila.editora@example.test` / `editor-token` | `EDITOR` | Estagiária / Operação (leitura de dados e pesquisas, sem mutação cadastral de hotéis). |
| `rafael.consulta@example.test` / `gestor-token` | `GESTOR` | Usuário exclusivo de consulta e emissão de relatórios. |
| `contas_empresario` (Hotel Serra Azul, CNPJ `54.839.271/0001-64`) | `HOTEL` | Responsável pelo estabelecimento (Painel do Empresário). |

Estabelecimentos de referência: Hotel Serra Azul (`11111111-…`, ativo), Pousada Ipê Amarelo (`22222222-…`, ativa), Hotel Vale do Sol (`33333333-…`, **inativo**) e Hospedagem em Cadastro (`44444444-…`, ativa).

## 4. Resultados detalhados

### 4.1 Gestão dos estabelecimentos (`UC01`, `UC02`, `UC04`, `UC05`)

| ID | Cenário | Referência | Resultado | Evidência |
| :--- | :--- | :--- | :---: | :--- |
| T1.A-01 | Cadastro completo de hospedagem (Happy Path) | UC01, UC02 / RF-01, RF-02 | **PASS** | `POST /estabelecimentos` com `admin-token` cria hotel com status `ATIVO` e retorna `201`. |
| T1.A-02 | Cadastro de Alimentação e Bebidas (Happy Path) | UC01, UC02 | Pendente (escopo) | `GET /categorias-estabelecimento` expõe apenas categoria 1 (Hospedagem). Aguarda definição do PO (NC-02). |
| T1.A-03 | Cancelar cadastro não grava dados (Happy Path) | UC01 4a | BLOCKED | Depende do formulário na interface gráfica. |
| T1.A-04 | Obrigatório ausente (Edge Case) | UC01 5a / RF-01 | **PASS** | `POST /estabelecimentos` sem nome fantasia retorna `422 VALIDATION_ERROR`. |
| T1.A-05 | CNPJ duplicado (Edge Case) | UC01 5b / RF-01 | **PASS** | Tentativa de cadastrar CNPJ existente retorna `409 CONFLICT`. |
| T1.A-06 | Texto em campo numérico (Edge Case) | UC02 4a / RF-02 | **PASS** | `total_uh="abc"` é rejeitado com `422 VALIDATION_ERROR`. |
| T1.A-07 | Usuários sem perfil admin não cadastram (Edge Case) | UC00 4a, UC01 / RF-06 | **PASS** | `gestor-token` e `editor-token` (estagiário) recebem `403 Forbidden` ao tentar cadastrar. |
| T1.A-08 | Edição parcial de dados do estabelecimento (Happy Path) | UC02 / RF-01, RF-02 | **PASS** | `PATCH /estabelecimentos/{id}` com `admin-token` atualiza UHs e telefone com `200`. |
| T1.B-01 | Inativar empresa com motivo (Happy Path) | UC04 / RF-04 | **PASS** | `POST .../inativacao` altera status para `INATIVO` e grava motivo com `200`. |
| T1.B-02 | Cancelar inativação mantém status (Happy Path) | UC04 3a | BLOCKED | Depende do diálogo de confirmação na interface gráfica. |
| T1.B-03 | Inativar empresa já inativa e fluxo de reativação (Edge Case) | UC04 5a / RF-04 | **PASS** | Inativação duplicada retorna `409 ESTABELECIMENTO_JA_INATIVO`; `/reativacao` restaura para `ATIVO` com `200`. |
| T1.B-04 | Sem exclusão definitiva (Edge Case) | UC04 *a / RF-04, RNF-05 | **PASS** | Rota `DELETE /estabelecimentos/{id}` inexistente no contrato (`405 Method Not Allowed`). |
| T1.C-01 | Busca por nome (Happy Path) | UC05 / RF-05 | **PASS** | `busca=Hotel Serra Azul` retorna `200` e total de 1 registro. |
| T1.C-02 | Filtro categoria + status (Happy Path) | UC05 / RF-05 | **PASS** | `id_categoria=1&status=ATIVO` retorna exatamente 3 hotéis ativos. |
| T1.C-03 | Limpar filtros restaura a lista (Happy Path) | UC05 2a / RF-05 | **PASS** | Consulta sem filtros restaura a totalidade de 4 estabelecimentos. |
| T1.C-04 | Busca sem resultados retorna coleção vazia (Edge Case) | UC05 3a / RF-05 | **PASS** | Busca por termo inexistente retorna `200`, `data: []` e `total: 0`. |

### 4.2 Segurança, permissões e rastreabilidade (`UC00`, `UC03`, `UC07`, `UC08`, `UC11`)

| ID | Cenário | Referência | Resultado | Evidência |
| :--- | :--- | :--- | :---: | :--- |
| T2.A-01 | Login e perfil correto (Happy Path) | UC00 / RF-06, RNF-01 | **PASS** | Login do `EDITOR` retorna `200`, token e bloqueia acesso a rotas administrativas (`403`). |
| T2.A-02 | Senha incorreta (Edge Case) | UC00 3a / RF-06 | **PASS** | `401 INVALID_CREDENTIALS` com mensagem genérica anti-enumeração de contas. |
| T2.A-03 | Perfil de consulta sem acesso a escrita (Edge Case) | UC00 4a / RNF-02 | **PASS** | `gestor-token` recebe `403` em rotas de criação de pesquisas, usuários e convites. |
| T2.A-04 | Acesso sem autenticação exige login (Edge Case) | UC00, UC05 / RF-06 | **PASS** | Rotas internas e de estabelecimentos retornam `401 Unauthorized` sem token. |
| T2.B-01 | Admin cria usuário Editor (Happy Path) | UC07 / RF-06, RF-07 | **FAIL** | Usuário é criado (`201`) e ativado por convite, mas o login subsequente falha com `500` (NC-07). |
| T2.B-02 | Admin altera perfil (Happy Path) | UC07 / RF-07 | Não implementado | Rota `PATCH /usuarios/{id}` retorna `404` (NC-08). |
| T2.B-03 | Bloqueio do último administrador (Edge Case) | UC07 3a / RF-07 | Não implementado | Rota `DELETE /usuarios/1` retorna `404`; regra ainda não verificável (NC-09). |
| T2.B-04 | Não-admin sem gestão de usuários (Edge Case) | UC07 / RNF-02 | **PASS** | `EDITOR` recebe `403` ao tentar listar ou cadastrar usuários. |
| T2.C-01 | Audit log registra criação de empresa (Happy Path) | UC03, UC08 / RF-03 | **PASS** | Criação de hotel por admin gera evento `ESTABELECIMENTO_CRIADO` no log de auditoria. |
| T2.C-02 | Audit log registra inativação de empresa (Happy Path) | UC03, UC08 / RF-03, RNF-05 | **PASS** | Inativação de hotel gera evento `ESTABELECIMENTO_INATIVADO` no log de auditoria. |
| T2.C-03 | Audit log registra troca de perfil (Happy Path) | UC03, UC07 / RF-03 | Não implementado | Depende da implementação de `PATCH /usuarios/{id}` (NC-08). |
| T2.C-04 | Consulta ao audit log com filtros (Happy Path) | UC08 / RF-03 | **FAIL** | Filtros por autor e período funcionam, mas o filtro por empresa (`id_entidade`) é ignorado pela API (NC-10). |
| T2.C-05 | Audit log não editável (Edge Case) | UC03 / RF-03, RNF-05 | **PASS** | Métodos `PUT`, `PATCH` e `DELETE` em `/auditoria` retornam `405`. |
| T2.C-06 | Falha no log desfaz a operação (Edge Case) | UC03 3a / RNF-05 | **FAIL** | Com falha simulada em `audit()`, a entidade permanece gravada em memória sem rollback (NC-11). |
| T2.C-07 | Usuários sem permissão não acessam audit log (Edge Case) | UC08 / RF-03 | **PASS** | `EDITOR` e `GESTOR` recebem `403` em `GET /auditoria`. |
| T2.D-01 | Empresário autentica via CNPJ e vê seus dados (Happy Path) | UC11 / RF-08 | Não implementado | Rota de login por CNPJ e isolamento de hotel não implementados (NC-12). |
| T2.D-02 | Empresa inativa bloqueada no login (Edge Case) | UC11 3b / RF-08 | Não implementado | Depende da implementação do login de empresário (NC-12). |
| T2.D-03 | Mensagem de erro neutra no login de empresário (Edge Case) | UC11 3a / RF-08 | Não implementado | Depende da implementação do login de empresário (NC-12). |
| T2.D-04 | Bloqueio temporário após tentativas inválidas (Edge Case) | UC11 3c / RF-08 | Pendente (exploratório) | A sondagem de `/auth/login` aceita tentativas ilimitadas. O requisito de lockout aplica-se ao login de empresário (NC-12 e NC-13). |

## 5. Não conformidades e divergências de especificação

| Cód. | Severidade | Referência | Status | Descrição e recomendação |
| :---: | :---: | :--- | :---: | :--- |
| **NC-01 / NC-04** | Resolvida | UC01, UC04 / RF-01, RF-04 | **Implementado no backend** | Rotas de cadastro (`POST /estabelecimentos`), edição (`PATCH`) e inativação/reativação foram entregues no PR #34 e estão plenamente validadas na Task 1. |
| **NC-02** | A decidir (PO) | UC01 / HU-01 | Pendência de Escopo | O documento de Casos de Uso lista 7 categorias turísticas, enquanto o MVP cobre exclusivamente "Meios de Hospedagem" (categoria 1). Recomenda-se formalizar o recorte e alinhar os documentos. |
| **NC-03** | Média | UC01 5b | Estática (mock) | O exemplo de conflito 409 no contrato informa a mensagem de duplicidade, mas não o ID do registro existente para redirecionamento. Sugere-se incluir o ID na resposta. |
| **NC-06** | Resolvida | UC00, UC05 / RF-06 | **Protegido** | As rotas de inventário e categorias agora exigem autenticação obrigatória (`401` sem token). |
| **NC-07** | Alta | UC07 / RF-06, RF-07 | **FAIL (Ativa)** | Usuários criados e ativados via convite geram `StopIteration` no login (`backend/app/main.py:202`) porque a geração de token dinâmico não está implementada. |
| **NC-08 / NC-09** | Alta | UC07 / RF-07 | **Não implementado** | Ausência das rotas `PATCH` e `DELETE /usuarios/{id}`. Regra de proteção do último administrador ainda não pôde ser exercitada. |
| **NC-10** | Média | UC08 / RF-03 | **FAIL (Ativa)** | O endpoint `GET /auditoria` ignora o parâmetro `id_entidade`, impossibilitando a filtragem de histórico por estabelecimento. |
| **NC-11** | Alta | UC03 3a / RNF-05 | **FAIL (Ativa)** | Em caso de falha de gravação no log de auditoria, a mutação de dados não é revertida em memória. Reavaliar transacionalidade quando o banco de dados for integrado. |
| **NC-12 / NC-13** | Alta | UC11 / RF-08 | **Não implementado** | Ausência de endpoint para autenticação de empresários via CNPJ e senha e de trava de tentativas inválidas. |
| **NC-14** | Esclarecida | UC01, UC04 / Personas | **Alinhada aos Protótipos** | Os Casos de Uso originais citavam a Estagiária como executora de cadastro e inativação. Conforme definido nos protótipos de interface e no OpenAPI, estagiários possuem perfil estritamente de visualização/relatórios (`EDITOR`/`GESTOR`), ficando a mutação restrita a `ADMINISTRADOR`. Os Casos de Uso devem ser atualizados pela equipe. |

## 6. Próximos passos para a equipe

1. **PO / Gestão de Requisitos:** atualizar o documento de Casos de Uso (UC01 e UC04) para formalizar que estagiários possuem apenas acesso de consulta/relatórios (conforme protótipos e contrato OpenAPI) e formalizar o escopo de categorias do MVP (NC-02).
2. **Backend:**
   - Corrigir a emissão de token no login para contas criadas via convite (NC-07).
   - Implementar o filtro por empresa (`id_entidade`) na rota `/auditoria` (NC-10).
   - Definir no contrato OpenAPI e implementar as rotas de alteração/exclusão de usuários (NC-08) e de autenticação do empresário via CNPJ (NC-12).
3. **Persistência / Banco de Dados:** implementar rollback transacional das operações quando a gravação do log de auditoria falhar (NC-11).
4. **Frontend:** implementar os formulários e diálogos para liberar a validação dos cenários pendentes de interface gráfica (T1.A-03 e T1.B-02).

## 7. Como executar

Comandos a partir da raiz do repositório:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r testes/requirements.txt
```

```bash
# Executar a suíte completa de testes
pytest testes/ -v -rxXs

# Executar apenas a Tarefa 1 (Gestão dos estabelecimentos)
pytest testes/test_gestao_estabelecimentos.py -v -rxXs

# Executar apenas a Tarefa 2 (Segurança, permissões e rastreabilidade)
pytest testes/test_seguranca_permissoes_rastreabilidade.py -v -rxXs

# Executar ignorando xfail para inspecionar as falhas reais
pytest testes/ -v --runxfail
```

Resultado atual da suíte completa: **`22 passed, 2 skipped, 11 xfailed`**.
