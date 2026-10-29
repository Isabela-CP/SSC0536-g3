# SSC0536-g3 — OTO Hospedagem

Plataforma web do Grupo 3 (disciplina **SSC0536**). Frontend em **React + Vite**. Visão geral e comandos: veja [README.md](README.md).

## Estrutura

- `frontend/`: app React + Vite (`src/`, `package.json`).
- `pr_reviewing/`: histórico de reviews (`<pr-number>.md`).
- `.github/review/REVIEW_GUIDE.md`: **fonte única** de critérios e formato de review.
- `.github/scripts/review_pr.py` e `.github/workflows/pr-review.yml`: automação de review com IA.
- `.github/pull_request_template.md`: template obrigatório de PR.
- `.gemini/skills/review-pr/`: skill para revisar PRs localmente (aponta para o guia).

## Comandos (a partir de `frontend/`)

```bash
npm install
npm run dev
npm run build     # deve passar sem erros antes do merge
npm run preview
```

## Fluxo de PR

1. Preencha o template: descrição, `Closes #<numero>`, prints/Figma.
2. Review com IA: automático no PR, ou `/review-pr <numero-ou-branch>` localmente. Siga `.github/review/REVIEW_GUIDE.md`.
3. Qualidade: `npm run build` limpo; componentes com responsabilidades bem delimitadas; evitar estados/efeitos desnecessários.
