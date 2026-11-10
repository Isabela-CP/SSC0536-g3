"""Adaptadores cloud sem chamadas externas nem credenciais reais."""
from io import BytesIO
import httpx
import pytest

from app.cloud_storage import SupabaseStorage
from app.inventory_errors import InventoryError
from app.mailer import send_brevo
from app.start import validate_hosted_config


def storage(handler, max_bytes=1024):
    return SupabaseStorage('https://project.supabase.co', 'sb_secret_fake_test',
                           'oto-arquivos', 'documentos', max_bytes,
                           client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_cloud_storage_private_roundtrip():
    objects = {}
    def handle(request):
        assert request.headers['apikey'] == 'sb_secret_fake_test'
        assert 'authorization' not in request.headers
        key = request.url.path.rsplit('/', 1)[-1]
        if request.method == 'POST':
            assert '/authenticated/' not in request.url.path
            objects[key] = request.content
            return httpx.Response(200)
        if request.method == 'DELETE':
            objects.pop(key, None)
            return httpx.Response(200)
        assert '/authenticated/oto-arquivos/documentos/' in request.url.path
        return httpx.Response(200, content=objects[key]) if key in objects else httpx.Response(404)
    backend = storage(handle)
    saved = backend.save(BytesIO(b'%PDF-test'), '../teste.pdf', 'application/pdf')
    assert saved.metadata['nome_arquivo'] == 'teste.pdf'
    assert saved.metadata['tamanho_bytes'] == 9
    with backend.open(saved.key) as stream:
        assert stream.read() == b'%PDF-test'
    backend.delete(saved.key)
    with pytest.raises(FileNotFoundError):
        backend.open(saved.key)
    with pytest.raises(ValueError):
        backend.open('../outro')


@pytest.mark.parametrize('content,name,mime,status', [
    (b'', 'a.pdf', 'application/pdf', 422),
    (b'12345', 'a.pdf', 'application/pdf', 413),
    (b'123', 'a.exe', 'application/pdf', 415),
    (b'123', 'a.pdf', 'application/x-msdownload', 415),
])
def test_cloud_upload_rejected_before_network(content, name, mime, status):
    def unexpected(request):
        pytest.fail('Não deve transmitir arquivo inválido.')
    with pytest.raises(InventoryError) as error:
        storage(unexpected, 4).save(BytesIO(content), name, mime)
    assert error.value.status_code == status


def test_cloud_provider_failure_is_generic():
    backend = storage(lambda request: httpx.Response(403, text='fake-server-only-key'))
    with pytest.raises(InventoryError) as error:
        backend.save(BytesIO(b'pdf'), 'a.pdf', 'application/pdf')
    assert error.value.status_code == 503
    assert 'fake-server-only-key' not in str(error.value.error)


def test_brevo_uses_https_and_server_secret(monkeypatch):
    monkeypatch.setenv('OTO_BREVO_API_KEY', 'fake-brevo-key')
    monkeypatch.setenv('OTO_MAIL_FROM', 'oto@example.test')
    def post(url, **options):
        assert url == 'https://api.brevo.com/v3/smtp/email'
        assert options['headers']['api-key'] == 'fake-brevo-key'
        assert options['json']['to'] == [{'email': 'destino@example.test'}]
        assert options['json']['textContent'] == 'link de ativação'
        return httpx.Response(201, request=httpx.Request('POST', url))
    send_brevo({'destinatario': 'destino@example.test', 'assunto': 'Ativação', 'corpo': 'link de ativação'}, post=post)


def test_hosted_entry_rejects_incomplete_configuration(monkeypatch):
    monkeypatch.setenv('OTO_ENV', 'production')
    monkeypatch.setenv('OTO_DATA_BACKEND', 'postgres')
    monkeypatch.delenv('OTO_SUPABASE_SERVICE_KEY', raising=False)
    with pytest.raises(RuntimeError, match='variáveis obrigatórias'):
        validate_hosted_config()
