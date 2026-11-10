# SSC0536-g3 — OTO Hospedagem

Plataforma React + Vite e FastAPI para o inventário de meios de hospedagem.
A API real usa PostgreSQL; o contrato REST fica em
[`contratos_api_oto/openapi.json`](contratos_api_oto/openapi.json).

Para preparar a publicação automática, siga o [guia de CI/CD](docs/DEPLOY.md).

## Executar com Docker

```bash
cp .env.example .env
# Ajuste as portas em .env se já estiverem ocupadas.
docker compose up -d --build --wait
```

- Aplicação: http://localhost:8080 (ou a porta `OTO_WEB_PORT`).
- API e Swagger: http://localhost:8080/api/docs.
- Caixa de e-mail de desenvolvimento: http://localhost:8025.

Nesta máquina a porta 8080 já estava ocupada; a configuração local ignorada usa
**8081**, com `OTO_PUBLIC_URL=http://localhost:8081`.

O Compose inicia PostgreSQL 17, migrations versionadas, API, worker de e-mail,
Mailpit e frontend Nginx. O banco não é publicado na rede do host. As portas
web/e-mail são limitadas ao loopback. Os volumes `postgres` e `files` preservam
dados e arquivos ao reiniciar/recriar containers. `docker compose down` os mantém;
`docker compose down --volumes` **apaga os dados** e é reservado a ambientes descartáveis.
O Mailpit captura mensagens localmente: não entrega e-mails à internet.

### Contas fictícias locais

| Perfil | Login | Senha |
| --- | --- | --- |
| ADMINISTRADOR | marina.admin@example.test | admin-demo |
| GESTOR | rafael.consulta@example.test | gestor-demo |
| EDITOR | camila.editora@example.test | editor-demo |
| HOTEL | responsavel@serra-azul.example | hotel-demo |

Essas contas são fixtures públicas exclusivas de desenvolvimento. O seed gerenciado
é aplicado uma vez e não sobrescreve contas/senhas alteradas ao reiniciar a stack.
No ambiente de produção, não execute o seed e configure credenciais/SMTP próprios.

## Desenvolvimento e testes

```bash
cd frontend
npm ci
npm test
npm run build
```

Para Vite junto do Docker, configure em `frontend/.env.local`:

```dotenv
VITE_API_MODE=real
VITE_API_BASE_URL=/api
OTO_API_TARGET=http://127.0.0.1:8080/api
```

Troque 8080 por `OTO_WEB_PORT`. O proxy é exclusivo do servidor Vite;
URL/token/tratamento de erro continuam compartilhados no cliente HTTP.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v
```

A suíte unitária opta explicitamente por memória. Para executar também a integração
SQL, informe uma conexão **de testes** com permissão de criar bancos descartáveis:

```bash
OTO_TEST_ADMIN_URL=postgresql://usuario:senha@localhost:5432/postgres python -m pytest -v
```

Os testes SQL criam e removem apenas bancos `oto_test_*` exclusivos da execução;
não truncam bases de desenvolvimento. O CI sempre disponibiliza PostgreSQL real.
A integração não é considerada validada quando essa variável está ausente.

Teste da stack completa (cria registros fictícios e reinicia `api`/`worker`):

```bash
OTO_STACK_URL=http://localhost:8080 python backend/tests/stack_smoke.py
```

Esse teste comprova que sessão, ficha, documento substituído, auditoria e PDF
persistem após reinício. Não execute contra ambientes de produção.

## Organização

- `frontend/`: telas e cliente HTTP; [documentação](frontend/README.md).
- `backend/`: API, serviços, repositórios, storage e testes; [documentação](backend/README.md).
- `db/`: migrations e seed PostgreSQL; [documentação](db/README.md).
- `contratos_api_oto/`: OpenAPI e fixtures originais.
- `.github/`: CI, template de PR e review automático.

Login usa Bearer opaco com hash no banco, validade no servidor e revogação.
Recuperação/ativação usam tokens de uso único; a fila de e-mails é transacional.
ADMINISTRADOR, GESTOR, EDITOR e HOTEL são autorizados pelo backend, incluindo
isolamento HOTEL e proteção de CNPJ/razão social. Avatar continua representado
por iniciais; preferências de tema/fonte são locais por usuário, fora da persistência
remota do MVP. Nenhuma dessas duas funcionalidades simula upload/sincronização.

Preencha o template de PR, informe `Closes #<issue>` e siga o
[guia de review](.github/review/REVIEW_GUIDE.md). Reviews automáticos não fazem merge.
