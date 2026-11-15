# Testes de integração e regressão — Inventário OTO

Esta suíte verifica duas coisas:

- **Integração:** se os componentes funcionam juntos, inclusive quando um deles falha. Os componentes são o frontend, a API,
  o PostgreSQL, o storage, a fila de e-mail e os contêineres.
- **Regressão:** se a última entrega, o PR #39 (preparo para hospedagem gratuita), não quebrou o que já funcionava.

| Camada | Pasta | O que exercita | Requer |
| --- | --- | --- | --- |
| **Integração em processo** | `integracao/` | API real + PostgreSQL real + SMTP real (Mailpit) + disco + código do frontend em Node; falhas injetadas | PostgreSQL e Mailpit de testes, Node 20 com `frontend/node_modules` |
| **Integração da stack** | `stack/` | Contêineres do `compose.yaml` (Nginx, API, worker, banco, Mailpit, volumes) reiniciados, parados e recriados | Stack Docker descartável |
| **Regressão** | `regressao/` | Todas as suítes do projeto na build atual; comparação, caso a caso, entre a versão anterior e a atual | Imagem `oto-qa-regressao` (Python 3.11 + Node 20, igual ao CI) |

O relatório completo, com planejamento, execução, resultados e capturas de tela, está em
[`docs/relatorio_integracao_regressao.pdf`](docs/relatorio_integracao_regressao.pdf).

## Resultado da última execução

Build `b9b1865` (`origin/Develop`, igual à `main`), 14/11/2026. Versão de referência para a regressão: `a81a719`
(merge do PR #38, antes do PR #39).

### Integração

| Área | Interfaces | Casos | Aprovados | Defeitos |
| --- | --- | ---: | ---: | --- |
| API e PostgreSQL | I3, I7 | 17 | 17 | – |
| Outbox, dispatcher e e-mail | I5, I6 | 10 | 10 | – |
| Armazenamento de arquivos (local e Supabase) | I4 | 28 | 26 | DF-11 |
| Frontend e API | I2 | 8 | 8 | – |
| Publicação e inicialização | I2, I7 | 18 | 18 | – |
| Stack Docker | I1, I8 | 6 | 5 | DF-12 |
| **Total** | | **87** | **84** | **2 defeitos novos** |

### Defeitos encontrados

| Código | Severidade | Interface | Descrição |
| --- | --- | --- | --- |
| DF-12 | Média | Dispatcher ↔ SMTP/Brevo | O dispatcher tenta de novo 1 s depois de cada falha. Uma queda de cerca de 10 s do servidor de e-mail esgota as 10 tentativas, e o convite ou a recuperação nunca chega, nem depois que o servidor volta. A conta fica Pendente, sem aviso. O defeito já existia em `a81a719`. |
| DF-11 | Baixa | API ↔ storage | O download de um documento do seed responde 500, e a tela mostra “Não foi possível acessar o serviço”. O backend promete 404. Causa: `caminho_storage` fora do formato UUID gera `ValueError`, que não é tratado como no download de relatórios. |

A numeração continua a da sprint funcional (DF-01 a DF-10, em [`../testes_funcionais/`](../testes_funcionais/)).

### Regressão

| Parte | O que foi feito | Resultado |
| --- | --- | --- |
| RG-1 | Todas as suítes na build atual | backend 254 ✓ · frontend 133 ✓ · funcionais API 170 ✓ + 18 esperados · funcionais e2e 30 ✓ + 1 esperado · integração 84 ✓ + 3 esperados (**693 casos**) |
| RG-2 | `a81a719` × `b9b1865`, caso a caso | 367 casos comparados (funcionais, integração sem recursos novos, frontend): **0 mudanças, 0 regressões** |
| RG-3 | Testes do time de `a81a719` sobre o código atual | backend 242/243, frontend 132/132. A única falha é intencional: o teste espera 3 migrations, e o PR #39 incluiu a 004; o próprio time atualizou a asserção para 4 |
| RG-4 | Reteste dos defeitos | DF-01 a DF-12 continuam reproduzindo; DF-01 a DF-09 e DF-11 já existiam antes do PR #39 |
| RG-5 | Estabilidade | 3 execuções seguidas da integração com resultados idênticos (nenhum teste instável) |

As evidências estão em [`evidencias/`](evidencias/): JUnit XML e saída de cada suíte, comparações, `--runxfail` e capturas.

## Como executar

Todos os comandos rodam a partir da raiz do repositório. Use **somente** serviços de teste descartáveis: a suíte cria e apaga
bancos `oto_int_*` e esvazia a caixa do Mailpit.

### Integração em processo

```bash
docker run -d --name oto-int-pg -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55433:5432 postgres:17-alpine
docker run -d --name oto-int-mailpit -p 127.0.0.1:18025:8025 -p 127.0.0.1:11025:1025 axllent/mailpit:v1.27
(cd frontend && npm ci)                       # o teste do frontend carrega frontend/src pelo Vite

export OTO_TEST_ADMIN_URL=postgresql://postgres@127.0.0.1:55433/postgres
export OTO_TEST_MAILPIT_URL=http://127.0.0.1:18025 OTO_TEST_SMTP=127.0.0.1:11025
pytest testes_integracao_regressao/integracao -v -rxX
```

Sem essas variáveis, a coleta **falha com erro** em vez de pular, porque integração não se simula. `OTO_TEST_NODE`
escolhe o executável do Node (padrão: `node`).

### Integração da stack

```bash
docker compose -p oto-int --env-file testes_integracao_regressao/stack/stack-int.env up -d --build --wait
OTO_STACK_URL=http://localhost:8092 OTO_STACK_MAILPIT=http://localhost:8027 \
  pytest testes_integracao_regressao/stack -v -rxX           # para, reinicia e recria serviços do projeto oto-int

# capturas de tela (imagem do Playwright de testes_funcionais/e2e)
docker run --rm --network host -v "$PWD":/src -w /src -e OTO_STACK_URL=http://localhost:8092 \
  -e OTO_STACK_MAILPIT=http://localhost:8027 -e OTO_CAPTURAS=/src/testes_integracao_regressao/evidencias/capturas \
  oto-qa-playwright python3 testes_integracao_regressao/stack/capturas.py normal

docker compose -p oto-int down --volumes
```

Os cenários só agem sobre o projeto informado em `OTO_STACK_PROJETO` (padrão `oto-int`). Nunca aponte para uma stack em uso.

### Regressão

```bash
docker build -t oto-qa-regressao -f testes_integracao_regressao/Dockerfile .

# todas as suítes de uma árvore de código (a de trabalho ou um `git archive <commit>` com as suítes de QA copiadas)
docker run --rm --network host -v "$PWD":/src -w /src \
  -e OTO_TEST_ADMIN_URL=... -e OTO_TEST_MAILPIT_URL=... -e OTO_TEST_SMTP=... \
  oto-qa-regressao bash testes_integracao_regressao/regressao/executar_suites.sh /src /src/saida [--sem-hospedagem]

# comparação caso a caso (sai com código 1 se algum caso aprovado passou a falhar)
python testes_integracao_regressao/regressao/comparar_execucoes.py base/funcionais.xml atual/funcionais.xml
```

`--sem-hospedagem` exclui os testes de recursos criados no PR #39 (marcador `hospedagem`), que não existem nas versões
anteriores.

### Relatório

```bash
python testes_integracao_regressao/docs/gerar_relatorio.py   # regenera o PDF a partir de evidencias/
```

## Organização

| Arquivo | Conteúdo |
| --- | --- |
| `conftest.py`, `apoio.py` | Banco exclusivo por teste, Mailpit, uvicorn real, dublês do Supabase Storage e do Brevo, proxy TCP do banco |
| `integracao/test_int_01_banco.py` | Migrations, seed, papel restrito, RLS, queda do banco, concorrência, sessão |
| `integracao/test_int_02_email.py` | Outbox na mesma transação, SMTP real, retentativa, limite, dispatchers concorrentes, dispatcher embutido, Brevo |
| `integracao/test_int_03_armazenamento.py` | Envio, download, substituição, arquivos órfãos, limites e relatórios, nos provedores local e Supabase |
| `integracao/test_int_04_frontend_api.py` + `frontend/cliente_frontend.mjs` | Código real de `frontend/src/services` contra a API real; contrato frontend × backend × OpenAPI |
| `integracao/test_int_05_publicacao.py` | CORS, `root_path`, `app.start`, primeiro administrador, seed bloqueado em produção |
| `stack/test_stk_01_resiliencia.py`, `stack/apoio_stack.py` | Reinício, queda e recriação de cada serviço, observados pelo Nginx |
| `stack/capturas.py`, `stack/stack-int.env` | Capturas de tela com o Playwright; ambiente da stack descartável |
| `regressao/` | `executar_suites.sh` e `comparar_execucoes.py` |
| `Dockerfile` | Executor com as versões do CI |
| `docs/`, `evidencias/` | Relatório em PDF e o script que o gera; saídas, JUnit XML e capturas |

## Convenções

- **Nomes:** `test_int_<area>_<nn>_<descrição>`; o ID do cenário (ex.: `INT-ARQ-04`) vem do nome.
- **Componentes reais:** dublês só para serviços externos que exigem conta (Supabase Storage e Brevo), e fiéis às APIs deles.
- **Oráculo:** a documentação do projeto (`backend/README.md`, `docs/DEPLOY.md`), o contrato OpenAPI e as mensagens do
  frontend; nunca o comportamento atual.
- **Defeitos:** `@defeito("DF-xx", motivo)` aplica `xfail(strict=True, raises=AssertionError)`. Só a falha do oráculo conta
  como defeito, e qualquer outra exceção aparece como falha real. Quando o problema for corrigido, o teste dá XPASS e a
  suíte falha de propósito: remova o marcador, e o teste passa a fazer parte da regressão.
- **Marcadores:** `integracao(...)` registra as interfaces exercitadas no JUnit XML; `hospedagem` separa os recursos do
  PR #39.
