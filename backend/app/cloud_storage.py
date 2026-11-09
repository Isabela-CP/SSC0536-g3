"""Arquivos privados no Supabase; a chave de serviço nunca vai ao navegador."""
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import SpooledTemporaryFile
from uuid import UUID, uuid4

import httpx

from app.document_storage import LocalDocumentStorage, StoredFile
from app.inventory_errors import InventoryError, invalid_field


class SupabaseStorage:
    def __init__(self, url, key, bucket, prefix, max_bytes, types=None, client=None):
        if not url.startswith('https://') or not key or not bucket:
            raise RuntimeError('Configure URL HTTPS, chave e bucket privado do Supabase.')
        if not bucket.replace('-', '').replace('_', '').isalnum() or max_bytes < 1:
            raise RuntimeError('Bucket ou limite de storage inválido.')
        self.url = url.rstrip('/') + '/storage/v1/object'
        self.headers = {'Authorization': 'Bearer ' + key, 'apikey': key}
        self.bucket, self.prefix, self.max_bytes = bucket, prefix, max_bytes
        self.types = types or LocalDocumentStorage.TYPES
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def _url(self, key, download=False):
        if str(UUID(key)) != key:
            raise ValueError('Chave de storage inválida.')
        route = '/authenticated' if download else ''
        return f'{self.url}{route}/{self.bucket}/{self.prefix}/{key}'

    def save(self, stream, filename, content_type):
        filename = (filename or '').replace('\\', '/').rsplit('/', 1)[-1]
        if not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
            raise invalid_field('arquivo', 'Nome de arquivo inválido.')
        if content_type not in self.types or Path(filename).suffix.lower() not in self.types[content_type]:
            raise InventoryError(415, 'UNSUPPORTED_MEDIA_TYPE', 'Tipo de arquivo não permitido.')
        content = bytearray()
        while chunk := stream.read(min(65536, self.max_bytes + 1 - len(content))):
            content.extend(chunk)
            if len(content) > self.max_bytes:
                raise InventoryError(413, 'PAYLOAD_TOO_LARGE', 'O arquivo excede o tamanho máximo permitido.')
        if not content:
            raise invalid_field('arquivo', 'O arquivo não pode estar vazio.')
        key = str(uuid4())
        try:
            response = self.client.post(self._url(key), headers={**self.headers, 'Content-Type': content_type}, content=bytes(content))
            response.raise_for_status()
        except httpx.HTTPError:
            raise InventoryError(503, 'STORAGE_UNAVAILABLE', 'Armazenamento indisponível.') from None
        return StoredFile(key, {'nome_arquivo': filename, 'content_type': content_type,
                               'tamanho_bytes': len(content),
                               'enviado_em': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')})

    def open(self, key):
        output = SpooledTemporaryFile(max_size=1024 * 1024)
        try:
            with self.client.stream('GET', self._url(key, download=True), headers=self.headers) as response:
                if response.status_code == 404:
                    raise FileNotFoundError(key)
                response.raise_for_status()
                size = 0
                for chunk in response.iter_bytes(65536):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise InventoryError(503, 'STORAGE_UNAVAILABLE', 'Arquivo armazenado excede o limite.')
                    output.write(chunk)
            output.seek(0)
            return output
        except Exception as error:
            output.close()
            if isinstance(error, httpx.HTTPError):
                raise InventoryError(503, 'STORAGE_UNAVAILABLE', 'Armazenamento indisponível.') from None
            raise

    def delete(self, key):
        try:
            response = self.client.delete(self._url(key), headers=self.headers)
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPError:
            raise InventoryError(503, 'STORAGE_UNAVAILABLE', 'Armazenamento indisponível.') from None


def cloud_storage(prefix, max_bytes, types=None):
    return SupabaseStorage(os.environ['OTO_SUPABASE_URL'], os.environ['OTO_SUPABASE_SERVICE_KEY'],
                           os.environ.get('OTO_STORAGE_BUCKET', 'oto-arquivos'), prefix, max_bytes, types)
