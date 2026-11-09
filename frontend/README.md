# Interface OTO — SCRUM-96 e SCRUM-97

Telas de cadastro, edição e manutenção dos meios de hospedagem, com componentes
reutilizáveis e integração com os oito endpoints de escrita/documentos do OpenAPI.
Listagem, filtros, paginação, consulta completa, mapa, dashboards e auditoria
estão implementados pela SCRUM-96, compartilhando o cliente e a sessão da SCRUM-97.

## Executar conectado ao backend

Inicie o FastAPI conforme `backend/README.md`. Em outro terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

A API real é o padrão (`VITE_API_MODE=real`). O navegador solicita `/api`, e o
servidor Vite encaminha ao FastAPI em `OTO_API_TARGET` (padrão
`http://127.0.0.1:8000`). Isso funciona tanto em `localhost:5173` quanto em
`127.0.0.1:5173`, sem duplicar a configuração HTTP no navegador.

O login está integrado. A sessão guarda `oto.accessToken` e `oto.expiresAt` em
`sessionStorage`; expiração, resposta 401 e saída removem a sessão. O cliente
bloqueia chamadas protegidas sem sessão antes de alcançar o proxy.
`OTO_DEV_BEARER_TOKEN` permanece opcional para ferramentas locais, somente no
servidor Vite; não autentica automaticamente a interface e não entra no bundle.

Contas fictícias do backend local:

| Perfil | E-mail | Senha |
| --- | --- | --- |
| ADMINISTRADOR | marina.admin@example.test | admin-demo |
| EDITOR | camila.editora@example.test | editor-demo |
| GESTOR | rafael.consulta@example.test | gestor-demo |
| HOTEL | responsavel@serra-azul.example | hotel-demo |

O proxy é configurado somente em `vite serve`. Em produção, configure um proxy
reverso para `/api` ou informe a URL real em `VITE_API_BASE_URL`, com CORS apropriado
no backend. O build não inclui o proxy nem o Bearer de desenvolvimento.

## Dados de demonstração opcionais

Use `VITE_API_MODE=mock` explicitamente para trabalhar sem backend. Esse modo
carrega o seed existente e mantém alterações e arquivos somente na memória da
sessão, restaurando os exemplos ao recarregar a página. Arquivos fictícios do
seed retornam 404 até um arquivo real ser anexado. Nenhum binário é serializado
em JSON. A etiqueta visual de demonstração foi removida do cabeçalho.

A API real agora usa PostgreSQL e storage persistente. Alterações, sessões, auditoria
e arquivos sobrevivem ao reinício. O modo memória é exclusivo de testes explícitos.

Rotas de entrada:

- `/#/estabelecimentos/novo`: cadastro, exclusivo do ADMINISTRADOR.
- `/#/estabelecimentos/<uuid>/editar`: edição ou consulta conforme perfil.
- `/#/meu-cadastro`: resolve exclusivamente o vínculo da conta HOTEL.

Exemplo de edição com o seed:
`http://localhost:5173/#/estabelecimentos/11111111-1111-4111-8111-111111111111/editar`.

`VITE_MOCK_ROLE` escolhe o perfil da conta de desenvolvimento em modo mock.
Esse transporte cobre cadastro/manutenção/documentos, login e perfil. Contas,
convites, pesquisas e relatórios exigem backend real e mostram indisponibilidade
explícita no modo mock.

## API real e cliente compartilhado com SCRUM-96

`services/http.js` centraliza URL, Bearer, JSON, multipart, erros HTTP, cancelamento
e download binário. `services/runtime.js` concentra a configuração da sessão.
A SCRUM-96 reutiliza esses módulos e acrescenta seus métodos de consulta à
mesma fábrica `createInventoryApi`. Não crie outra configuração de URL/token.
Respostas 401/403 nunca ativam fallback para mocks.

Os métodos de cadastro, PATCH, inativação, reativação, upload, edição de metadados,
download e substituição utilizam os caminhos e métodos do OpenAPI. GET de perfil,
categorias e ficha são dependências para inicializar a edição, compartilhadas com a
listagem e o mapa da SCRUM-96.

## Campos, validações e permissões

O contrato original é importado em `domain/establishment.js`: tipos, enums,
limites, formatos e grupos aninhados não são duplicados em um segundo schema.
Os campos de hospedagem, infraestrutura e acessibilidade incluem as propriedades
aninhadas de seus schemas. Os demais segmentos turísticos ficam fora da interface.

Cadastro exige categoria de hospedagem, nome fantasia, razão social, CNPJ e
endereço, permitindo dados operacionais incompletos. CNPJ é normalizado para
somente dígitos e tem seus dígitos verificadores validados. A unicidade continua
sob responsabilidade da API; o erro 409 é apresentado junto ao campo.

PATCH envia somente os campos alterados, preserva valores omitidos e diferencia
`false`, zero e `null`. Campos anuláveis podem ser limpos; listas usam um valor
por linha, e pagamentos oferecem os códigos conhecidos e opções livres do contrato.

ADMINISTRADOR cadastra, edita campos protegidos e altera status. EDITOR edita
sem alterar CNPJ/razão social. HOTEL recebe somente a ficha vinculada e tem esses
mesmos campos bloqueados. GESTOR não recebe ações de escrita. Essas restrições
não substituem a autorização do backend.

Inativação exige modal de confirmação e motivo de 3 a 500 caracteres. Reativação
também exige confirmação. Durante o envio, ações repetidas são bloqueadas e os
dados preenchidos permanecem disponíveis após erros.

## Documentos

Upload e substituição usam `FormData`; o cliente deixa o navegador definir o
boundary do multipart. A edição de metadados usa PATCH JSON, e o download usa
Blob, nome público do arquivo e URL temporária revogada após o acionamento.

Tipos permitidos: PDF, JPEG e PNG, com extensão correspondente. O limite padrão
é de 10 MiB por arquivo. `VITE_UPLOAD_MAX_BYTES` deve acompanhar o
`OTO_UPLOAD_MAX_BYTES` do backend. Arquivos vazios ou acima do limite são
rejeitados antes do envio; a API aplica sua própria validação.

## Referência visual e limites de escopo

Referência: página **Alta Fidelidade** do arquivo Figma `PDSI - OTO`, incluindo
`ADMIN-CADASTRO` (node `168:539`), `ADMIN - EDITAR` e `HOTEL -MEUCADASTRO`, além
do modal de inativação apresentado no PDF fornecido.

A página foi consultada no navegador; o conector de inspeção/exportação exige
permissão de editor e não disponibilizou os tokens e assets originais. A logo
local foi extraída da identidade visual do PDF, sem redesenhar a marca. A versão
atual reproduz a composição observável; a conferência exata de fonte, cores e
assets exportados permanece dependente desse acesso.

Diferenças necessárias entre a referência visual e o escopo/contrato:

- Categoria e razão social, ausentes no frame simplificado, foram incluídas na
  identificação para permitir o cadastro válido.
- Grupos completos do contrato ficam em seções expansíveis, mantendo o formulário
  inicial compacto e permitindo completar os dados depois.
- O atalho “Piscina” representa `infraestrutura.piscina_adulto`; “Acessibilidade”
  representa `acessibilidade.possui_facilidade_pcd`; “Área de Lazer” inverte
  `infraestrutura.recreacao.nao_possui`, sem criar uma propriedade fora do contrato.
- “Salvar e enviar convite” primeiro persiste a hospedagem e abre a confirmação
  da conta HOTEL vinculada. Falha no convite permite tentar novamente sem criar
  outra hospedagem ou duplicar uma conta já criada.
- Dashboards ADMIN/FUNCIONARIO, inventário, mapa e auditoria pertencem à SCRUM-96.
  Suas entradas abrem as telas de consulta implementadas nesta etapa.
- O campo “Justificativa de Remoção” mantém o rótulo do protótipo, mas envia
  `motivo_inativacao` e executa uma transição lógica, sem apagar o registro.

## Testes e verificação

```bash
cd frontend
npm test
npm run build
```

Testes usam `node:test`, `node:assert/strict`, Vite em middleware mode,
`ssrLoadModule` e `renderToStaticMarkup`. Cada servidor de testes usa cache
isolado e removido ao finalizar, preservando o servidor de desenvolvimento.
Não foram adicionados runners nem bibliotecas de DOM.

São cobertos: campos obrigatórios, cadastro incompleto, CNPJ, números, enums,
datas, checklists, PATCH, permissões, isolamento HOTEL, mensagens e estados de
envio, FormData, MIME/tamanho, download e preservação do arquivo anterior quando
a substituição falha. O transporte mockado reutiliza o seed original por teste.

A verificação manual no navegador inclui cadastro mínimo, erros de obrigatoriedade,
inativação sem/com motivo, envio, substituição e download. O conteúdo baixado foi
comparado ao arquivo temporário usado na substituição.

A integração HTTP foi validada contra o FastAPI real passando pelo proxy Vite:
perfil, categorias, cadastro, PATCH, upload, metadados, download, substituição,
inativação e reativação, além de 401 para token inválido e 403 para escrita GESTOR.
Os testes unitários do proxy verificam precedência de sessão e ausência de
configuração de desenvolvimento no build, sem depender de um backend em execução.

## Complemento da SCRUM-97

O planejamento local foi consolidado nas duas tarefas existentes: SCRUM-96 para
consulta e SCRUM-97 para acesso e operações. Nenhuma SCRUM-98–102 foi criada.

- `/#/login`, `/#/recuperar-senha` e `/#/ativar-convite?id=...&token=...`:
  autenticação, solicitação de recuperação e definição de senha de convite.
  Após ativar, o usuário entra pelo login; confirmação de senha fica no cliente.
- `/#/contas`: administração de equipe/HOTEL e criação/reenvio de convite.
- `/#/pesquisas`: criação, edição, confirmação, encerramento e exportação para
  os perfis permitidos. GESTOR consulta/exporta; HOTEL responde pelo seu início.
- `/#/inicio`: pendências e histórico do HOTEL, com resposta de ocupação de 0–100%.
- `/#/perfil`: nome/e-mail e preferências locais de tema e tamanho de fonte,
  isoladas por usuário. Cargo permanece protegido.

Não há endpoint de remoção de conta, alteração direta de senha nem upload de
avatar no contrato. Essas ações não simulam sucesso. A recuperação registra a
solicitação e os convites são registrados pelo servidor; entrega de e-mail e
conclusão da recuperação dependem do serviço de envio/contrato correspondente.
Relatórios agora retornam arquivos PDF/CSV reais, com polling limitado e validação
de MIME no cliente. Os dados e arquivos de relatório ainda são temporários no
backend; PostgreSQL segue dependente das migrations.

Os testes adicionais cobrem sessão/expiração, isolamento de rotas e preferências,
payloads, validação de acesso, convites com falha parcial, paginação de destinatários,
pesquisas, ocupação, exportação e renderização SSR dos novos módulos. Nenhuma
biblioteca de interação DOM ou dependência frontend foi adicionada.

## Consultas e dashboards — SCRUM-96

Plano executado: completar consultas do servidor, implementar dashboard/inventário/mapa,
adicionar detalhe/histórico/auditoria, testar combinações/permissões e conferir no navegador.
As operações de escrita existentes foram reutilizadas; scripts e prints seguem ignorados.

Rotas adicionais:

- `/#/inicio`: dashboard ADMINISTRADOR, EDITOR e GESTOR; HOTEL mantém seu início próprio.
- `/#/inventario`: busca por nome/razão social/CNPJ com ou sem pontuação; categoria,
  status, Cadastur, aceite de pesquisas, tamanho de página, ordenação e direção.
- `/#/estabelecimentos/<uuid>`: consulta de dados básicos, hospedagem, infraestrutura,
  acessibilidade e documentos; grupos expansíveis preservam a ficha completa.
- `/#/estabelecimentos/<uuid>/pesquisas`: histórico e pesquisas sem resposta da hospedagem.
- `/#/pesquisas/<uuid>/respostas`: respostas por hospedagem, incluindo taxa zero.
- `/#/auditoria`: filtros de ação, ID do autor e intervalo de data/hora, exclusivo ADMIN.

A tabela do inventário usa paginação e filtros no servidor. O mapa consulta todas as
páginas dos mesmos filtros, sem resumir o conjunto à página visível. A categoria
é restrita ao segmento de hospedagem. HOTEL continua isolado pelo backend e pelas
rotas da interface; GESTOR recebe somente ações de consulta e exportação.

### Mapa

Leaflet 1.9.4 foi escolhido antes da instalação por oferecer navegação, zoom e
marcadores sem adicionar outro framework React. A importação JS é dinâmica no
cliente, preservando renderização SSR dos testes. Tiles HTTPS do OpenStreetMap,
com atribuição visível e sem prefetch/download em massa, seguem a
[política do provedor](https://operations.osmfoundation.org/policies/tiles/).
Marcadores usam coordenadas reais da API, inclusive zero; não há geolocalização
do navegador. O seed aponta para São Carlos, portanto o mapa não força Olímpia.
Ausência de coordenadas e falha de rede têm estados explícitos e lista alternativa.
Em produção, avaliar provedor de tiles conforme volume e disponibilidade.

### Dashboard e lacunas contratuais

O servidor calcula totais sobre todas as fichas de hospedagem do repositório atual,
incluindo alterações persistidas no PostgreSQL. Leitos desconhecidos não são inventados: o card
indica total parcial e a quantidade de fichas incompletas. A tabela Cadastur usa
vencimentos efetivamente informados, ordenados do mais antigo ao mais recente;
valores negativos indicam vencidos. Não foi inventada uma janela de alerta de 30/60 dias.
A janela e eventual restrição por status ainda exigem alinhamento de negócio.

`GET /dashboard` tem resposta definida no OpenAPI, incluindo totais, leitos não
informados, alertas Cadastur e referência temporal. HOTEL não acessa o dashboard
administrativo; intervalos inválidos de auditoria retornam 422.

A auditoria compara instantes com fuso horário, ordena do mais recente e mostra
cada campo alterado, com distinção entre ausente, `null`, `false` e zero. O intervalo
`datetime-local` é convertido para ISO no cliente. Pesquisas permitem consulta por
mês/tipo, taxa de resposta calculada, histórico individual e exportação PDF/CSV
existente. Exportação consolidada inclui todas as pesquisas, independentemente do
filtro visual; XLS não é oferecido porque o backend não o gera.

No modo mock explícito, inventário, detalhe, dashboard e mapa reutilizam o seed;
a auditoria começa vazia e as operações de pesquisa continuam exigindo o backend.
O modo real nunca troca automaticamente para mock após 401/403.

A suíte adicional `src/reading.test.js` cobre parâmetros, busca, combinações,
ordenação/paginação, mapa completo, cancelamento, dados ausentes, permissões,
renderização dos estados, histórico e valores de auditoria. Mantém `node:test`,
`node:assert/strict` e Vite SSR; não adiciona biblioteca de DOM.

## Finalização #37 — Docker e persistência real

Execute `docker compose up -d --build --wait` na raiz após copiar `.env.example`
para `.env`. O frontend Nginx é servido em `OTO_WEB_PORT` (padrão 8080; nesta máquina
8081 por conflito prévio). A API fica em `/api`; documentação em `/api/docs`.
Migrations, PostgreSQL e worker são iniciados pelo Compose; volumes preservam banco
/arquivos. Mailpit captura e-mails em `http://localhost:8025`, sem envio externo.

Para o Vite, `OTO_API_TARGET=http://127.0.0.1:8080/api` encaminha à stack real
(ajuste para a porta configurada). O proxy continua fora do build. Não configure
`OTO_DEV_BEARER_TOKEN` para substituir o login da aplicação.

Com alinhamento do usuário, agora estão disponíveis alteração da própria senha,
redefinição por token e inativação/reativação de contas. O perfil abre um modal de
senha atual/nova/confirmada. Novas senhas têm 8–128 caracteres; sucesso encerra a
sessão e exige novo login. O link de recuperação abre `/#/redefinir-senha?token=...`.
Ativação e recuperação devem ser abertas a partir das mensagens capturadas no
Mailpit. Tokens ficam no fragmento da URL e no corpo do pedido, não na query HTTP.

Contas mostram ATIVO/INATIVO/PENDENTE corretamente. ADMIN confirma inativação ou
reativação; a própria conta não recebe o botão e o servidor protege o último
administrador. Contas pendentes recebem reenvio de convite. Nenhum DELETE é usado.
O frontend trata 401 sem fallback; expiração/revogação também são verificadas no SQL.

Avatar permanece por iniciais e preferências são locais por usuário: não há
upload ou sincronização remota dessas duas funções no MVP. Backend e contrato
detalham os schemas, regras de token e parâmetros SMTP.
