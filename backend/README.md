# API OTO — FastAPI e PostgreSQL

O modo real usa PostgreSQL por padrão. `DATABASE_URL` é obrigatório fora do Docker;
alternativamente configure `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.
Falha de conexão retorna 503, sem trocar para JSON. `OTO_DATA_BACKEND=memory` é
exclusivo de testes/mocks explícitos e é rejeitado com `OTO_ENV=production`.

## Executar

A forma recomendada é `docker compose up -d --build --wait` na raiz do projeto.
O serviço `migrate` aplica as migrations e o seed de desenvolvimento; a API só sobe
quando ele termina com sucesso. O Swagger está em `/api/docs` do frontend Docker.

Para PostgreSQL local, em um banco destinado ao OTO:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://usuario:senha@localhost:5432/oto_dev'
python -m app.migrate --seed
uvicorn app.main:app --reload
```

Não aponte esses comandos para outro projeto/banco de produção. Um banco legado
criado manualmente precisa de verificação/baseline assistido antes do runner;
não há adoção silenciosa de schemas pré-existentes nem exclusão automática de dados.

## Persistência e transações

- `database.py`: conexões psycopg e unidade de trabalho compartilhada; nenhum pool
  global guarda transações abertas entre requisições. O DSN não é devolvido em erros.
- `postgres_inventory.py`: adaptador do protocolo de inventário existente. Usa
  tabelas relacionais, JSONB dos checklists, busca/filtros/ordenação/paginação SQL
  e locks para alterações concorrentes. CNPJ normalizado tem índice único no banco.
- `postgres_portal.py`: usuários, convites, sessões, pesquisas, destinatários,
  respostas, auditoria e relatórios SQL, com DTOs públicos compatíveis com a interface.
- `inventory_service.py`: continua responsável por validação de CNPJ, PATCH,
  autorização por campo, status e documentos. A auditoria SQL participa da mesma
  transação; falhas não deixam alteração/log de sucesso parcialmente gravados.
- `read_views.py`: agregações e validações compartilhadas das consultas.

As migrations são rastreadas em `schema_migrations`, com checksum e lock PostgreSQL.
Cada arquivo e seu registro são atômicos. Alterar migration já aplicada gera erro;
use migration incremental. O seed gerenciado usa `application_seeds` e só é aplicado
uma vez; não redefine senhas ou estado de fichas ao reiniciar os containers.

## Autenticação e contas

Senhas são verificadas com Argon2id (`pwdlib`). Os hashes do seed SQL correspondem
às contas públicas de desenvolvimento descritas no README da raiz. A API SQL não
aceita `admin-token`/outros tokens fixos dos mocks.

Cada login gera um Bearer opaco aleatório de 256 bits. Apenas SHA-256 desse token
fica em `sessoes`. `OTO_SESSION_SECONDS` configura validade (padrão 900; permitido
60–86400 segundos). O servidor verifica expiração/revogação e status do usuário
em toda requisição, independentemente do relógio/sessionStorage do navegador.
Não há refresh automático: ao expirar, faça login novamente.

Logout revoga a sessão apresentada. Alteração/redefinição de senha e inativação
de conta revogam todas as sessões do usuário. Reativar não restaura sessões antigas.
A API impede auto-inativação e preserva ao menos um administrador ativo. Contas
pendentes são ativadas por convite; não se tornam ativas pelo endpoint de reativação.

Perfis:

- ADMINISTRADOR: gestão de contas, campos protegidos, status, inventário e auditoria.
- EDITOR: edição da ficha, exceto CNPJ/razão social; gestão de pesquisas.
- GESTOR: consultas e exportação; escrita de negócio bloqueada.
- HOTEL: apenas a própria ficha/respostas, com vínculo lido da sessão SQL.

Perfil pessoal pode ser atualizado por seu titular. Nenhum campo de perfil/conta
pode aumentar as permissões de quem solicita a operação.

## E-mail, ativação e senhas

O contrato foi ampliado com alinhamento explícito da issue #37:

- `POST /auth/redefinicao-senha`: token e nova senha, sem autenticação prévia.
- `PUT /perfil/senha`: senha atual e nova senha; exige sessão.
- `POST /usuarios/{id_usuario}/inativacao` e `/reativacao`: somente ADMINISTRADOR.

Novas senhas têm 8–128 caracteres. A confirmação é validada na interface e não é
enviada como campo extra à API. Os endpoints existentes de ativação/recuperação,
perfil, usuários, pesquisas, auditoria, dashboard e relatórios ganharam schemas.
IDs operacionais são strings opacas na API, mapeadas aos BIGINTs SQL; UUIDs são
mantidos para estabelecimentos. SQL `estado` é traduzido para DTO `status`.

Convite: sete dias, hash persistido, uso único, reenvio cancela o anterior. Recuperação:
30 minutos, hash persistido, novo pedido invalida tokens anteriores ainda válidos.
A resposta da recuperação é igual para conta conhecida/desconhecida. Tokens e senhas
não entram na auditoria nem nas respostas públicas de criação de convite.

A fila `email_outbox` é criada na mesma transação da operação. `python -m app.mailer`
envia por SMTP com locks `SKIP LOCKED`, tentativas limitadas e limpeza do corpo após
envio. A mensagem contém temporariamente o link até ser entregue. SMTP tem semântica
**ao menos uma vez**: falha entre envio e commit pode causar e-mail duplicado, mas não
reutilização de token. Mensagens que atingem dez falhas exigem inspeção/reprocessamento.
A fila não afirma sucesso de entrega na interface; no Docker o Mailpit captura o envio.

Configuração: `OTO_SMTP_HOST`, `OTO_SMTP_PORT`, `OTO_MAIL_FROM`, opcionais
`OTO_SMTP_STARTTLS=true`, `OTO_SMTP_USER`, `OTO_SMTP_PASSWORD`. Sem host, o worker
não envia. `OTO_PUBLIC_URL` define a origem dos links de ativação/redefinição.

## Arquivos e relatórios

`DocumentStorage` separa binários do registro SQL. A implementação local usa chaves
UUID geradas pelo servidor; nomes e referências internas não são aceitos do cliente.
SQL preserva metadados e associações ao arquivo. `OTO_STORAGE_DIR` configura a raiz
(padrão `~/.local/share/oto/documentos`); Docker usa o volume em `/data/documentos`.
Relatórios têm storage próprio via o mesmo protocolo, em `relatorios/`, configurável
por `OTO_REPORT_STORAGE_DIR`. Binários não são serializados em JSON/colunas do banco.

Upload: um único POST multipart com arquivo e metadados. PATCH altera metadados;
PUT `/arquivo` substitui o binário. São aceitos PDF/JPEG/PNG, MIME e extensão
correspondentes, máximo padrão de 10 MiB (`OTO_UPLOAD_MAX_BYTES`). Arquivo vazio
é rejeitado. Nginx limita a requisição completa a 12 MiB e retorna JSON em 413.
Substituição preserva o arquivo anterior quando persistência/auditoria falham.
Relatórios PDF/CSV reais têm limite próprio de 50 MiB (`OTO_REPORT_MAX_BYTES`).

O seed contém exemplos de metadados de documentos/relatórios; binários fictícios
não são fabricados. Seu download retorna 404 até haver conteúdo real no storage.
Upload/substituição e relatórios gerados pela aplicação sobrevivem a reinícios.
A geração de relatório é síncrona (resposta 202 já concluída neste adaptador local).

## Decisões do MVP

- Documento vence antes de hoje: VENCIDO; de hoje até 30 dias: A_VENCER;
  além disso: REGULAR. O cálculo usa a data UTC; exemplos antigos não fixam a janela.
- Dashboard Cadastur lista todos os vencimentos informados, inclusive vencidos,
  ordenados por data; não aplica uma janela inventada nem usa alertas AVCB fixos.
- Leitos desconhecidos são indicados como total parcial; zeros não são tratados
  como ausentes. Histórico e auditoria preservam nulo/false/zero.
- Conta é inativada, sem DELETE; avatar por iniciais e preferências locais de
  tema/fonte permanecem fora da sincronização remota do MVP.
- PostgreSQL é obrigatório para os novos fluxos de senha/contas. O modo mock legado
  cobre inventário e testes, sem simular entrega externa ou persistência SQL.

## Testes

```bash
python -m pytest -v
OTO_TEST_ADMIN_URL='postgresql://usuario:senha@localhost:5432/postgres' python -m pytest -v
```

Sem `OTO_TEST_ADMIN_URL`, casos SQL são explicitamente pulados; isso não comprova
integração. O CI usa PostgreSQL 17 e executa a suíte com essa variável. Fixtures SQL
criam bancos aleatórios `oto_test_*`, aplicam migrations/seed e descartam somente
suas bases isoladas. Há testes de concorrência, rollback, sessões/expiração/revogação,
perfis, convites, recuperação, e-mail capturado, documentos e relatórios.
O job Docker também executa `tests/stack_smoke.py`, que escreve dados fictícios e
reinicia processos para verificar persistência. Nunca execute esse smoke em produção.
