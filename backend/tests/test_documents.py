from datetime import datetime, timedelta, timezone

import pytest


ROOT = "/estabelecimentos/{id_estabelecimento}/documentos"
DETAIL = ROOT + "/{id_documento}"
FILE = DETAIL + "/arquivo"
MISSING = "00000000-0000-4000-8000-000000000000"
PDF = b"%PDF-1.4\nconteudo de teste\n%%EOF"


def path(env, index=0):
    return f'/estabelecimentos/{env.items[index]["id_estabelecimento"]}/documentos'


def upload(env, endpoint=None, **kwargs):
    return env.client.post(endpoint or path(env),
                           data=kwargs.pop("data", {"tipo_documento": "ALVARA", "data_vencimento": "2099-01-01"}),
                           files=kwargs.pop("files", {"arquivo": ("alvara.pdf", PDF, "application/pdf")}), **kwargs)


def test_upload_download_replace_and_audit(write_env):
    env = write_env
    created = upload(env)
    assert created.status_code == 201
    env.validate(created, ROOT, "post")
    document = created.json()
    assert document["status"] == "REGULAR"
    assert document["arquivo"]["nome_arquivo"] == "alvara.pdf"
    assert document["arquivo"]["content_type"] == "application/pdf"
    assert document["arquivo"]["tamanho_bytes"] == len(PDF)
    key = env.repository.file_reference(document["id_documento"])
    assert key not in created.text
    assert env.storage.root.joinpath(key).read_bytes() == PDF
    endpoint = path(env) + f'/{document["id_documento"]}/arquivo'
    download = env.client.get(endpoint)
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/octet-stream"
    assert "attachment" in download.headers["content-disposition"]
    assert "alvara.pdf" in download.headers["content-disposition"]
    assert env.client.get(path(env)).json()["data"][-1] == document
    assert env.audit[-1]["acao"] == "DOCUMENTO_CRIADO"
    assert env.audit[-1]["depois"] == document

    new_content = b"%PDF-1.4\nnovo documento"
    replaced = env.client.put(endpoint, files={"arquivo": ("novo.pdf", new_content, "application/pdf")})
    assert replaced.status_code == 200
    env.validate(replaced, FILE, "put")
    assert replaced.json()["id_documento"] == document["id_documento"]
    assert replaced.json()["arquivo"]["nome_arquivo"] == "novo.pdf"
    assert env.client.get(endpoint).content == new_content
    assert not env.storage.root.joinpath(key).exists()
    assert env.audit[-1]["acao"] == "DOCUMENTO_ARQUIVO_SUBSTITUIDO"
    assert env.audit[-1]["antes"] == document
    assert env.audit[0]["depois"] == document
    assert len(list(env.storage.root.iterdir())) == 1


@pytest.mark.parametrize("filename,mime,content", [
    ("imagem.png", "image/png", b"\x89PNG\r\n\x1a\nimage"),
    ("imagem.jpeg", "image/jpeg", b"\xff\xd8\xffimage"),
    ("imagem.jpg", "image/jpeg", b"\xff\xd8\xffimage"),
])
def test_allowed_types(write_env, filename, mime, content):
    response = upload(write_env, files={"arquivo": (filename, content, mime)})
    assert response.status_code == 201
    endpoint = path(write_env) + f'/{response.json()["id_documento"]}/arquivo'
    assert write_env.client.get(endpoint).content == content


@pytest.mark.parametrize("filename,mime", [
    ("script.exe", "application/octet-stream"), ("texto.txt", "text/plain"),
    ("foto.png", "application/pdf"), ("arquivo.exe", "application/pdf"),
])
def test_reject_mime_or_extension(write_env, filename, mime):
    response = upload(write_env, files={"arquivo": (filename, PDF, mime)})
    assert response.status_code == 415
    write_env.validate(response, ROOT, "post")
    assert write_env.audit == []
    assert not write_env.storage.root.exists()


@pytest.mark.parametrize("size,expected", [(0, 422), (1024, 201), (1025, 413)])
def test_file_size_boundaries(write_env, size, expected):
    response = upload(write_env, files={"arquivo": ("arquivo.pdf", b"x" * size, "application/pdf")})
    assert response.status_code == expected
    write_env.validate(response, ROOT, "post")
    if expected != 201:
        assert list(write_env.storage.root.iterdir()) == []
        assert write_env.audit == []


@pytest.mark.parametrize("data", [
    {}, {"tipo_documento": "INVALIDO", "data_vencimento": "2099-01-01"},
    {"tipo_documento": "ALVARA", "data_vencimento": "invalida"},
    {"tipo_documento": "ALVARA", "data_vencimento": "2099-01-01", "numero": "x" * 121},
    {"tipo_documento": "ALVARA", "data_vencimento": "2099-01-01", "data_emissao": "invalida"},
    {"tipo_documento": "ALVARA", "data_vencimento": "2099-01-01", "storage_key": "chave-do-cliente"},
])
def test_invalid_metadata(write_env, data):
    response = upload(write_env, data=data)
    assert response.status_code == 422
    write_env.validate(response, ROOT, "post")
    assert write_env.audit == []
    assert not write_env.storage.root.exists()


def test_missing_file(write_env):
    response = write_env.client.post(path(write_env), data={"tipo_documento": "ALVARA", "data_vencimento": "2099-01-01"})
    assert response.status_code == 422
    write_env.validate(response, ROOT, "post")


def test_update_metadata_and_preserve_file(write_env):
    env = write_env
    document = upload(env).json()
    endpoint = path(env) + f'/{document["id_documento"]}'
    response = env.client.patch(endpoint, json={"numero": "Novo número", "data_emissao": None, "data_vencimento": "2000-01-01"})
    assert response.status_code == 200
    env.validate(response, DETAIL, "patch")
    assert response.json()["status"] == "VENCIDO"
    assert response.json()["numero"] == "Novo número"
    assert response.json()["data_emissao"] is None
    assert response.json()["arquivo"] == document["arquivo"]
    assert env.client.get(endpoint + "/arquivo").content == PDF
    assert env.audit[-1]["acao"] == "DOCUMENTO_ATUALIZADO"
    assert env.audit[-1]["antes"] == document
    assert env.audit[-1]["depois"] == response.json()


@pytest.mark.parametrize("changes", [{}, {"data_vencimento": None}, {"data_vencimento": "invalida"},
                                    {"tipo_documento": "INVALIDO"}, {"arquivo": {}}, {"status": "VENCIDO"},
                                    {"numero": "x" * 121}])
def test_invalid_document_patch(write_env, changes):
    env = write_env
    document = upload(env).json()
    response = env.client.patch(path(env) + f'/{document["id_documento"]}', json=changes)
    assert response.status_code == 422
    env.validate(response, DETAIL, "patch")
    assert len(env.audit) == 1


@pytest.mark.parametrize("days,status", [(-1, "VENCIDO"), (0, "A_VENCER"), (30, "A_VENCER"), (31, "REGULAR")])
def test_document_status(write_env, days, status):
    expiration = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
    response = upload(write_env, data={"tipo_documento": "AVCB", "data_vencimento": expiration})
    assert response.status_code == 201
    assert response.json()["status"] == status


@pytest.mark.parametrize("role,index,expected", [("EDITOR", 1, 201), ("HOTEL", 0, 201), ("HOTEL", 1, 403), ("GESTOR", 0, 403)])
def test_upload_roles_and_scope(write_env, role, index, expected):
    response = upload(write_env, endpoint=path(write_env, index), headers=write_env.headers(role))
    assert response.status_code == expected
    write_env.validate(response, ROOT, "post")


@pytest.mark.parametrize("role,index", [("HOTEL", 1), ("GESTOR", 0)])
def test_document_writes_forbidden(write_env, role, index):
    env = write_env
    document = upload(env, endpoint=path(env, index)).json()
    endpoint = path(env, index) + f'/{document["id_documento"]}'
    headers = env.headers(role)
    assert env.client.patch(endpoint, json={"numero": "Tentativa"}, headers=headers).status_code == 403
    assert env.client.put(endpoint + "/arquivo", files={"arquivo": ("novo.pdf", PDF, "application/pdf")}, headers=headers).status_code == 403
    if role == "HOTEL":
        assert env.client.get(endpoint + "/arquivo", headers=headers).status_code == 403
    else:
        assert env.client.get(endpoint + "/arquivo", headers=headers).status_code == 200
    assert len(env.audit) == 1


@pytest.mark.parametrize("role", ["EDITOR", "HOTEL"])
def test_document_write_allowed(write_env, role):
    env = write_env
    document = upload(env).json()
    endpoint = path(env) + f'/{document["id_documento"]}'
    headers = env.headers(role)
    assert env.client.patch(endpoint, json={"numero": "Novo"}, headers=headers).status_code == 200
    assert env.client.put(endpoint + "/arquivo", files={"arquivo": ("novo.pdf", PDF, "application/pdf")}, headers=headers).status_code == 200
    assert env.client.get(endpoint + "/arquivo", headers=headers).status_code == 200


def test_documents_not_found_and_cross_parent(write_env):
    env = write_env
    document = upload(env).json()
    for endpoint in [path(env) + "/999999", path(env, 1) + f'/{document["id_documento"]}',
                     f'/estabelecimentos/{MISSING}/documentos/1']:
        assert env.client.patch(endpoint, json={"numero": "Novo"}).status_code == 404
        assert env.client.get(endpoint + "/arquivo").status_code == 404
        assert env.client.put(endpoint + "/arquivo", files={"arquivo": ("novo.pdf", PDF, "application/pdf")}).status_code == 404
    assert upload(env, endpoint=f'/estabelecimentos/{MISSING}/documentos').status_code == 404
    assert len(env.audit) == 1


def test_seed_file_missing_and_deleted_storage_file(write_env):
    env = write_env
    seed_document = env.items[0]["documentos"][0]
    assert env.client.get(path(env) + f'/{seed_document["id_documento"]}/arquivo').status_code == 404
    document = upload(env).json()
    env.storage.delete(env.repository.file_reference(document["id_documento"]))
    response = env.client.get(path(env) + f'/{document["id_documento"]}/arquivo')
    assert response.status_code == 404
    env.validate(response, FILE, "get")


@pytest.mark.parametrize("content,mime,expected", [(b"x" * 1025, "application/pdf", 413), (b"x", "text/plain", 415)])
def test_failed_replacement_preserves_file(write_env, content, mime, expected):
    env = write_env
    document = upload(env).json()
    endpoint = path(env) + f'/{document["id_documento"]}/arquivo'
    response = env.client.put(endpoint, files={"arquivo": ("novo.pdf", content, mime)})
    assert response.status_code == expected
    env.validate(response, FILE, "put")
    assert env.client.get(endpoint).content == PDF
    assert len(list(env.storage.root.iterdir())) == 1
    assert len(env.audit) == 1


def test_storage_failure_rolls_back(write_env, monkeypatch):
    env = write_env
    def fail(*args):
        raise OSError("Storage indisponível")
    monkeypatch.setattr(env.storage, "save", fail)
    with pytest.raises(OSError, match="indisponível"):
        upload(env)
    assert env.repository.establishments() == env.items
    assert env.audit == []


def test_repository_failure_removes_new_file(write_env, monkeypatch):
    env = write_env
    def fail(*args):
        raise RuntimeError("Persistência indisponível")
    monkeypatch.setattr(env.repository, "set_file_reference", fail)
    with pytest.raises(RuntimeError, match="indisponível"):
        upload(env)
    assert env.repository.establishments() == env.items
    assert list(env.storage.root.iterdir()) == []
    assert env.audit == []


def test_document_unauthorized(write_env):
    env = write_env
    document = upload(env).json()
    env.client.headers.pop("Authorization")
    endpoint = path(env) + f'/{document["id_documento"]}'
    assert upload(env).status_code == 401
    assert env.client.patch(endpoint, json={"numero": "Tentativa"}).status_code == 401
    assert env.client.get(endpoint + "/arquivo").status_code == 401
    assert env.client.put(endpoint + "/arquivo", files={"arquivo": ("novo.pdf", PDF, "application/pdf")}).status_code == 401
    assert len(env.audit) == 1


def test_filename_is_sanitized(write_env):
    env = write_env
    response = upload(env, files={"arquivo": ("../../alvará.pdf", PDF, "application/pdf")})
    assert response.status_code == 201
    assert response.json()["arquivo"]["nome_arquivo"] == "alvará.pdf"
    assert len(list(env.storage.root.iterdir())) == 1


def test_replacement_repository_failure_preserves_old_file(write_env, monkeypatch):
    env = write_env
    document = upload(env).json()
    old_key = env.repository.file_reference(document["id_documento"])
    endpoint = path(env) + f'/{document["id_documento"]}/arquivo'
    def fail(*args):
        raise RuntimeError("Persistência indisponível")
    monkeypatch.setattr(env.repository, "set_file_reference", fail)
    with pytest.raises(RuntimeError, match="indisponível"):
        env.client.put(endpoint, files={"arquivo": ("novo.pdf", b"novo", "application/pdf")})
    assert env.repository.file_reference(document["id_documento"]) == old_key
    assert env.client.get(endpoint).content == PDF
    assert len(list(env.storage.root.iterdir())) == 1
    assert len(env.audit) == 1


def test_replace_seed_document_without_existing_file(write_env):
    env = write_env
    document = env.items[0]["documentos"][0]
    endpoint = path(env) + f'/{document["id_documento"]}/arquivo'
    response = env.client.put(endpoint, files={"arquivo": ("novo.pdf", PDF, "application/pdf")})
    assert response.status_code == 200
    env.validate(response, FILE, "put")
    assert env.client.get(endpoint).content == PDF


def test_invalid_multipart_returns_contract_error(write_env):
    response = write_env.client.post(path(write_env), content=b"invalido",
                                      headers={"Content-Type": "multipart/form-data"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
