"""Storage local substituível, com limites de upload e chaves geradas no servidor."""
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID, uuid4

from app.inventory_errors import InventoryError, invalid_field


@dataclass(frozen=True)
class StoredFile:
    key: str
    metadata: dict


class DocumentStorage(Protocol):
    def save(self, stream: BinaryIO, filename: str, content_type: str) -> StoredFile: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...


class LocalDocumentStorage:
    TYPES = {"application/pdf": {".pdf"}, "image/jpeg": {".jpg", ".jpeg"}, "image/png": {".png"}}

    def __init__(self, root: Path, max_bytes: int = 10 * 1024 * 1024):
        if max_bytes < 1:
            raise ValueError("O limite de upload deve ser positivo.")
        self.root, self.max_bytes = root, max_bytes

    def _path(self, key: str) -> Path:
        # Apenas UUIDs gerados pelo storage são aceitos como referências.
        if str(UUID(key)) != key:
            raise ValueError("Chave de storage inválida.")
        return self.root / key

    def save(self, stream: BinaryIO, filename: str, content_type: str) -> StoredFile:
        filename = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
            raise invalid_field("arquivo", "Nome de arquivo inválido.")
        if content_type not in self.TYPES or Path(filename).suffix.lower() not in self.TYPES[content_type]:
            raise InventoryError(415, "UNSUPPORTED_MEDIA_TYPE", "Tipo de arquivo não permitido.")
        key = str(uuid4())
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        size = 0
        try:
            with path.open("xb") as output:
                while chunk := stream.read(min(64 * 1024, self.max_bytes + 1 - size)):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise InventoryError(413, "PAYLOAD_TOO_LARGE", "O arquivo excede o tamanho máximo permitido.")
                    output.write(chunk)
                if not size:
                    raise invalid_field("arquivo", "O arquivo não pode estar vazio.")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return StoredFile(key, {"nome_arquivo": filename, "content_type": content_type,
                                "tamanho_bytes": size,
                                "enviado_em": datetime.now(timezone.utc).isoformat()})

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


@lru_cache
def document_storage() -> DocumentStorage:
    return LocalDocumentStorage(
        Path(os.environ.get("OTO_STORAGE_DIR", Path.home() / ".local/share/oto/documentos")),
        int(os.environ.get("OTO_UPLOAD_MAX_BYTES", 10 * 1024 * 1024)),
    )
