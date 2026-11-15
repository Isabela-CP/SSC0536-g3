"""Controle da stack Docker descartável (projeto compose próprio) e cliente HTTP pelo Nginx."""
from __future__ import annotations

import os
import random
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = Path(__file__).with_name("stack-int.env")
SENHAS = {"ADMINISTRADOR": "admin-demo", "GESTOR": "gestor-demo", "EDITOR": "editor-demo", "HOTEL": "hotel-demo"}
CONTAS = {"ADMINISTRADOR": "marina.admin@example.test", "GESTOR": "rafael.consulta@example.test",
          "EDITOR": "camila.editora@example.test", "HOTEL": "responsavel@serra-azul.example"}
SERRA_AZUL = "11111111-1111-4111-8111-111111111111"
PDF = b"%PDF-1.4\nstack de integracao\n%%EOF\n"


def cnpj_unico() -> str:
    base = [random.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        resto = sum(d * p for d, p in zip(base, pesos)) % 11
        base.append(0 if resto < 2 else 11 - resto)
    d = "".join(map(str, base))
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


class Stack:
    def __init__(self):
        self.base = os.environ["OTO_STACK_URL"].rstrip("/")
        self.mailpit_url = os.environ["OTO_STACK_MAILPIT"].rstrip("/")
        self.projeto = os.getenv("OTO_STACK_PROJETO", "oto-int")

    # ---------------------------------------------------------------- docker compose
    def compose(self, *args: str, timeout: int = 300) -> str:
        comando = ["docker", "compose", "-p", self.projeto, "--env-file", str(ENV_FILE), *args]
        processo = subprocess.run(comando, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        assert processo.returncode == 0, f"{' '.join(comando)}\n{processo.stderr[-2000:]}"
        return processo.stdout

    def iniciado_em(self, servico: str) -> str:
        conteiner = self.compose("ps", "-q", servico).strip()
        return subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", conteiner],
                              capture_output=True, text=True, check=True).stdout.strip()

    def sql(self, consulta: str) -> str:
        return self.compose("exec", "-T", "db", "psql", "-U", "oto_owner", "-d", "oto", "-At", "-c", consulta).strip()

    # ---------------------------------------------------------------- HTTP pelo Nginx
    def http(self, token: str | None = None) -> httpx.Client:
        cabecalhos = {"Authorization": "Bearer " + token} if token else {}
        return httpx.Client(base_url=self.base + "/api", headers=cabecalhos, timeout=20)

    def token(self, perfil: str) -> str:
        resposta = self.http().post("/auth/login", json={"email": CONTAS[perfil], "senha": SENHAS[perfil]})
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["access_token"]

    def cliente(self, perfil: str) -> httpx.Client:
        return self.http(self.token(perfil))

    def esperar_saude(self, segundos: float = 90) -> float:
        inicio = time.monotonic()
        while time.monotonic() - inicio < segundos:
            try:
                if self.http().get("/health").status_code == 200:
                    return time.monotonic() - inicio
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise AssertionError("a API não voltou a responder /health")

    # ---------------------------------------------------------------- Mailpit
    def _mailpit(self, caminho: str, **params) -> dict:
        # Conexão nova a cada consulta: o Mailpit pode ter sido reiniciado pelo próprio cenário.
        with httpx.Client(base_url=self.mailpit_url, timeout=10) as cliente:
            return cliente.get(caminho, params=params).json()

    def emails_para(self, email: str) -> list[dict]:
        mensagens = self._mailpit("/api/v1/messages", limit=500)["messages"]
        return [m for m in mensagens if any(t["Address"].casefold() == email.casefold() for t in m["To"])]

    def esperar_email(self, email: str, segundos: float = 30) -> list[dict]:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            try:
                if achados := self.emails_para(email):
                    return achados
            except httpx.HTTPError:          # Mailpit ainda voltando
                pass
            time.sleep(1)
        return []

    def texto(self, mensagem: dict) -> str:
        return self._mailpit(f"/api/v1/message/{mensagem['ID']}")["Text"]
