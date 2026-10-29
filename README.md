# SSC0536-g3 — OTO Hospedagem

Projeto do Grupo 3 da disciplina **SSC0536**: plataforma web de hospedagem com frontend em **React + Vite**.

## Como rodar
# Inventário OTO

Aplicação para gestão do inventário de meios de hospedagem. O repositório está
separado por responsabilidade para que interface, API e contrato evoluam sem
misturar dependências.

## Estrutura

```text
frontend/            Interface React + Vite
backend/             API FastAPI e testes básicos
contratos_api_oto/   Contrato OpenAPI e dados mockados
```

## Contratos e mocks

O contrato em `contratos_api_oto/openapi.json` descreve a API REST do MVP:
categorias, estabelecimentos, inativação/reativação e documentos de controle
com upload e download. Ele também documenta os perfis `ADMINISTRADOR`,
`GESTOR`, `EDITOR` e `HOTEL` e as restrições de acesso de cada um.

Os dados fictícios de desenvolvimento ficam em
`contratos_api_oto/mocks/seed-data.json`. Para facilitar o consumo no frontend,
`contratos_api_oto/mocks/responses/` contém respostas prontas de sucesso para
as leituras principais. O backend usa o `seed-data.json` como sua fonte de
verdade temporária, portanto as respostas de consulta correspondem aos mocks.

Na revisão dos dados, os quatro CNPJs são estruturalmente válidos e os campos
exigidos pelo contrato estão presentes. Há uma decisão de negócio ainda aberta:
o contrato marca um documento que vence em 34 dias como `A_VENCER`, mas não
define a janela de dias para esse status. Essa regra deve ser fechada antes das
rotas de escrita e da persistência definitiva.

Para detalhes de permissões, uploads e pendências de produto, consulte o
[README dos contratos](contratos_api_oto/README.md).

## Executar

### Frontend

```bash
cd frontend
npm install
npm run dev      # servidor local
npm run build    # build de produção (deve passar antes do merge)
```

## Contribuindo

1. Abra o PR preenchendo o template (descrição, `Closes #<issue>`, prints/Figma).
2. O workflow **AI PR Review** comenta automaticamente no PR (Gemini/OpenAI/Anthropic, conforme o secret configurado). Comente `/review` para pedir nova análise.
3. O parecer fica salvo em [`pr_reviewing/`](pr_reviewing/). Critérios: [REVIEW_GUIDE.md](.github/review/REVIEW_GUIDE.md).

A IA apenas comenta; a aprovação e o merge são sempre humanos.
npm run dev
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

O frontend é servido normalmente em `http://localhost:5173` e a documentação
da API em `http://localhost:8000/docs`.
