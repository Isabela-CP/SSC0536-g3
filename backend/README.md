# Backend — Inventário OTO

API FastAPI do Inventário OTO. As consultas usam
`../contratos_api_oto/mocks/seed-data.json` e seguem os schemas de
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

`app/inventory.py` contém o protocolo `InventoryRepository`, o adaptador JSON
e a consulta. As rotas recebem o repositório via `inventory_repository`, que
pode ser substituído por uma implementação PostgreSQL sem alterar os contratos
HTTP. A consulta não depende de migrations. A integração SQL deverá ser
validada separadamente com o núcleo de SCRUM-85.

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
seus dados em memória; as rotas de escrita do inventário e download de documentos
não fazem parte desta implementação de leitura.

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

## Plano executado e validação

1. Comparar parâmetros, perfis e estruturas de resposta com o OpenAPI.
2. Separar repositório JSON e consultas das rotas HTTP.
3. Completar filtros, ordenação, validações e autorização, incluindo HOTEL.
4. Validar contratos e comportamentos com fixtures independentes baseadas no seed.

Execute a mesma suíte usada pelo CI:

```bash
cd backend
python -m pytest -v
```

Os testes usam `pytest`, `TestClient` e `jsonschema`; cobrem filtros combinados,
busca nos três campos, limites, paginação, ordenação com empates e fusos horários,
fichas completas/incompletas, documentos, autenticação e isolamento de HOTEL.
