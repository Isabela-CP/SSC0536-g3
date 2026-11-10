#!/usr/bin/env python3
"""
Script de Review Automático de PRs com IA para o projeto SSC0536-g3 (OTO Hospedagem).
Utiliza a API do Google Gemini (com fallback para OpenAI ou Anthropic conforme variáveis de ambiente).
"""

import os
import sys
import json
import urllib.request
import urllib.error

GUIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "review", "REVIEW_GUIDE.md")


def load_system_prompt() -> str:
    """Lê o guia único de review (fonte da verdade para critérios e formato)."""
    with open(GUIDE_PATH, "r", encoding="utf-8") as f:
        return f.read()


SYSTEM_PROMPT = load_system_prompt()


def call_anthropic(prompt: str, api_key: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 2048,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}]
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["content"][0]["text"]

def call_openai(prompt: str, api_key: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

def call_gemini(prompt: str, api_key: str) -> str:
    api_key = api_key.strip()
    # Modelos ativos no Free Tier do Google AI Studio (3.1-flash-lite e 3.5-flash com fallback)
    models = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-flash-latest"]
    last_error = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            }
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            last_error = e
            # Se for 404 (modelo descontinuado) ou 503/429 (sobrecarga temporária), tenta o próximo modelo
            if e.code in (404, 429, 503):
                continue
            # Se for erro 400 ou 403 (chave inválida ou permissão), extrai o detalhe do Google
            try:
                body = json.loads(e.read().decode("utf-8"))
                msg = body.get("error", {}).get("message", str(e))
                raise RuntimeError(f"Erro na API do Google ({e.code}): {msg}") from e
            except Exception:
                raise e

    if last_error:
        try:
            body = json.loads(last_error.read().decode("utf-8"))
            msg = body.get("error", {}).get("message", str(last_error))
            raise RuntimeError(f"Erro na API do Google ({last_error.code}): {msg}") from last_error
        except Exception:
            raise last_error
    raise RuntimeError("Nenhum modelo Gemini respondeu com sucesso.")

def main():
    diff_file = sys.argv[1] if len(sys.argv) > 1 else "diff.txt"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "review.md"

    pr_number = os.getenv("PR_NUMBER", "N/A")
    pr_title = os.getenv("PR_TITLE", "Pull Request")
    source_branch = os.getenv("PR_BRANCH", "feature")
    target_branch = os.getenv("TARGET_BRANCH", "main")
    build_status = os.getenv("BUILD_STATUS", "Não verificado")
    issue_info = os.getenv("ISSUE_INFO", "Verificar descrição do PR")

    diff_content = ""
    if os.path.exists(diff_file):
        with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
            diff_content = f.read()

    # Limita o tamanho do diff para evitar estouro de tokens
    max_chars = 30000
    if len(diff_content) > max_chars:
        diff_content = diff_content[:max_chars] + "\n\n... [Diff truncado devido ao tamanho elevado] ..."

    prompt = f"""Informações do Pull Request:
- PR: #{pr_number}
- Título: {pr_title}
- Branch: {source_branch} -> {target_branch}
- Status de Build: {build_status}
- Issue: {issue_info}

Diff das alterações:
```diff
{diff_content}
```

Analise o diff acima e gere o parecer no formato especificado.
"""

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    review_text = ""
    try:
        if anthropic_key:
            review_text = call_anthropic(prompt, anthropic_key)
        elif openai_key:
            review_text = call_openai(prompt, openai_key)
        elif gemini_key:
            review_text = call_gemini(prompt, gemini_key)
        else:
            review_text = f"""# PR #{pr_number} — {pr_title}

> [!WARNING]
> Nenhuma chave de API de IA configurada nos Secrets do repositório (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` ou `GEMINI_API_KEY`).
> Configure ao menos uma delas nas configurações de Actions do GitHub para ativar as análises automáticas completas.

**Status do Build:** {build_status}
"""
    except Exception as e:
        review_text = f"""# PR #{pr_number} — {pr_title}

> [!ERROR]
> Ocorreu um erro ao consultar a IA para o review: `{str(e)}`

**Status do Build:** {build_status}
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(review_text)

    print(f"Revisão gerada com sucesso em: {output_file}")

if __name__ == "__main__":
    main()
