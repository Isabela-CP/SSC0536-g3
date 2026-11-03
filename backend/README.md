# Backend — Inventário OTO

API FastAPI do Inventário OTO. Leitura e escrita compartilham um repositório
em memória inicializado de `../contratos_api_oto/mocks/seed-data.json`, seguindo
`../contratos_api_oto/openapi.json`.

## Executar

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API: `http://localhost:8000`; documentação: `http://localhost:8000/docs`.

## Consultas do inventário

- `GET /health` (pública)
- `GET /categorias-estabelecimento`
- `GET /estabelecimentos`
- `GET /estabelecimentos/{id_estabelecimento}`
- `GET /estabelecimentos/{id_estabelecimento}/documentos`

As quatro rotas de inventário exigem `Authorization: Bearer <token>`.
ADMINISTRADOR, GESTOR e EDITOR consultam todo o inventário; HOTEL consulta apenas
o estabelecimento vinculado à conta. Contas inativas recebem `401`; perfis não
autorizados e HOTEL sem vínculo recebem `403`. O escopo é aplicado no servidor
antes de filtros e paginação, e antes de consultar ficha/documentos de outra
hospedagem.

A listagem aceita todos os parâmetros do contrato:

- `busca`: substring em nome fantasia, razão social ou CNPJ, sem diferenciar
  maiúsculas/minúsculas, até 120 caracteres. CNPJ mantém a máscara do seed.
- `id_categoria`: inteiro a partir de 1.
- `status`: `ATIVO` ou `INATIVO`.
- `cadastur_status`: `OBRIGATORIO`, `OPCIONAL` ou `NAO_CONSTA`.
- `aceita_pesquisas`: booleano, incluindo filtro por `false`.
- `page`: a partir de 1, padrão 1; `page_size`: de 1 a 100, padrão 20.
- `ordenar_por`: `nome_fantasia` (padrão), `criado_em` ou `atualizado_em`;
  `ordem`: `asc` (padrão) ou `desc`.

Os filtros são combinados por interseção. A ordenação ocorre antes da paginação,
com desempate pelo UUID ascendente. Datas são comparadas como instantes com
fuso horário. Nomes usam comparação Unicode sem distinção de caixa.
A paginação preserva o comportamento anterior: `total_pages` mínimo de 1,
mesmo sem resultados; páginas além do total retornam `data: []`.
A ficha preserva os campos do seed, incluindo hospedagem, infraestrutura,
acessibilidade e documentos com metadados de arquivo. Cadastros incompletos
preservam campos nulos e seções opcionais ausentes.

`app/inventory.py` contém o protocolo de leitura e o adaptador JSON.
`app/inventory_repository.py` adiciona `WritableInventoryRepository` e o
repositório em memória compartilhado entre leitura e escrita. As rotas recebem
o repositório via `inventory_repository`; uma implementação PostgreSQL pode
substituí-lo sem alterar o contrato HTTP. O mock usa lock e rollback por
transação; a implementação SQL deverá usar transações e unicidade do CNPJ
normalizado, além de persistir a auditoria junto da operação.

O mock é inicializado no primeiro acesso e preserva o arquivo seed original.
O estado é por processo: use um único worker em desenvolvimento. Reiniciar a
API restaura o seed e perde alterações e referências de arquivos em memória.
Arquivos locais permanecem no storage. A persistência PostgreSQL e seus testes
de integração devem ser validados com SCRUM-85 e as migrations operacionais.

## Escrita de estabelecimentos

- `POST /estabelecimentos`: ADMINISTRADOR, resposta `201`.
- `PATCH /estabelecimentos/{id_estabelecimento}`: ADMINISTRADOR, EDITOR ou HOTEL.
- `POST /estabelecimentos/{id_estabelecimento}/inativacao`: ADMINISTRADOR.
- `POST /estabelecimentos/{id_estabelecimento}/reativacao`: ADMINISTRADOR.

Cadastro exige categoria existente, nome fantasia, razão social, CNPJ e endereço.
Capacidade, infraestrutura e checklists são opcionais. CNPJ aceita a máscara do
contrato ou apenas dígitos; valida dígitos verificadores e rejeita duplicidade
com `409 CONFLICT`, comparando os dígitos independentemente da máscara.

Os modelos de entrada e saída são Pydantic, derivados dos schemas do OpenAPI
em `app/inventory_models.py`. A validação anterior à conversão também verifica
formatos, campos extras, `minProperties` e `uniqueItems` pelo JSON Schema.

PATCH usa `exclude_unset=True`: campo ausente é preservado; `null` explícito
limpa apenas campos anuláveis. Objetos aninhados são atualizados parcialmente;
listas são substituídas integralmente. CNPJ e razão social são exclusivos de
ADMINISTRADOR, inclusive tentativas com valor nulo ou inválido. HOTEL só edita
a própria ficha; GESTOR não escreve. Status é alterado apenas nas rotas próprias.

Inativação faz `ATIVO -> INATIVO` e exige `motivo_inativacao` com 3 a 500
caracteres. Reativação faz `INATIVO -> ATIVO` e limpa o motivo da ficha atual,
preservando o motivo anterior nos snapshots da auditoria. Transições repetidas
retornam `409 ESTABELECIMENTO_JA_INATIVO` ou `ESTABELECIMENTO_JA_ATIVO`.

## Documentos e arquivos

- `POST /estabelecimentos/{id_estabelecimento}/documentos`: multipart, resposta `201`.
- `PATCH /estabelecimentos/{id_estabelecimento}/documentos/{id_documento}`: metadados JSON.
- `GET /estabelecimentos/{id_estabelecimento}/documentos/{id_documento}/arquivo`: download.
- `PUT /estabelecimentos/{id_estabelecimento}/documentos/{id_documento}/arquivo`: substituição multipart.

Escrita de documentos permite ADMINISTRADOR, EDITOR e HOTEL; download também
permite GESTOR. HOTEL permanece limitado à hospedagem vinculada, e o documento
sempre é buscado dentro do estabelecimento indicado na URL.

Upload exige `tipo_documento`, `data_vencimento` e `arquivo`; `numero` e
`data_emissao` são opcionais. PUT recebe somente `arquivo`. Os formatos são
`multipart/form-data`, sem base64 em JSON. Campos extras ou repetidos são
rejeitados. O status é calculado na criação e ao alterar o vencimento: vencido
antes da data UTC atual, a vencer entre hoje e 30 dias, regular após esse prazo.
Esse intervalo de 30 dias é uma decisão de desenvolvimento a confirmar.

`app/document_storage.py` define `DocumentStorage` e `LocalDocumentStorage`.
Os limites adotados para desenvolvimento são:

- MIME `application/pdf`, `image/jpeg` e `image/png`, conforme o encoding do contrato.
- Extensões correspondentes `.pdf`, `.jpg`/`.jpeg` e `.png`.
- Limite padrão **10 MiB por arquivo**, configurável por `OTO_UPLOAD_MAX_BYTES`.
- Nome de arquivo de até 255 caracteres; caminhos enviados pelo cliente são removidos.
- Storage padrão `~/.local/share/oto/documentos`, configurável por `OTO_STORAGE_DIR`.

MIME declarado e extensão são verificados; tamanho é contado durante a cópia
em blocos. Arquivo vazio retorna `422`; tipo não permitido, `415`; tamanho acima
do limite, `413`. O parser multipart do framework usa arquivos temporários
antes da validação do storage. Os testes usam storage isolado em `tmp_path`.

Cada arquivo recebe uma chave UUID gerada pelo servidor. A referência fica
separada da ficha e dos metadados públicos: nome, MIME, tamanho e envio. Binários
ficam apenas no storage. Download usa `application/octet-stream` com attachment.
Documentos do seed têm metadados fictícios; sem upload de um arquivo real,
o download retorna `404`. PUT permite anexar o arquivo a esses documentos.

Substituição mantém o ID do documento, grava um arquivo novo e remove o anterior
após atualizar a referência. Falhas de persistência desfazem a alteração no mock
e removem o arquivo novo; o anterior é preservado.

`app/inventory_service.py` concentra regras e operações. Cadastro, edição,
transições, upload, edição de metadados e substituição chamam `audit()`, com
snapshots independentes antes/depois, sem expor chave ou caminho de storage.

## Credenciais e demais módulos de demonstração

As credenciais locais são `marina.admin@example.test` / `admin-demo`,
`rafael.consulta@example.test` / `gestor-demo` e
`camila.editora@example.test` / `editor-demo`. Use `POST /auth/login` para obter
o token Bearer.

Para testar HOTEL, use os e-mails de `contas_empresario` do seed (por exemplo,
`responsavel@serra-azul.example`) com senha `hotel-demo`. O vínculo é carregado
do seed no servidor, sem aceitar o estabelecimento enviado pelo cliente no login.
Essas contas e os tokens estáticos são exclusivamente de demonstração, assim
como as demais credenciais locais; não implementam sessões de produção.

A base também inclui autenticação, perfil, usuários, convites, pesquisas de
ocupação, respostas, relatórios, auditoria e dashboard. Esses módulos mantêm
seus dados em memória, assim como o repositório temporário do inventário.

## Decisões e pontos do contrato para discussão

O arquivo `../contratos_api_oto/openapi.json` e os mocks não foram alterados.
Os testes validam respostas diretamente contra seus schemas e formatos.

- A listagem documenta `400`, mas não `422`: parâmetros inválidos retornam
  `400` com `ErrorResponse`, em vez do erro padrão do FastAPI.
- O contrato declara IDs no formato UUID, mas não documenta resposta para UUID
  malformado na ficha/documentos. A implementação usa `400` com `ErrorResponse`;
  documentar essa resposta depende de discussão com a equipe.
- O contrato não define desempate, colação de nomes nem mínimo de `total_pages`.
  Os critérios descritos acima explicitam essas decisões sem modificar o contrato.
- Alguns exemplos antigos de ficha omitem `arquivo` dos documentos, embora
  `DocumentoControle` o exija. As respostas seguem o schema e o seed atual,
  que já fornece os metadados. Ajustes nos exemplos ficam para discussão.

- O schema de cadastro aceita CNPJ e razão social nulos, mas a descrição e a
  issue #30 exigem esses dados. No cadastro a implementação rejeita `null` com
  `422`; no PATCH o ADMINISTRADOR pode usar `null`, conforme o schema. A equipe
  deve decidir se o contrato de criação deve deixar de ser anulável.
- O PUT de arquivo não documenta `422` para multipart ausente/inválido. A API
  retorna `422 VALIDATION_ERROR` nesses casos. JSON/multipart malformado e IDs
  inválidos usam `400 BAD_REQUEST`, que também está ausente em algumas operações.
  São lacunas a discutir antes de alterar o contrato.
- O tamanho máximo e a janela de documento a vencer ficam configuráveis ou
  documentados como padrões de desenvolvimento; a equipe deve confirmar os valores.

## Plano executado e validação

1. Comparar parâmetros, perfis e estruturas de resposta com o OpenAPI.
2. Separar repositório JSON e consultas das rotas HTTP.
3. Completar filtros, ordenação, validações e autorização, incluindo HOTEL.
4. Validar contratos e comportamentos com fixtures independentes baseadas no seed.
5. Adicionar modelos Pydantic e repositório mutável substituível.
6. Implementar escrita, autorização por campo e transições com auditoria.
7. Implementar documentos, storage, download e substituição com rollback.
8. Testar casos positivos, negativos, concorrência de CNPJ e falhas de persistência.

Execute a mesma suíte usada pelo CI:

```bash
cd backend
python -m pytest -v
```

Os testes usam `pytest`, `TestClient` e `jsonschema`; cobrem filtros combinados,
busca nos três campos, limites, paginação, ordenação com empates e fusos horários,
fichas completas/incompletas, escrita, documentos, autenticação e isolamento de
HOTEL. As fixtures de escrita reutilizam o seed, injetam um repositório por teste
e storage em `tmp_path`, sem modificar os mocks nem criar arquivos no repositório.
