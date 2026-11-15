#!/usr/bin/env bash
# Executa as suítes automatizadas de uma árvore de código e grava a saída e o JUnit XML de cada uma.
# Roda dentro da imagem oto-qa-regressao (Python 3.11 + Node 20), com PostgreSQL e Mailpit de testes.
#
# Uso: executar_suites.sh <raiz-do-codigo> <dir-de-saida> [--sem-hospedagem]
#   --sem-hospedagem  exclui os testes de integração de recursos criados no PR #39 (regressão entre versões)
# Requer: OTO_TEST_ADMIN_URL, OTO_TEST_MAILPIT_URL, OTO_TEST_SMTP; frontend/node_modules instalado.
set -u
RAIZ=$(cd "$1" && pwd)
SAIDA=$(mkdir -p "$2" && cd "$2" && pwd)
FILTRO=()
[ "${3:-}" = "--sem-hospedagem" ] && FILTRO=(-m "not hospedagem")
PYTEST=(python -m pytest -p no:cacheprovider -q -rxX)

resumo() { printf '%-12s %s\n' "$1" "$(grep -E '(passed|failed|error)' "$SAIDA/$1.txt" | tail -1)"; }

cd "$RAIZ/backend"   && "${PYTEST[@]}" --junitxml="$SAIDA/backend.xml" > "$SAIDA/backend.txt" 2>&1;            resumo backend
cd "$RAIZ/frontend"  && node --test --test-reporter=tap --test-reporter-destination="$SAIDA/frontend.txt" \
                          --test-reporter=junit --test-reporter-destination="$SAIDA/frontend.xml" src/*.test.js
printf '%-12s %s\n' frontend "$(grep -E '^# (pass|fail) ' "$SAIDA/frontend.txt" | tr '\n' ' ')"
cd "$RAIZ"
if [ -d testes_funcionais ]; then
  "${PYTEST[@]}" testes_funcionais --ignore=testes_funcionais/e2e --junitxml="$SAIDA/funcionais.xml" > "$SAIDA/funcionais.txt" 2>&1
  resumo funcionais
fi
"${PYTEST[@]}" testes_integracao_regressao/integracao "${FILTRO[@]}" --junitxml="$SAIDA/integracao.xml" > "$SAIDA/integracao.txt" 2>&1
resumo integracao
