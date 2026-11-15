"""Massa de dados, dublês de serviços externos e utilitários dos testes de integração.

Os dublês substituem apenas o que não pode ser exercitado localmente com o serviço real
(Supabase Storage e Brevo, que exigem conta e rede externa). Banco, SMTP (Mailpit),
sistema de arquivos e o código do frontend são reais.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

# --------------------------------------------------------------------- massa de dados (seed)
SENHAS = {"ADMINISTRADOR": "admin-demo", "GESTOR": "gestor-demo", "EDITOR": "editor-demo", "HOTEL": "hotel-demo"}
CONTAS = {
    "ADMINISTRADOR": "marina.admin@example.test",
    "GESTOR": "rafael.consulta@example.test",
    "EDITOR": "camila.editora@example.test",
    "HOTEL": "responsavel@serra-azul.example",          # vínculo: Hotel Serra Azul
    "HOTEL_IPE": "responsavel@ipe-amarelo.example",      # vínculo: Pousada Ipê Amarelo
    "EDITOR_PENDENTE": "juliana.editor@example.test",    # conta PENDENTE (sem convite aceito)
}
SERRA_AZUL = "11111111-1111-4111-8111-111111111111"
IPE_AMARELO = "22222222-2222-4222-8222-222222222222"
CNPJ_LIVRE = "11.222.333/0001-81"
PESQUISA_CONSOLIDADO_ABERTA = "3"   # Serra Azul já respondeu
PESQUISA_EXPECTATIVA_ABERTA = "4"   # sem respostas
PDF_MINIMO = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
CHAVE_SUPABASE = "sb_secret_integracao_qa_0123456789"


def novo_estabelecimento(**extra) -> dict:
    return {"id_categoria": 1, "nome_fantasia": "Hotel Integração", "razao_social": "Hotel Integração Ltda.",
            "cnpj": CNPJ_LIVRE, "endereco": "Rua dos Testes, 100, Olímpia - SP", **extra}


def nova_pesquisa(**extra) -> dict:
    return {"titulo": "Pesquisa de integração", "tipo": "CONSOLIDADO", "periodo_inicio": "2026-12-01",
            "periodo_fim": "2026-12-15", "estabelecimentos": [SERRA_AZUL, IPE_AMARELO], **extra}


def enviar_documento(cliente, conteudo=PDF_MINIMO, nome="alvara.pdf", tipo="application/pdf", id_estab=SERRA_AZUL):
    return cliente.post(f"/estabelecimentos/{id_estab}/documentos",
                        data={"tipo_documento": "ALVARA", "data_vencimento": "2030-01-31"},
                        files={"arquivo": (nome, conteudo, tipo)})


def defeito(codigo: str, motivo: str):
    """Teste que evidencia defeito: falha esperada estrita (XPASS indica correção)."""
    def aplicar(func):
        func = pytest.mark.defeito(codigo)(func)
        # raises=AssertionError: só a falha do oráculo conta como defeito; qualquer outra exceção é falha real.
        return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{codigo}: {motivo}")(func)
    return aplicar


# --------------------------------------------------------------------- Mailpit (SMTP real)
class Mailpit:
    """Cliente da API HTTP do Mailpit, que recebe as mensagens pelo SMTP real."""

    def __init__(self, url: str, smtp: str):
        self.url = url.rstrip("/")
        self.smtp_host, _, porta = smtp.partition(":")
        self.smtp_porta = int(porta or 1025)
        self.http = httpx.Client(base_url=self.url, timeout=10)

    def limpar(self):
        self.http.delete("/api/v1/messages").raise_for_status()

    def mensagens(self) -> list[dict]:
        resposta = self.http.get("/api/v1/messages", params={"limit": 500})
        resposta.raise_for_status()
        return resposta.json()["messages"]

    def para(self, email: str) -> list[dict]:
        return [m for m in self.mensagens() if any(t["Address"].casefold() == email.casefold() for t in m["To"])]

    def texto(self, mensagem: dict) -> str:
        return self.http.get(f"/api/v1/message/{mensagem['ID']}").json()["Text"]

    def esperar(self, email: str, quantidade: int = 1, segundos: float = 20) -> list[dict]:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            achadas = self.para(email)
            if len(achadas) >= quantidade:
                return achadas
            time.sleep(0.3)
        return self.para(email)


# --------------------------------------------------------------------- dublê do Supabase Storage
class SupabaseFalso:
    """Implementa as rotas da Storage API usadas pelo backend (upload, download autenticado e remoção).

    Guarda os objetos em memória, registra cada requisição e permite simular indisponibilidade.
    """

    PREFIXO = "/storage/v1/object/"

    def __init__(self, chave: str = CHAVE_SUPABASE, bucket: str = "oto-arquivos"):
        self.chave, self.bucket = chave, bucket
        self.objetos: dict[str, tuple[bytes, str]] = {}
        self.requisicoes: list[SimpleNamespace] = []
        self.falhar: set[str] = set()       # métodos HTTP que devolvem 500

    def __call__(self, environ, start_response):
        metodo, caminho = environ["REQUEST_METHOD"], environ["PATH_INFO"]
        cabecalhos = {k[5:].replace("_", "-").lower(): v for k, v in environ.items() if k.startswith("HTTP_")}
        if environ.get("CONTENT_TYPE"):
            cabecalhos["content-type"] = environ["CONTENT_TYPE"]
        corpo = environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH") or 0))
        self.requisicoes.append(SimpleNamespace(metodo=metodo, caminho=caminho, cabecalhos=cabecalhos))

        def responder(status, dados=b"", tipo="application/json"):
            start_response(status, [("Content-Type", tipo), ("Content-Length", str(len(dados)))])
            return [dados]

        if metodo in self.falhar:
            return responder("500 Internal Server Error", b'{"message":"falha interna simulada"}')
        if cabecalhos.get("apikey") != self.chave or not caminho.startswith(self.PREFIXO):
            return responder("401 Unauthorized", b'{"message":"Invalid key"}')
        rota = caminho[len(self.PREFIXO):]
        if rota.startswith("authenticated/"):
            rota = rota[len("authenticated/"):]
        bucket, _, objeto = rota.partition("/")
        if bucket != self.bucket:
            return responder("404 Not Found", b'{"message":"Bucket not found"}')
        if metodo == "POST":
            if objeto in self.objetos:
                return responder("409 Conflict", b'{"message":"exists"}')
            self.objetos[objeto] = (corpo, cabecalhos.get("content-type", ""))
            return responder("200 OK", json.dumps({"Key": f"{bucket}/{objeto}"}).encode())
        if metodo == "GET":
            if objeto not in self.objetos:
                return responder("404 Not Found", b'{"message":"Object not found"}')
            dados, tipo = self.objetos[objeto]
            return responder("200 OK", dados, tipo)
        if metodo == "DELETE":
            if self.objetos.pop(objeto, None) is None:
                return responder("404 Not Found", b'{"message":"Object not found"}')
            return responder("200 OK", b"{}")
        return responder("405 Method Not Allowed")

    def chaves(self, prefixo: str) -> set[str]:
        return {k for k in self.objetos if k.startswith(prefixo + "/")}


# --------------------------------------------------------------------- dublê do Brevo
class BrevoFalso:
    """Substitui o POST HTTPS à API transacional do Brevo, registrando cada chamada."""

    def __init__(self):
        self.chamadas: list[dict] = []
        self.status = 201

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.chamadas.append({"url": url, "headers": headers or {}, "json": json, "timeout": timeout})
        requisicao = httpx.Request("POST", url)
        return httpx.Response(self.status, request=requisicao, json={"messageId": "<qa@brevo>"})


# --------------------------------------------------------------------- rede do banco controlável
class ProxyTCP:
    """Proxy TCP entre a API e o PostgreSQL; `derrubar()` simula a perda de rede do banco."""

    def __init__(self, destino: tuple[str, int]):
        self.destino = destino
        self.servidor = socket.create_server(("127.0.0.1", 0))
        self.porta = self.servidor.getsockname()[1]
        self.disponivel = True
        self.abertas: list[socket.socket] = []
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while True:
            try:
                cliente, _ = self.servidor.accept()
            except OSError:
                return
            if not self.disponivel:
                cliente.close()
                continue
            try:
                banco = socket.create_connection(self.destino, timeout=5)
            except OSError:
                cliente.close()
                continue
            self.abertas += [cliente, banco]
            for origem, alvo in ((cliente, banco), (banco, cliente)):
                threading.Thread(target=self._copiar, args=(origem, alvo), daemon=True).start()

    @staticmethod
    def _copiar(origem, alvo):
        try:
            while dados := origem.recv(65536):
                alvo.sendall(dados)
        except OSError:
            pass
        finally:
            for s in (origem, alvo):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def derrubar(self):
        self.disponivel = False
        for s in self.abertas:
            try:
                s.close()
            except OSError:
                pass
        self.abertas.clear()

    def restaurar(self):
        self.disponivel = True

    def fechar(self):
        self.derrubar()
        self.servidor.close()


def porta_fechada() -> int:
    """Porta local sem nenhum serviço escutando (para simular SMTP/banco fora do ar)."""
    with socket.create_server(("127.0.0.1", 0)) as s:
        return s.getsockname()[1]


def env_obrigatoria(nome: str) -> str:
    valor = os.getenv(nome)
    if not valor:
        raise pytest.UsageError(f"Configure {nome} (veja testes_integracao_regressao/README.md).")
    return valor
