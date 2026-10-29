---
name: review-pr
description: Revisa um Pull Request com foco em arquitetura, integridade do frontend (React/Vite) e itens bloqueantes. Use quando o usuário fornecer o número de um PR ou nome de branch, ou pedir para re-revisar um PR.
---

# Review de PR — SSC0536-g3 (OTO Hospedagem)

Critérios, formato do relatório e vereditos estão em **`.github/review/REVIEW_GUIDE.md`** (fonte única). Leia esse arquivo antes de revisar e siga-o à risca.

## Como executar

1. **Obter as alterações:** se faltar número/branch, pergunte ao usuário. Depois:
   ```bash
   git fetch origin
   git diff origin/<target>...origin/<branch>
   git merge-tree --write-tree origin/<target> origin/<branch>   # checa conflitos
   ```
2. **Entender o escopo:** commits, título e descrição; confira o `.github/pull_request_template.md`.
3. **Validar o frontend:**
   ```bash
   cd frontend && npm run build
   ```
4. **Gerar a revisão** no formato do guia e salvar em `pr_reviewing/<pr-number>.md`.
5. **Resumir no chat** em até 30 segundos, com o veredito.
