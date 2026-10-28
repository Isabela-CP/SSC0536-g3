# Backend — Inventário OTO

Base FastAPI para a API do Inventário OTO. No estágio inicial, ela entrega as
respostas de leitura a partir de `../contratos_api_oto/mocks/seed-data.json`;
assim contrato, mock e API não divergem durante o desenvolvimento do frontend.

## Executar

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

A API estará em `http://localhost:8000`; a documentação interativa é
`http://localhost:8000/docs`.

## Rotas já disponíveis

- `GET /health`
- `GET /categorias-estabelecimento`
- `GET /estabelecimentos` (busca, filtros básicos e paginação)
- `GET /estabelecimentos/{id_estabelecimento}`
- `GET /estabelecimentos/{id_estabelecimento}/documentos`
- `GET /estabelecimentos/{id_estabelecimento}/documentos/{id_documento}`

Além das consultas de estabelecimentos, a base de demonstração inclui:

- `POST /auth/login`, `POST /auth/logout` e `POST /auth/recuperacao-senha`
- `GET|PATCH /perfil`, `GET|POST /usuarios` e fluxos de `POST /convites`
- `GET|POST /pesquisas-ocupacao`, `PATCH /pesquisas-ocupacao/{id_pesquisa}`, encerramento, pendências e respostas de ocupação
- `POST /relatorios`, `GET /relatorios/{id_relatorio}`, `GET /relatorios/{id_relatorio}/arquivo`, `GET /auditoria` e `GET /dashboard`

Os dados desses novos módulos são mantidos apenas em memória para demonstrar
os contratos e seus fluxos. As credenciais locais são
`marina.admin@example.test` / `admin-demo`,
`rafael.consulta@example.test` / `gestor-demo` e
`camila.editora@example.test` / `editor-demo`; os tokens retornados podem ser
enviados como `Authorization: Bearer <token>`.

As rotas de escrita, autenticação, autorização e arquivos seguem documentadas
em `../contratos_api_oto/openapi.json`, mas ainda não foram implementadas nesta
base inicial.
