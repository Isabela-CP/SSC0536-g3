from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


ROOT_DIR = Path(__file__).resolve().parents[2]
SEED_FILE = ROOT_DIR / "contratos_api_oto" / "mocks" / "seed-data.json"

app = FastAPI(
    title="Inventário OTO",
    version="0.1.0",
    description="Base FastAPI que entrega respostas mockadas do contrato OTO.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def seed_data() -> dict:
    """Lê a fonte única de dados de desenvolvimento a cada requisição."""
    with SEED_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def find_establishment(establishment_id: str) -> dict:
    for establishment in seed_data()["estabelecimentos"]:
        if establishment["id_estabelecimento"] == establishment_id:
            return establishment
    raise HTTPException(status_code=404, detail="Estabelecimento não encontrado.")


@app.get("/health", tags=["Sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/categorias-estabelecimento", tags=["Categorias"])
def list_categories() -> dict:
    return {"data": seed_data()["categorias_estabelecimento"]}


@app.get("/estabelecimentos", tags=["Estabelecimentos"])
def list_establishments(
    busca: str | None = None,
    status: str | None = None,
    id_categoria: int | None = None,
    aceita_pesquisas: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    establishments = seed_data()["estabelecimentos"]
    if busca:
        term = busca.casefold()
        establishments = [
            item for item in establishments
            if term in " ".join(
                [item["nome_fantasia"], item["razao_social"], item["cnpj"]]
            ).casefold()
        ]
    if status:
        establishments = [item for item in establishments if item["status"] == status]
    if id_categoria:
        establishments = [item for item in establishments if item["id_categoria"] == id_categoria]
    if aceita_pesquisas is not None:
        establishments = [
            item for item in establishments if item["aceita_pesquisas"] == aceita_pesquisas
        ]

    total = len(establishments)
    start = (page - 1) * page_size
    summaries = [
        {
            key: item[key]
            for key in (
                "id_estabelecimento", "id_categoria", "nome_fantasia", "razao_social",
                "cnpj", "bairro", "status", "cadastur_status", "possui_cadastur",
                "aceita_pesquisas", "latitude", "longitude",
            )
        }
        for item in establishments[start : start + page_size]
    ]
    return {
        "data": summaries,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@app.get("/estabelecimentos/{id_estabelecimento}", tags=["Estabelecimentos"])
def get_establishment(id_estabelecimento: str) -> dict:
    return find_establishment(id_estabelecimento)


@app.get("/estabelecimentos/{id_estabelecimento}/documentos", tags=["Documentos"])
def list_documents(id_estabelecimento: str) -> dict:
    return {"data": find_establishment(id_estabelecimento)["documentos"]}


