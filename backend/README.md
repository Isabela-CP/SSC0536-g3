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

As rotas de escrita, autenticação, autorização e arquivos seguem documentadas
em `../contratos_api_oto/openapi.json`, mas ainda não foram implementadas nesta
base inicial.
