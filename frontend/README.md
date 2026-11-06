# Interface de cadastro e manutenção — SCRUM-97

Telas de cadastro, edição e manutenção dos meios de hospedagem, com componentes
reutilizáveis e integração com os oito endpoints de escrita/documentos do OpenAPI.
Listagem, filtros, paginação, consulta completa e mapa pertencem à SCRUM-96.

## Executar com dados de demonstração

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

O modo `mock` é explícito em `.env.local`. Sem essa configuração, o cliente usa a
API real. A demonstração carrega o seed existente, mantém alterações e arquivos
somente na memória da sessão e restaura os exemplos ao recarregar a página.
Arquivos fictícios do seed retornam 404 até um arquivo real ser anexado por upload
ou substituição. Nenhum arquivo binário é serializado em JSON.

Rotas de entrada:

- `/#/estabelecimentos/novo`: cadastro, exclusivo do ADMINISTRADOR.
- `/#/estabelecimentos/<uuid>/editar`: edição ou consulta conforme perfil.
- `/#/meu-cadastro`: resolve exclusivamente o vínculo da conta HOTEL.

Exemplo de edição com o seed:
`http://localhost:5173/#/estabelecimentos/11111111-1111-4111-8111-111111111111/editar`.

`VITE_MOCK_ROLE` permite verificar ADMINISTRADOR, EDITOR, HOTEL e GESTOR sem criar
uma tela de gestão de contas. Para EDITOR/GESTOR, abra a rota de edição do exemplo;
HOTEL abre sua própria ficha por padrão. Não há seletor de perfis na interface.

## API real e cliente compartilhado com SCRUM-96

Configure `VITE_API_MODE=real` e `VITE_API_BASE_URL=http://localhost:8000`.
Execute o backend conforme seu README e use o frontend em `http://localhost:5173`,
origem já permitida pelo CORS do backend.

A integração de autenticação deve disponibilizar o access token na chave
`oto.accessToken` de `sessionStorage`. O cliente lê o token a cada requisição;
nenhuma credencial de demonstração é enviada automaticamente à API real.
Login e recuperação de senha não fazem parte desta issue.

`services/http.js` centraliza URL, Bearer, JSON, multipart, erros HTTP, cancelamento
e download binário. `services/runtime.js` concentra a configuração da sessão.
A SCRUM-96 pode reutilizar esses módulos e adicionar seus métodos de consulta à
mesma fábrica `createInventoryApi`. Não crie outra configuração de URL/token.
Respostas 401/403 nunca ativam fallback para mocks.

Os métodos de cadastro, PATCH, inativação, reativação, upload, edição de metadados,
download e substituição utilizam os caminhos e métodos do OpenAPI. GET de perfil,
categorias e ficha são dependências para inicializar a edição, sem construir a
listagem ou o mapa da outra issue.

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
- Ações de convite e alertas fixos de vencimento não foram implementados. O botão
  “Salvar e enviar convite” é de outro fluxo e não aparece como uma ação falsa.
- Os rótulos de navegação de outros módulos servem de contexto visual; as respectivas
  telas e operações não foram implementadas. “Sair” também não aciona autenticação.
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
