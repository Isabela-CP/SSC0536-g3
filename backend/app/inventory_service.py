"""Regras de escrita do inventário; persistência, storage e auditoria são injetados."""
from copy import deepcopy
from datetime import datetime, timezone
import logging
import re
from typing import BinaryIO, Callable
from uuid import uuid4

from app.document_storage import DocumentStorage
from app.inventory_errors import InventoryError, invalid_field
from app.inventory_repository import WritableInventoryRepository


logger = logging.getLogger(__name__)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cnpj_digits(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def valid_cnpj(value: str) -> bool:
    digits = cnpj_digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    numbers = list(map(int, digits))
    for length, weights in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
                            (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        remainder = sum(number * weight for number, weight in zip(numbers[:length], weights)) % 11
        if numbers[length] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True


def authorize(actor: dict, establishment_id: str | None = None, *, admin_only: bool = False, read: bool = False):
    roles = {"ADMINISTRADOR"} if admin_only else {"ADMINISTRADOR", "EDITOR", "HOTEL"}
    if read:
        roles.add("GESTOR")
    if actor["perfil"] not in roles or (
        actor["perfil"] == "HOTEL" and (
            not actor.get("id_estabelecimento") or actor["id_estabelecimento"] != establishment_id
        )
    ):
        raise InventoryError(403, "FORBIDDEN", "Seu perfil não pode executar esta operação.")


def check_fields(actor: dict, changes: dict):
    if actor["perfil"] != "ADMINISTRADOR" and {"cnpj", "razao_social"} & changes.keys():
        raise InventoryError(403, "FORBIDDEN", "Somente ADMINISTRADOR pode alterar CNPJ e razão social.")


def merge_changes(current: dict, changes: dict) -> dict:
    result = deepcopy(current)
    for key, value in changes.items():
        result[key] = merge_changes(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


class InventoryService:
    def __init__(self, repository: WritableInventoryRepository, audit: Callable, storage: DocumentStorage | None = None):
        self.repository, self.audit, self.storage = repository, audit, storage

    def establishment(self, establishment_id: str) -> dict:
        item = self.repository.establishment(establishment_id)
        if item is None:
            raise InventoryError(404, "NOT_FOUND", "Estabelecimento ou documento não encontrado.")
        return item

    def category(self, category_id: int) -> dict:
        category = next((item for item in self.repository.categories() if item["id_categoria"] == category_id), None)
        if category is None:
            raise invalid_field("id_categoria", "Categoria de hospedagem não encontrada.")
        return category

    def check_cnpj(self, value: str | None, establishment_id: str | None = None):
        if value is None:
            return
        if not valid_cnpj(value):
            raise invalid_field("cnpj", "CNPJ inválido.")
        if any(item["id_estabelecimento"] != establishment_id and item.get("cnpj") and
               cnpj_digits(item["cnpj"]) == cnpj_digits(value) for item in self.repository.establishments()):
            raise InventoryError(409, "CONFLICT", "Já existe um estabelecimento cadastrado com esse CNPJ.")

    def create(self, actor: dict, payload: dict) -> dict:
        authorize(actor, admin_only=True)
        with self.repository.transaction():
            for field in ("razao_social", "cnpj"):
                if payload[field] is None:
                    raise invalid_field(field, "Campo obrigatório no cadastro.")
            self.check_cnpj(payload["cnpj"])
            item = {"aceita_pesquisas": True, "cadastur_status": "OBRIGATORIO", "possui_cadastur": False,
                    "meio_hospedagem": None, "infraestrutura": None, **payload,
                    "id_estabelecimento": str(uuid4()), "status": "ATIVO", "motivo_inativacao": None,
                    "criado_em": now(), "atualizado_em": now(), "documentos": [],
                    "categoria": self.category(payload["id_categoria"])}
            self.repository.save(item)
            self.audit(actor, "ESTABELECIMENTO_CRIADO", "ESTABELECIMENTO", item["id_estabelecimento"], after=item)
            return item

    def update(self, actor: dict, establishment_id: str, changes: dict) -> dict:
        authorize(actor, establishment_id)
        check_fields(actor, changes)
        with self.repository.transaction():
            before = self.establishment(establishment_id)
            if "cnpj" in changes:
                self.check_cnpj(changes["cnpj"], establishment_id)
            item = merge_changes(before, changes)
            if "id_categoria" in changes:
                item["categoria"] = self.category(changes["id_categoria"])
            item["atualizado_em"] = now()
            self.repository.save(item)
            self.audit(actor, "ESTABELECIMENTO_ATUALIZADO", "ESTABELECIMENTO", establishment_id, before, item)
            return item

    def change_status(self, actor: dict, establishment_id: str, active: bool, reason: str | None = None) -> dict:
        authorize(actor, admin_only=True)
        with self.repository.transaction():
            before = self.establishment(establishment_id)
            target = "ATIVO" if active else "INATIVO"
            if before["status"] == target:
                raise InventoryError(409, f"ESTABELECIMENTO_JA_{target}",
                                     f"O estabelecimento já está {target.lower()}.")
            item = {**before, "status": target, "motivo_inativacao": None if active else reason,
                    "atualizado_em": now()}
            self.repository.save(item)
            action = "ESTABELECIMENTO_REATIVADO" if active else "ESTABELECIMENTO_INATIVADO"
            self.audit(actor, action, "ESTABELECIMENTO", establishment_id, before, item)
            return item

    @staticmethod
    def document(item: dict, document_id: int) -> dict:
        document = next((doc for doc in item.get("documentos", []) if doc["id_documento"] == document_id), None)
        if document is None:
            raise InventoryError(404, "NOT_FOUND", "Estabelecimento ou documento não encontrado.")
        return document

    @staticmethod
    def document_status(expiration: str) -> str:
        days = (datetime.fromisoformat(expiration).date() - datetime.now(timezone.utc).date()).days
        return "VENCIDO" if days < 0 else "A_VENCER" if days <= 30 else "REGULAR"

    def discard_file(self, key: str):
        try:
            self.storage.delete(key)
        except OSError:
            logger.exception("Não foi possível remover arquivo sem referência.")

    def upload(self, actor: dict, establishment_id: str, payload: dict, stream: BinaryIO, filename: str, mime: str) -> dict:
        authorize(actor, establishment_id)
        with self.repository.transaction():
            item = self.establishment(establishment_id)
            stored = self.storage.save(stream, filename, mime)
            try:
                document = {**payload, "id_documento": self.repository.next_document_id(),
                            "id_estabelecimento": establishment_id,
                            "status": self.document_status(payload["data_vencimento"]), "arquivo": stored.metadata}
                item.setdefault("documentos", []).append(document)
                item["atualizado_em"] = now()
                self.repository.save(item)
                self.repository.set_file_reference(document["id_documento"], stored.key)
                self.audit(actor, "DOCUMENTO_CRIADO", "DOCUMENTO", str(document["id_documento"]), after=document)
                return document
            except Exception:
                self.discard_file(stored.key)
                raise

    def update_document(self, actor: dict, establishment_id: str, document_id: int, changes: dict) -> dict:
        authorize(actor, establishment_id)
        with self.repository.transaction():
            item = self.establishment(establishment_id)
            document = self.document(item, document_id)
            before = deepcopy(document)
            document.update(changes)
            if "data_vencimento" in changes:
                document["status"] = self.document_status(changes["data_vencimento"])
            item["atualizado_em"] = now()
            self.repository.save(item)
            self.audit(actor, "DOCUMENTO_ATUALIZADO", "DOCUMENTO", str(document_id), before, document)
            return document

    def replace_file(self, actor: dict, establishment_id: str, document_id: int, stream: BinaryIO, filename: str, mime: str) -> dict:
        authorize(actor, establishment_id)
        with self.repository.transaction():
            item = self.establishment(establishment_id)
            document = self.document(item, document_id)
            before = deepcopy(document)
            old_key = self.repository.file_reference(document_id)
            stored = self.storage.save(stream, filename, mime)
            try:
                document["arquivo"] = stored.metadata
                item["atualizado_em"] = now()
                self.repository.save(item)
                self.repository.set_file_reference(document_id, stored.key)
                self.audit(actor, "DOCUMENTO_ARQUIVO_SUBSTITUIDO", "DOCUMENTO", str(document_id), before, document)
            except Exception:
                self.discard_file(stored.key)
                raise
        if old_key:
            self.discard_file(old_key)
        return document

    def download(self, actor: dict, establishment_id: str, document_id: int):
        authorize(actor, establishment_id, read=True)
        # Abre o arquivo ainda sob o lock para não disputar com substituições.
        with self.repository.transaction():
            item = self.establishment(establishment_id)
            document = self.document(item, document_id)
            key = self.repository.file_reference(document_id)
            if key is None:
                raise InventoryError(404, "NOT_FOUND", "Arquivo não encontrado.")
            try:
                return self.storage.open(key), document["arquivo"]
            except FileNotFoundError:
                raise InventoryError(404, "NOT_FOUND", "Arquivo não encontrado.") from None
