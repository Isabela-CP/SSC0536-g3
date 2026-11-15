# Executor das suítes com as mesmas versões do CI (.github/workflows/ci.yml): Python 3.11 e Node.js 20.
# Construa a partir da raiz do repositório:
#   docker build -t oto-qa-regressao -f testes_integracao_regressao/Dockerfile .
FROM node:20-bookworm-slim AS node
FROM python:3.11-slim
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
