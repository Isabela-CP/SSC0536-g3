"""Integração real em bancos descartáveis, sem tocar nas bases de desenvolvimento."""
import os
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from fastapi.testclient import TestClient
from app import main
from app.database import Database, database
from app.document_storage import document_storage, report_storage
from app.migrate import apply_migrations, seed_development
from app.postgres_portal import digest


@pytest.fixture(scope='module')
def sql_template():
    admin = os.getenv('OTO_TEST_ADMIN_URL')
    if not admin: pytest.skip('Configure OTO_TEST_ADMIN_URL para testar PostgreSQL real.')
    name = 'oto_test_template_'+uuid4().hex[:12]
    with psycopg.connect(admin,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn = make_conninfo(admin,dbname=name)
    try:
        db = Database(dsn)
        apply_migrations(db)
        apply_migrations(db)
        seed_development(db)
        seed_development(db)
        yield admin,name
    finally:
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.fixture
def pg(sql_template,monkeypatch,tmp_path):
    admin,template = sql_template
    name = 'oto_test_'+uuid4().hex[:12]
    with psycopg.connect(admin,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(name),sql.Identifier(template)))
    monkeypatch.setenv('OTO_DATA_BACKEND','postgres')
    monkeypatch.setenv('DATABASE_URL',make_conninfo(admin,dbname=name))
    monkeypatch.setenv('OTO_STORAGE_DIR',str(tmp_path/'files'))
    database.cache_clear();main.inventory_repository.cache_clear();document_storage.cache_clear();report_storage.cache_clear()
    try:
        with TestClient(main.app) as client:
            response = client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'admin-demo'})
            assert response.status_code==200,response.text
            client.headers['Authorization']='Bearer '+response.json()['access_token']
            yield client,database()
    finally:
        database.cache_clear();main.inventory_repository.cache_clear();document_storage.cache_clear();report_storage.cache_clear()
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_pg_seed_and_repositories(pg):
    client,db=pg
    assert client.get('/health').json()=={'status':'ok'}
    result=client.get('/estabelecimentos',params={'id_categoria':1}).json()
    assert result['pagination']['total']==4
    for row in result['data']:
        response=client.get('/estabelecimentos/'+row['id_estabelecimento'])
        assert response.status_code==200,response.text
    with db.transaction() as conn:
        assert conn.execute('SELECT count(*) AS n FROM schema_migrations').fetchone()['n']==3
        assert conn.execute('SELECT count(*) AS n FROM usuarios').fetchone()['n']==10
        assert conn.execute("SELECT count(*) AS n FROM usuarios WHERE senha_hash NOT LIKE '$argon2id$%'").fetchone()['n']==0


def test_pg_login_expiration_and_logout(pg):
    client,db=pg
    token=client.headers['Authorization'].split()[1]
    with db.transaction() as conn:
        conn.execute("UPDATE sessoes SET expira_em=now()-interval '1 second' WHERE token_hash=%s",(digest(token),))
    assert client.get('/perfil').status_code==401
    response=client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'admin-demo'})
    client.headers['Authorization']='Bearer '+response.json()['access_token']
    assert client.post('/auth/logout').status_code==204
    assert client.get('/perfil').status_code==401
    assert client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'errada'}).status_code==401


def test_pg_write_persists_and_audits(pg,create_payload):
    client,db=pg
    response=client.post('/estabelecimentos',json=create_payload)
    assert response.status_code==201,response.text
    item=response.json()
    assert client.patch('/estabelecimentos/'+item['id_estabelecimento'],json={'meio_hospedagem':{'total_leitos':0},'infraestrutura':{'estacionamento':False}}).status_code==200
    main.inventory_repository.cache_clear()
    result=client.get('/estabelecimentos/'+item['id_estabelecimento']).json()
    assert result['meio_hospedagem']['total_leitos']==0
    assert result['infraestrutura']['estacionamento'] is False
    assert client.post('/estabelecimentos',json={**create_payload,'cnpj':'11222333000181'}).status_code==409
    assert client.patch('/estabelecimentos/'+item['id_estabelecimento'],json={'cnpj':None,'razao_social':None}).status_code==200
    with db.transaction() as conn:
        assert conn.execute('SELECT count(*) AS n FROM auditoria_logs WHERE entidade_id=%s',(item['id_estabelecimento'],)).fetchone()['n']==3


def test_pg_concurrent_cnpj(pg,create_payload):
    client,db=pg
    headers=dict(client.headers)
    def create(_):
        with TestClient(main.app,headers=headers) as other:
            return other.post('/estabelecimentos',json=create_payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create,range(2)))==[201,409]


def test_pg_transaction_rolls_back_record_and_audit(pg,create_payload,monkeypatch):
    client,db=pg
    original=main.audit
    def broken(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('falha controlada')
    monkeypatch.setattr(main,'audit',broken)
    # O callback do router foi capturado na construção; substitui o método do serviço SQL.
    from app.postgres_portal import PostgresPortal
    original_method=PostgresPortal.audit
    def broken_audit(self,*args,**kwargs):
        original_method(self,*args,**kwargs)
        raise RuntimeError('falha controlada')
    monkeypatch.setattr(PostgresPortal,'audit',broken_audit)
    with pytest.raises(RuntimeError,match='falha controlada'):
        client.post('/estabelecimentos',json=create_payload)
    with db.transaction() as conn:
        assert conn.execute('SELECT count(*) AS n FROM estabelecimentos WHERE nome_fantasia=%s',(create_payload['nome_fantasia'],)).fetchone()['n']==0
        assert conn.execute("SELECT count(*) AS n FROM auditoria_logs WHERE acao='ESTABELECIMENTO_CRIADO'").fetchone()['n']==0


def test_pg_documents_survive_repository_restart(pg):
    client,db=pg
    path='/estabelecimentos/11111111-1111-4111-8111-111111111111/documentos'
    response=client.post(path,data={'tipo_documento':'ALVARA','data_vencimento':'2030-01-01'},files={'arquivo':('exemplo.pdf',b'%PDF-1.4 conteudo','application/pdf')})
    assert response.status_code==201,response.text
    document=response.json()
    file_path=path+'/'+str(document['id_documento'])+'/arquivo'
    main.inventory_repository.cache_clear()
    assert client.get(file_path).content==b'%PDF-1.4 conteudo'
    response=client.put(file_path,files={'arquivo':('novo.pdf',b'%PDF-1.4 substituido','application/pdf')})
    assert response.status_code==200,response.text
    main.inventory_repository.cache_clear()
    assert client.get(file_path).content==b'%PDF-1.4 substituido'


def test_pg_hotel_isolation_and_survey(pg):
    client,db=pg
    hotel='11111111-1111-4111-8111-111111111111'
    body={'titulo':'Pesquisa SQL','tipo':'CONSOLIDADO','periodo_inicio':'2026-11-01','periodo_fim':'2026-11-30','estabelecimentos':[hotel]}
    response=client.post('/pesquisas-ocupacao',json=body)
    assert response.status_code==201,response.text
    research=response.json()['id_pesquisa']
    login=client.post('/auth/login',json={'email':'responsavel@serra-azul.example','senha':'hotel-demo'})
    assert login.status_code==200,login.text
    headers={'Authorization':'Bearer '+login.json()['access_token']}
    assert client.get('/estabelecimentos',headers=headers).json()['pagination']['total']==1
    assert client.get('/estabelecimentos/22222222-2222-4222-8222-222222222222',headers=headers).status_code==403
    assert client.post('/pesquisas-ocupacao/'+research+'/respostas',json={'taxa_ocupacao':0},headers=headers).status_code==201
    assert client.post('/pesquisas-ocupacao/'+research+'/respostas',json={'taxa_ocupacao':20},headers=headers).status_code==409
    assert all(row['id_estabelecimento']==hotel for row in client.get('/respostas-ocupacao/historico',headers=headers).json()['data'])
    report=client.post('/relatorios',json={'tipo':'OCUPACAO','formato':'CSV','id_pesquisa':research})
    assert report.status_code==202,report.text
    main.inventory_repository.cache_clear()
    download=client.get('/relatorios/'+report.json()['id_relatorio']+'/arquivo')
    assert download.status_code==200 and 'text/csv' in download.headers['content-type']
    assert 'Pesquisa SQL' in download.content.decode('utf-8-sig')


def test_pg_invite_activation_password_and_user_status(pg):
    client,db=pg
    response=client.post('/usuarios',json={'nome':'Pessoa Teste','email':'nova@example.test','perfil':'GESTOR'})
    assert response.status_code==201,response.text
    user=response.json()['id_usuario']
    invited=client.post('/convites',json={'email':'nova@example.test'})
    assert invited.status_code==201,invited.text
    with db.transaction() as conn:
        message=conn.execute("SELECT corpo FROM email_outbox WHERE destinatario='nova@example.test'").fetchone()['corpo']
    import re
    token=re.search(r'token=([^\s]+)',message).group(1)
    path='/convites/'+invited.json()['id_convite']+'/aceitacao'
    assert client.post(path,json={'token':token,'senha':'senha-nova-123'}).status_code==200
    assert client.post(path,json={'token':token,'senha':'senha-nova-123'}).status_code==409
    login=client.post('/auth/login',json={'email':'nova@example.test','senha':'senha-nova-123'})
    headers={'Authorization':'Bearer '+login.json()['access_token']}
    assert client.post(f'/usuarios/{user}/inativacao').status_code==200
    assert client.get('/perfil',headers=headers).status_code==401
    assert client.post(f'/usuarios/{user}/reativacao').status_code==200


def test_pg_recovery_single_use_and_revocation(pg):
    client,db=pg
    assert client.post('/auth/recuperacao-senha',json={'email':'marina.admin@example.test'}).status_code==202
    import re
    with db.transaction() as conn:
        body=conn.execute("SELECT corpo FROM email_outbox WHERE destinatario='marina.admin@example.test'").fetchone()['corpo']
    token=re.search(r'token=([^\s]+)',body).group(1)
    assert client.post('/auth/redefinicao-senha',json={'token':token,'senha':'outra-senha-123'}).status_code==200
    assert client.get('/perfil').status_code==401
    assert client.post('/auth/redefinicao-senha',json={'token':token,'senha':'outra-senha-123'}).status_code==400
    assert client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'outra-senha-123'}).status_code==200


def test_pg_audit_append_only(pg):
    client,db=pg
    with pytest.raises(psycopg.errors.RaiseException):
        with db.transaction() as conn:
            conn.execute("UPDATE auditoria_logs SET acao='MODIFICADA'")
