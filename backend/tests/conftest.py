import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app import main
from app.document_storage import LocalDocumentStorage, document_storage
from app.inventory import JsonInventoryRepository
from app.inventory_repository import MemoryInventoryRepository


@pytest.fixture
def write_env(tmp_path, monkeypatch):
    repository = MemoryInventoryRepository(JsonInventoryRepository(main.SEED_FILE))
    storage = LocalDocumentStorage(tmp_path / "files", max_bytes=1024)
    monkeypatch.setitem(main.app.dependency_overrides, main.inventory_repository, lambda: repository)
    monkeypatch.setitem(main.app.dependency_overrides, document_storage, lambda: storage)
    monkeypatch.setattr(main, "AUDIT_LOG", [])
    seed_bytes = main.SEED_FILE.read_bytes()
    contract = json.loads(main.OPENAPI_FILE.read_text(encoding="utf-8"))

    def validate(response, path, method):
        schema = contract["paths"][path][method]["responses"][str(response.status_code)]["content"]["application/json"]["schema"]
        Draft202012Validator({**schema, "components": contract["components"]},
                             format_checker=FormatChecker()).validate(response.json())

    def headers(role):
        token = {"ADMINISTRADOR": "admin-token", "EDITOR": "editor-token",
                 "GESTOR": "gestor-token", "HOTEL": "hotel-501-token"}[role]
        return {"Authorization": f"Bearer {token}"}

    with TestClient(main.app, headers=headers("ADMINISTRADOR")) as client:
        yield SimpleNamespace(client=client, repository=repository, storage=storage,
                              items=repository.establishments(), headers=headers, validate=validate,
                              audit=main.AUDIT_LOG)
    assert main.SEED_FILE.read_bytes() == seed_bytes


@pytest.fixture
def create_payload():
    return {"id_categoria": 1, "nome_fantasia": "Hotel Novo", "razao_social": "Hotel Novo Ltda.",
            "cnpj": "11.222.333/0001-81", "endereco": "Rua dos Testes, 123"}
