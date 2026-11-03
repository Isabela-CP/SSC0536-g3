"""Consultas do inventário, independentes do transporte HTTP e do armazenamento."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class InventoryRepository(Protocol):
    """Uma implementação PostgreSQL pode substituir o adaptador JSON."""

    def categories(self) -> list[dict]: ...

    def establishments(self) -> list[dict]: ...

    def establishment(self, establishment_id: str) -> dict | None: ...


class JsonInventoryRepository:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict:
        with self.path.open(encoding="utf-8") as file:
            return json.load(file)

    def categories(self) -> list[dict]:
        return self._read()["categorias_estabelecimento"]

    def establishments(self) -> list[dict]:
        return self._read()["estabelecimentos"]

    def establishment(self, establishment_id: str) -> dict | None:
        return next((item for item in self.establishments()
                     if item["id_estabelecimento"] == establishment_id), None)


@dataclass(frozen=True)
class InventoryQuery:
    busca: str | None = None
    id_categoria: int | None = None
    status: str | None = None
    cadastur_status: str | None = None
    aceita_pesquisas: bool | None = None
    page: int = 1
    page_size: int = 20
    ordenar_por: str = "nome_fantasia"
    ordem: str = "asc"


SUMMARY_FIELDS = (
    "id_estabelecimento", "id_categoria", "nome_fantasia", "razao_social",
    "cnpj", "bairro", "status", "cadastur_status", "possui_cadastur",
    "aceita_pesquisas", "latitude", "longitude",
)


def query_establishments(
    repository: InventoryRepository,
    query: InventoryQuery,
    establishment_scope: str | None = None,
) -> dict:
    items = repository.establishments()
    # O escopo vem da conta autenticada, nunca de parâmetros do cliente.
    if establishment_scope is not None:
        items = [item for item in items if item["id_estabelecimento"] == establishment_scope]
    if query.busca:
        term = query.busca.casefold()
        items = [item for item in items if any(
            term in (item.get(field) or "").casefold()
            for field in ("nome_fantasia", "razao_social", "cnpj")
        )]
    for field in ("id_categoria", "status", "cadastur_status", "aceita_pesquisas"):
        value = getattr(query, field)
        if value is not None:
            items = [item for item in items if item.get(field) == value]

    # Desempate por UUID ascendente, inclusive na ordenação principal descendente.
    items = sorted(items, key=lambda item: item["id_estabelecimento"])
    def sort_key(item: dict):
        value = item[query.ordenar_por]
        if query.ordenar_por == "nome_fantasia":
            return value.casefold()
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    items.sort(key=sort_key, reverse=query.ordem == "desc")
    total = len(items)
    start = (query.page - 1) * query.page_size
    return {
        "data": [{key: item[key] for key in SUMMARY_FIELDS if key in item}
                 for item in items[start:start + query.page_size]],
        "pagination": {
            "page": query.page, "page_size": query.page_size, "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        },
    }
