"""Repositório mutável de desenvolvimento; o seed original permanece intacto."""
from contextlib import contextmanager
from copy import deepcopy
from threading import RLock
from typing import ContextManager, Protocol

from app.inventory import InventoryRepository


class WritableInventoryRepository(InventoryRepository, Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def save(self, establishment: dict) -> None: ...

    def next_document_id(self) -> int: ...

    def file_reference(self, document_id: int) -> str | None: ...

    def set_file_reference(self, document_id: int, key: str) -> None: ...


class MemoryInventoryRepository:
    """Snapshot isolado, com rollback e transações serializadas no processo.

    PostgreSQL deverá implementar este protocolo com transações e UNIQUE para
    CNPJ normalizado. Nenhum binário ou chave interna é incluído na ficha pública.
    """
    def __init__(self, source: InventoryRepository):
        self._categories = deepcopy(source.categories())
        self._items = {item["id_estabelecimento"]: deepcopy(item) for item in source.establishments()}
        self._files: dict[int, str] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self):
        with self._lock:
            items, files = deepcopy(self._items), self._files.copy()
            try:
                yield
            except Exception:
                self._items, self._files = items, files
                raise

    def categories(self) -> list[dict]:
        with self._lock:
            return deepcopy(self._categories)

    def establishments(self) -> list[dict]:
        with self._lock:
            return deepcopy(list(self._items.values()))

    def establishment(self, establishment_id: str) -> dict | None:
        with self._lock:
            return deepcopy(self._items.get(establishment_id))

    def save(self, establishment: dict) -> None:
        with self._lock:
            self._items[establishment["id_estabelecimento"]] = deepcopy(establishment)

    def next_document_id(self) -> int:
        with self._lock:
            return max((doc["id_documento"] for item in self._items.values()
                        for doc in item.get("documentos", [])), default=0) + 1

    def file_reference(self, document_id: int) -> str | None:
        with self._lock:
            return self._files.get(document_id)

    def set_file_reference(self, document_id: int, key: str) -> None:
        with self._lock:
            self._files[document_id] = key
