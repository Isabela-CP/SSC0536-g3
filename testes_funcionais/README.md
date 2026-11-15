# Testes funcionais — Inventário OTO

Suíte de **testes funcionais de sistema** (caixa-preta) do Inventário Turístico de Olímpia, em três
camadas que verificam os mesmos casos de uso (UC00–UC15):

| Camada | Pasta | O que exercita | Requer |
| --- | --- | --- | --- |
| **API** | `testes_funcionais/` | Regras de negócio, perfis, auditoria, transações (banco PostgreSQL novo por teste) | PostgreSQL de testes |
| **Stack** | `testes_funcionais/e2e/` | Nginx (proxy, limites, cabeçalhos), worker SMTP e e-mail real no Mailpit | Stack Docker do projeto |
| **Interface** | `testes_funcionais/e2e/` | Telas no navegador: menus por perfil, formulários, diálogos, tablet | Stack Docker + Playwright |

Relatório completo (planejamento, execução, resultados e capturas de tela):
[`docs/relatorio_testes_funcionais.pdf`](docs/relatorio_testes_funcionais.pdf).

## Resultado da última execução

Build `b9b1865` (`origin/Develop`), 14/11/2026. A API rodou na mesma configuração do CI
(Python 3.11 + PostgreSQL 17); a interface, no Chromium 131.

| Camada | Casos | Aprovados | Defeitos (DF) | Não implementados (NI) | Saída do pytest |
| --- | ---: | ---: | ---: | ---: | --- |
| API | 188 | 170 | 10 | 8 | `170 passed, 18 xfailed` |
| Stack + Interface | 31 | 30 | 1 | 0 | `30 passed, 1 xfailed` |
| **Total** | **219** | **200** | **11** | **8** | 126 cenários |

Também foram executados: a regressão do backend (`254 passed`), o smoke de persistência do time
(`stack_smoke.py`, com reinício dos serviços conferido) e a consulta ao CI do GitHub. Evidências em
[`evidencias/`](evidencias/).

### Defeitos encontrados

| Código | Severidade | Caso de uso | Descrição |
| --- | --- | --- | --- |
| DF-01 | Alta | UC11 3c | Sem limite de tentativas de login (força bruta) |
| DF-05 | Alta | UC11 3b | Empresário de empresa **inativa** continua entrando e editando a ficha |
| DF-04 | Média | UC11 | Empresário entra com e-mail, não com CNPJ e senha |
| DF-06 | Média | UC13 2a | Permite duas pesquisas do mesmo tipo e período |
| DF-07 | Média | UC14 3a | Resposta enviada não pode ser corrigida com a pesquisa aberta (a tela avisa: "não poderá ser reenviada") |
| DF-08 | Média | UC15 *a | Relatório omite participantes "sem resposta" |
| DF-02 | Baixa | UC01 5b | 409 de CNPJ duplicado não indica o registro existente |
| DF-03 | Baixa | UC04 | Motivo de inativação só com espaços é aceito |
| DF-09 | Baixa | UC15 3a | Pesquisa sem respostas gera relatório vazio, sem aviso |
| DF-10 | Baixa | UC05 3a | Busca sem resultados (tela) não sugere limpar os filtros |

### Requisitos sem funcionalidade

NI-01 filtro por nº de leitos · NI-02 filtro do log por empresa · NI-03 alterar perfil de conta
existente · NI-04 relatório por período/categoria · NI-05 "empresas cadastradas no mês" ·
NI-06 importação Excel (UC06) · NI-07 backup/restauração (UC09, UC10) · NI-08 exportar a lista de
estabelecimentos (PDF/Excel). Sem funcionalidade não há comportamento a testar: esses testes
comprovam a ausência no contrato da API e devem virar cenários de comportamento quando ela existir.

### Observações (não são defeitos do sistema)

- **OBS-01:** `backend/tests/stack_smoke.py` reinicia com `docker compose restart` sem informar o
  projeto; em stack com outro nome o reinício não ocorre e a checagem passa sem ser feita. Rode com
  `COMPOSE_PROJECT_NAME=<projeto>`.
- **OBS-02:** o CI do PR #39 falhou sem criar jobs (falha de inicialização); o push na `main`, com a
  mesma árvore, passou nos três jobs.

## Como executar

### Camada de API

Requer um PostgreSQL **de testes** cujo usuário possa criar bancos. A suíte cria `oto_func_modelo_*`
(migrations + seed) e um clone `oto_func_*` por teste, e remove todos. **Nunca aponte para dados reais.**

```bash
# a partir da raiz do repositório
python -m venv backend/.venv && source backend/.venv/bin/activate
pip install -r backend/requirements.txt

docker run -d --name oto-pg-testes -e POSTGRES_HOST_AUTH_METHOD=trust \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
export OTO_TEST_ADMIN_URL=postgresql://postgres@127.0.0.1:55432/postgres

pytest testes_funcionais --ignore=testes_funcionais/e2e -v -rxX
```

Sem `OTO_TEST_ADMIN_URL`, a coleta **falha com erro** em vez de pular: sem banco real o resultado não
seria um teste funcional válido.

### Camadas de stack e interface

Use uma stack **descartável** (os testes criam dados com nomes e CNPJs únicos). O arquivo
[`e2e/stack-qa.env`](e2e/stack-qa.env) usa portas próprias (8091 e 8026), só no loopback.

```bash
docker compose -p oto-qa --env-file testes_funcionais/e2e/stack-qa.env up -d --build --wait
docker build -t oto-qa-playwright testes_funcionais/e2e          # Playwright 1.49.1 + Chromium

docker run --rm --network host -v "$PWD":/src:ro -w /src \
  -e OTO_STACK_URL=http://localhost:8091 -e OTO_MAILPIT_URL=http://localhost:8026 \
  -e OTO_E2E_CAPTURAS=/src/capturas oto-qa-playwright \
  python3 -m pytest testes_funcionais/e2e -v -rxX

# smoke de persistência do time, apontando para o projeto certo
COMPOSE_PROJECT_NAME=oto-qa OTO_STACK_URL=http://localhost:8091 python backend/tests/stack_smoke.py

docker compose -p oto-qa down --volumes                         # apaga a stack de teste
```

Sem `OTO_STACK_URL`, os testes de `e2e/` são pulados com o motivo indicado (camada opcional).
Para salvar capturas, monte um diretório gravável em `OTO_E2E_CAPTURAS`.

### Comandos úteis

```bash
pytest testes_funcionais -m defeito -rx               # só os defeitos
pytest testes_funcionais --runxfail --tb=line         # falha real de cada xfail
python testes_funcionais/docs/gerar_relatorio.py      # regenera o PDF a partir de evidencias/
```

## Organização

| Arquivo | Casos de uso | Conteúdo |
| --- | --- | --- |
| `conftest.py`, `apoio_api.py` | — | Fixtures (banco descartável por teste, login por perfil, fila de e-mails) e massa de dados |
| `test_01_autenticacao.py` | UC00 | Login, sessão, logout, expiração, tentativas |
| `test_02_cadastro_estabelecimentos.py` | UC01, UC02 | Cadastro, validação, CNPJ, edição e campos protegidos |
| `test_03_inativacao_e_busca.py` | UC04, UC05 | Inativação/reativação, limites do motivo, busca e filtros |
| `test_04_auditoria.py` | UC03, UC08 | Registro, filtros, imutabilidade e atomicidade do log |
| `test_05_contas_e_perfis.py` | UC07 | Contas, convites, senhas, último administrador |
| `test_06_painel_empresario.py` | UC11, UC12 | Isolamento do empresário, edição da própria ficha |
| `test_07_pesquisas_ocupacao.py` | UC13, UC14 | Criação, encerramento e respostas de pesquisas |
| `test_08_relatorios_e_painel.py` | UC15, Home | Relatório CSV/PDF e totalizadores |
| `test_09_documentos_e_requisitos_ausentes.py` | UC02, UC06, UC09, UC10 | Documentos e requisitos sem funcionalidade |
| `e2e/test_e2e_01_stack.py` | RNF-01, UC00, UC02, UC07 | Nginx, limites de upload, convite e recuperação por e-mail real |
| `e2e/test_e2e_02_interface.py` | UC00–UC14, RNF-01 | Telas: menus, cadastro, cancelamento, inativação, busca, pesquisas, tablet |
| `e2e/apoio.py`, `e2e/conftest.py` | — | Cliente da stack, Mailpit, navegador e capturas de tela |
| `e2e/Dockerfile`, `e2e/stack-qa.env` | — | Imagem do Playwright e ambiente da stack de teste |
| `docs/` | — | Relatório em PDF e o script que o gera |
| `evidencias/` | — | Saídas do pytest, JUnit XML, ambiente, CI, smoke e capturas |

## Convenções

- **Nomes:** `test_ft_<grupo>_<nn>_<descrição>`; o ID do cenário (ex.: `FT-UI-09`) vem do nome.
- **Oráculo:** o resultado esperado vem do caso de uso ou do contrato OpenAPI, nunca do
  comportamento atual. Quando o time decidiu diferente do caso de uso e documentou (ex.: só o
  ADMINISTRADOR cadastra empresas), vale a decisão documentada.
- **Defeitos:** `@defeito("DF-xx", motivo)` e `@nao_implementado("NI-xx", motivo)` aplicam
  `xfail(strict=True)`. Quando o problema for corrigido, o teste dá **XPASS** e a suíte falha de
  propósito: remova o marcador e o teste vira regressão.
- **Marcadores:** `uc(...)` liga cada teste aos casos de uso; os códigos vão para o JUnit XML.
- **Interface:** seletores por papel e rótulo acessível (como um leitor de tela), nunca por CSS;
  o resultado é conferido também na API quando a tela não mostra o estado final.
