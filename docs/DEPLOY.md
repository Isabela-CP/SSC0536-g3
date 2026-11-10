# Publicação gratuita do OTO

## Fluxo de branches

A branch de desenvolvimento deste repositório é `Develop` (D maiúsculo).

1. Push em `Develop`: testes Python/PostgreSQL, testes React, build Vite e smoke Docker.
2. PR `Develop -> main`: executa as mesmas verificações; não publica.
3. Merge na `main`: o CI repete as verificações no commit efetivamente integrado.
4. Com CI aprovado, GitHub Actions publica o frontend no Pages e Render publica a API da `main` com **After CI Checks Pass**.

Não há deploy de `Develop`, de PRs ou de código de forks. O workflow Pages usa o
SHA exato aprovado pelo CI. Render e Pages são entregas independentes: uma falha
em um provedor não desfaz a publicação do outro. Migrações devem manter
compatibilidade com a versão anterior enquanto as duas entregas acontecem.
Não há migração destrutiva automática nem rollback de banco.

Configure uma regra de proteção/ruleset para `main`: exigir PR e os checks
`Testes do Backend (FastAPI)`, `Testes e Build do Frontend` e
`Docker e persistência após reinício`. Restrinja o environment `github-pages` à
branch `main`. Configurações dos painéis não são aplicadas apenas pelo YAML.

## Serviços escolhidos e limites

| Componente | Serviço | Plano e observações |
| --- | --- | --- |
| Frontend | GitHub Pages | Gratuito para este repositório público; URL sob `github.io`, sem comprar domínio. |
| API Docker | Render Web Service Free | Suspende após 15 minutos sem tráfego; a primeira chamada pode demorar. Sem disco persistente e sem SMTP nas portas 25/465/587. |
| PostgreSQL e arquivos privados | Supabase Free | 500 MB de banco, 1 GB de arquivos, sujeito às cotas de tráfego; pausa após uma semana sem atividade. |
| E-mail transacional | Brevo Free | Até 300 envios/dia, sujeito à aprovação da conta e verificação do remetente. API HTTPS, sem SMTP. |

Não é uma hospedagem com disponibilidade garantida. Use planos gratuitos e não
habilite upgrades automáticos. Os limites podem mudar; confira os painéis.
Não foi escolhido Render Postgres Free porque expira após 30 dias.

## 1. Supabase: banco e storage

1. Entre em <https://supabase.com/dashboard> e crie uma organização/projeto **Free**.
2. Guarde a senha de banco em um gerenciador de senhas.
3. Em **Connect**, selecione **Session pooler**, porta **5432** (IPv4).
   Copie a URI PostgreSQL, substituindo a senha e mantendo `sslmode=require`.
   Não use o transaction pooler/porta 6543: o runner usa locks de sessão.
   Se a senha contém caracteres especiais, codifique-os na URI.
4. Em **Project Settings / API**, copie **Project URL**.
5. Em **Settings > API Keys > Secret keys**, crie uma chave `sb_secret_…`.
   O adaptador também aceita a chave legada `service_role`; não use publishable.
   Ela será exclusiva do backend, com privilégios para os arquivos privados.
6. Em **Storage**, crie o bucket `oto-arquivos`, **privado** (Public desligado).
   Configure limite de 50 MiB para comportar relatórios; uploads de documentos
   continuam limitados pela API a 10 MiB. MIME permitidos: `application/pdf`,
   `image/jpeg`, `image/png`, `text/csv`.
7. Não crie políticas públicas de leitura/escrita. A API autoriza cada operação
   e usa a chave de serviço para acessar o bucket. As tabelas da aplicação têm
   RLS sem acesso para os papéis `anon`/`authenticated`. Desative a Data API no
   painel se esse projeto for exclusivo do OTO: a aplicação não precisa dela.

O backend usa SQL pelo pooler com o proprietário do projeto para migrations e
operações. Não use essa URI no frontend. Os arquivos ficam no bucket, separados
em `documentos/` e `relatorios/`; a chave interna permanece no PostgreSQL.
Use um projeto novo/exclusivo, sem dados de outro sistema.

## 2. Brevo: envio de e-mails reais

1. Cadastre-se em <https://www.brevo.com/> no plano **Free**.
2. Conclua a verificação da conta e habilite o envio transacional, se solicitado.
3. Em **Settings > Senders, Domains, IPs > Senders**, adicione um remetente
   com nome `OTO Hospedagem` e um e-mail que você controla. Confirme o código
   enviado para essa caixa. Esse endereço será `OTO_MAIL_FROM`.
4. Em **SMTP & API > API Keys**, gere uma **API key**. Ela será
   `OTO_BREVO_API_KEY` no Render. Não é uma SMTP key nem a senha do seu e-mail.
5. Se tiver domínio próprio, autentique-o com os registros DNS indicados no
   painel. Com Gmail/outro endereço gratuito, você pode verificar o remetente,
   mas não autenticar esse domínio; o Brevo pode reescrever o endereço e aplicar
   restrições de entrega/aprovação. Não é necessário comprar domínio para criar
   a conta e iniciar os testes, mas entrega em caixas reais depende dessa validação.

Não instale nem configure Gmail SMTP no Render gratuito. Convites e recuperação
usam tokens gerados automaticamente, na outbox SQL; o corpo é limpo após envio.
No Render, a API executa o dispatcher em uma thread, sem contratar worker pago.
Quando o serviço estiver suspenso, mensagens pendentes aguardam o próximo início;
um pedido recebido normalmente acorda a API. Há até dez tentativas por mensagem;
falhas aparecem nos logs sem token nem credencial. Entrega é ao menos uma vez:
uma interrupção após aceite do provedor pode causar mensagem duplicada.

## 3. GitHub Pages

No repositório <https://github.com/Isabela-CP/SSC0536-g3>:

1. **Settings > Pages > Build and deployment > Source: GitHub Actions**.
2. O endereço esperado é `https://isabela-cp.github.io/SSC0536-g3/`;
   confirme no painel. O roteamento por hash funciona sem regras de rewrite.
3. Depois de criar a API no Render, em **Settings > Secrets and variables >
   Actions > Variables > New repository variable**, crie `OTO_API_URL` com a
   URL HTTPS do serviço, por exemplo `https://oto-api-xxxx.onrender.com`.
   **Sem `/api`**: no Render a API está na raiz, diferente do Compose local.
4. Não crie `VITE_*` com credenciais. A URL pública é uma variável, não um secret.
   O build define `VITE_BASE_PATH=/SSC0536-g3/` e `VITE_API_MODE=real`.

Sem `OTO_API_URL`, o job de publicação é ignorado: não publica um frontend
apontando por engano para localhost ou mocks. Configure o endereço e reexecute
o **CI** do último push da `main` para disparar a publicação.

## 4. Render: criar a API após o merge em main

O primeiro merge deve incluir `render.yaml`, o workflow e o código cloud.
Só então crie o serviço:

1. Entre em <https://dashboard.render.com/>, conecte sua conta GitHub e autorize
   acesso a este repositório. Use **New > Blueprint**, selecione o repositório
   e a branch **main**. O arquivo é `render.yaml` na raiz.
2. Confirme **Web Service / Docker / Free**, sem banco ou worker pago.
3. Preencha as variáveis abaixo no formulário do Blueprint/Environment.
4. Verifique **Auto-Deploy: After CI Checks Pass**, branch **main**,
   health check `/health`, comando `python -m app.start`.
   Nunca selecione `Develop` como branch de entrega.
5. A primeira criação pode iniciar uma implantação pelo painel; faça isso
   somente depois de o CI do merge da `main` passar. Deploys seguintes serão
   automáticos após os checks. A revisão/sync de Blueprint por si só não
   substitui a aprovação dos checks nem deve disparar deploy manual de Develop.

| Variável no Render | Origem/valor |
| --- | --- |
| `DATABASE_URL` | URI Session pooler do Supabase, com senha e `sslmode=require`. |
| `OTO_SUPABASE_URL` | Project URL do Supabase (`https://...supabase.co`). |
| `OTO_SUPABASE_SERVICE_KEY` | Nova chave `sb_secret_…` do Supabase. **Secreta.** |
| `OTO_PUBLIC_URL` | URL completa do frontend: `https://isabela-cp.github.io/SSC0536-g3`. |
| `OTO_CORS_ORIGINS` | Apenas origem: `https://isabela-cp.github.io` (sem caminho/barra final). |
| `OTO_BREVO_API_KEY` | API key gerada no Brevo. **Secreta.** |
| `OTO_MAIL_FROM` | E-mail do remetente verificado no Brevo. |
| `OTO_BOOTSTRAP_ADMIN_EMAIL` | Seu e-mail para a primeira conta administradora. |
| `OTO_BOOTSTRAP_ADMIN_PASSWORD` | Senha inicial exclusiva de 12–128 caracteres. **Secreta.** |

As demais variáveis estão preenchidas no Blueprint: produção, PostgreSQL,
Supabase, bucket `oto-arquivos`, Brevo e dispatcher embutido. Não configure
`OTO_ROOT_PATH=/api` no Render; isso pertence ao proxy do Compose local.

Na inicialização, o serviço aplica migrations versionadas com lock e cria o
primeiro administrador **somente se não houver usuários**. Não executa seed
com contas/senhas públicas de demonstração. Depois do primeiro acesso, altere
a senha no perfil e remova `OTO_BOOTSTRAP_ADMIN_PASSWORD`/`EMAIL` do ambiente:
com usuários existentes não são necessárias nem redefinem a senha ao reiniciar.

## 5. Conferência final

1. Render deve indicar **Live**; `/health` responde `{"status":"ok"}`;
   `/docs` deve abrir o contrato.
2. Configure `OTO_API_URL` no GitHub e reexecute o CI da `main` se o Pages
   foi ignorado antes de existir essa variável.
3. Abra o Pages e entre com seu administrador inicial. As contas demo não
   existem nessa base nova. Confirme a ausência de erros CORS no navegador.
4. Crie uma hospedagem, anexe PDF, baixe e substitua; reinicie o serviço
   Render e confira novamente. Arquivos devem continuar no bucket privado.
5. Crie uma conta pendente e envie convite para um endereço que você controla.
   Confira o painel Transactional/Logs do Brevo e a caixa de destino.
   Valide também recuperação de senha; os links devem apontar para o Pages,
   incluindo `/SSC0536-g3/#/...`.
6. Comprove que um push em `Develop` roda apenas CI. Só o merge em `main`
   deve disparar as próximas entregas automáticas.

Esses passos externos dependem das contas/chaves reais. Os testes de adaptadores
usam HTTP simulado; não comprovam credenciais nem entrega externa antes da
configuração. Nunca cole chaves/senhas em issues, PRs, commits ou no chat.

## Fontes oficiais

- <https://vite.dev/guide/static-deploy#github-pages>
- <https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site>
- <https://render.com/docs/free>
- <https://render.com/docs/blueprint-spec>
- <https://render.com/docs/deploys>
- <https://supabase.com/pricing>
- <https://supabase.com/docs/guides/database/connecting-to-postgres>
- <https://supabase.com/docs/guides/storage/security/access-control>
- <https://developers.brevo.com/docs/send-a-transactional-email>
- <https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan>
- <https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email>
