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
        assert conn.execute('SELECT count(*) AS n FROM schema_migrations').fetchone()['n']==4
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


def test_pg_roles_and_protected_fields(pg):
    client,db=pg
    for email,password in [('rafael.consulta@example.test','gestor-demo'),('camila.editora@example.test','editor-demo'),('responsavel@serra-azul.example','hotel-demo')]:
        response=client.post('/auth/login',json={'email':email,'senha':password})
        assert response.status_code==200,response.text
        headers={'Authorization':'Bearer '+response.json()['access_token']}
        assert client.get('/auditoria',headers=headers).status_code==403
        assert client.post('/usuarios',json={'nome':'Outra','email':'outra@example.test','perfil':'GESTOR'},headers=headers).status_code==403
        assert client.patch('/estabelecimentos/11111111-1111-4111-8111-111111111111',json={'razao_social':'Alterada'},headers=headers).status_code==403
    assert client.get('/perfil',headers={'Authorization':'Bearer admin-token'}).status_code==401


def test_pg_status_and_validation(pg):
    client,db=pg
    path='/estabelecimentos/11111111-1111-4111-8111-111111111111'
    assert client.post(path+'/inativacao',json={'motivo_inativacao':'ab'}).status_code==422
    assert client.post(path+'/inativacao',json={'motivo_inativacao':'Reforma temporária'}).status_code==200
    assert client.post(path+'/inativacao',json={'motivo_inativacao':'Reforma temporária'}).status_code==409
    assert client.post(path+'/reativacao').status_code==200
    assert client.post(path+'/reativacao').status_code==409
    assert client.get('/estabelecimentos/99999999-9999-4999-8999-999999999999').status_code==404
    assert client.post('/usuarios/1/inativacao').status_code==409


def test_pg_invitation_resend_and_expiration(pg):
    client,db=pg
    client.post('/usuarios',json={'nome':'Convidado','email':'convite@example.test','perfil':'EDITOR'})
    first=client.post('/convites',json={'email':'convite@example.test'}).json()
    second=client.post('/convites',json={'email':'convite@example.test'}).json()
    with db.transaction() as conn:
        assert conn.execute('SELECT estado FROM convites WHERE id=%s',(first['id_convite'],)).fetchone()['estado']=='CANCELADO'
        conn.execute("UPDATE convites SET expira_em=now()-interval '1 second' WHERE id=%s",(second['id_convite'],))
        body=conn.execute("SELECT corpo FROM email_outbox WHERE destinatario='convite@example.test' ORDER BY id DESC LIMIT 1").fetchone()['corpo']
    import re
    token=re.search(r'token=([^\s]+)',body).group(1)
    assert client.post('/convites/'+second['id_convite']+'/aceitacao',json={'token':token,'senha':'senha-valida-123'}).status_code==404


def test_pg_password_change_revokes_all_sessions(pg):
    client,db=pg
    assert client.put('/perfil/senha',json={'senha_atual':'errada','senha':'senha-nova-123'}).status_code==403
    assert client.put('/perfil/senha',json={'senha_atual':'admin-demo','senha':'curta'}).status_code==422
    second=client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'admin-demo'}).json()['access_token']
    assert client.put('/perfil/senha',json={'senha_atual':'admin-demo','senha':'senha-nova-123'}).status_code==200
    assert client.get('/perfil').status_code==401
    assert client.get('/perfil',headers={'Authorization':'Bearer '+second}).status_code==401
    assert client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'admin-demo'}).status_code==401
    assert client.post('/auth/login',json={'email':'marina.admin@example.test','senha':'senha-nova-123'}).status_code==200


def test_pg_email_worker_clears_token_after_delivery(pg,monkeypatch):
    client,db=pg
    client.post('/auth/recuperacao-senha',json={'email':'marina.admin@example.test'})
    from app.mailer import dispatch_one
    monkeypatch.setenv('OTO_SMTP_HOST','smtp.test')
    delivered=[]
    class SMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def send_message(self,message):delivered.append(message)
    assert dispatch_one(db,SMTP)
    assert len(delivered)==1
    assert 'token=' in delivered[0].get_content()
    with db.transaction() as conn:
        row=conn.execute('SELECT * FROM email_outbox ORDER BY id LIMIT 1').fetchone()
        assert row['corpo']=='' and row['enviado_em'] is not None
        assert conn.execute("SELECT count(*) AS n FROM recuperacao_senha WHERE length(token_hash)=64").fetchone()['n']>0


def test_pg_recovery_unknown_account_is_generic(pg):
    client,db=pg
    known=client.post('/auth/recuperacao-senha',json={'email':'marina.admin@example.test'})
    unknown=client.post('/auth/recuperacao-senha',json={'email':'inexistente@example.test'})
    assert known.status_code==unknown.status_code==202
    assert known.json()==unknown.json()
    with db.transaction() as conn:
        assert conn.execute("SELECT count(*) AS n FROM email_outbox WHERE destinatario='inexistente@example.test'").fetchone()['n']==0


def test_pg_storage_limits_and_metadata(pg):
    client,db=pg
    path='/estabelecimentos/11111111-1111-4111-8111-111111111111/documentos'
    body={'tipo_documento':'ALVARA','data_vencimento':'2030-01-01'}
    assert client.post(path,data=body,files={'arquivo':('x.txt',b'teste','text/plain')}).status_code==415
    response=client.post(path,data=body,files={'arquivo':('ok.pdf',b'%PDF-1.4 arquivo','application/pdf')})
    assert response.status_code==201
    document=response.json()['id_documento']
    assert client.patch(path+'/'+str(document),json={'numero':'SQL-001'}).status_code==200
    assert client.get(path).json()['data'][-1]['numero']=='SQL-001'
    with db.transaction() as conn:
        row=conn.execute('SELECT * FROM documentos_controle WHERE id_documento=%s',(document,)).fetchone()
        assert row['caminho_storage'] and row['nome_arquivo']=='ok.pdf'


def test_pg_database_failure_has_no_fallback(pg,monkeypatch):
    client,db=pg
    monkeypatch.setenv('DATABASE_URL','postgresql://invalid@127.0.0.1:1/absent')
    database.cache_clear();main.inventory_repository.cache_clear()
    result=client.get('/perfil')
    assert result.status_code==503
    assert result.json()['error']['code']=='DATABASE_UNAVAILABLE'


def test_pg_filter_combinations_pagination_and_literal_search(pg):
    client,db=pg
    query={'id_categoria':1,'status':'ATIVO','aceita_pesquisas':'true','page_size':1,'ordem':'desc'}
    first=client.get('/estabelecimentos',params=query).json()
    second=client.get('/estabelecimentos',params={**query,'page':2}).json()
    assert first['pagination']['total']>=2
    assert len(first['data'])==len(second['data'])==1
    assert first['data'][0]['id_estabelecimento']!=second['data'][0]['id_estabelecimento']
    for term in ['54839271000164','Serra Azul Hospedagem Ltda.','Hotel Serra Azul']:
        result=client.get('/estabelecimentos',params={'busca':term}).json()
        assert result['pagination']['total']==1
    for term in ['%',"' OR true --"]:
        assert client.get('/estabelecimentos',params={'busca':term}).json()['pagination']['total']==0


def test_pg_inactive_timestamp_is_preserved_on_edit(pg):
    client,db=pg
    identifier='33333333-3333-4333-8333-333333333333'
    with db.transaction() as conn:
        before=conn.execute('SELECT inativado_em FROM estabelecimentos WHERE id_estabelecimento=%s',(identifier,)).fetchone()['inativado_em']
    assert client.patch('/estabelecimentos/'+identifier,json={'observacoes':'Edição posterior à inativação'}).status_code==200
    with db.transaction() as conn:
        assert conn.execute('SELECT inativado_em FROM estabelecimentos WHERE id_estabelecimento=%s',(identifier,)).fetchone()['inativado_em']==before


def test_pg_operational_responses_follow_contract(pg):
    import json
    from jsonschema import Draft202012Validator,FormatChecker
    client,db=pg
    contract=json.loads(main.OPENAPI_FILE.read_text())
    for path in ('/perfil','/usuarios','/pesquisas-ocupacao','/respostas-ocupacao/historico','/auditoria','/dashboard'):
        response=client.get(path)
        assert response.status_code==200,response.text
        schema=contract['paths'][path]['get']['responses']['200']['content']['application/json']['schema']
        Draft202012Validator({**schema,'components':contract['components']},format_checker=FormatChecker()).validate(response.json())


def test_pg_bootstrap_creates_first_admin_once(pg, monkeypatch):
    from app.start import bootstrap_admin
    client, db = pg
    with db.transaction() as conn:
        conn.execute('TRUNCATE usuarios CASCADE')
    monkeypatch.setenv('OTO_BOOTSTRAP_ADMIN_EMAIL', 'initial@example.test')
    monkeypatch.setenv('OTO_BOOTSTRAP_ADMIN_PASSWORD', 'initial-secret-123')
    bootstrap_admin(db)
    monkeypatch.setenv('OTO_BOOTSTRAP_ADMIN_PASSWORD', 'ignored-restart-secret')
    bootstrap_admin(db)
    response = client.post('/auth/login', json={'email': 'initial@example.test', 'senha': 'initial-secret-123'})
    assert response.status_code == 200
    assert response.json()['usuario']['perfil'] == 'ADMINISTRADOR'
    with db.transaction() as conn:
        assert conn.execute('SELECT count(*) AS n FROM usuarios').fetchone()['n'] == 1


def test_pg_rls_blocks_non_owner_access(pg):
    client, db = pg
    role = 'oto_test_anon_' + uuid4().hex[:12]
    with db.transaction() as conn:
        conn.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        try:
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT SELECT ON usuarios,sessoes,email_outbox TO {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            for table in ('usuarios', 'sessoes', 'email_outbox'):
                assert not conn.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))).fetchall()
            conn.execute('RESET ROLE')
        finally:
            conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_pg_brevo_failure_retry_and_delivery(pg, monkeypatch):
    import httpx
    from app.mailer import dispatch_one
    client, db = pg
    monkeypatch.setenv('OTO_MAIL_PROVIDER', 'brevo')
    client.post('/auth/recuperacao-senha', json={'email': 'marina.admin@example.test'})
    def failure(row):
        raise httpx.ConnectError('sensitive-provider-response')
    assert dispatch_one(db, brevo_sender=failure)
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM email_outbox ORDER BY id DESC LIMIT 1').fetchone()
        assert row['tentativas'] == 1 and row['enviado_em'] is None
        assert 'sensitive' not in row['ultimo_erro']
    assert dispatch_one(db, brevo_sender=lambda row: None)
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM email_outbox ORDER BY id DESC LIMIT 1').fetchone()
        assert row['tentativas'] == 2 and row['enviado_em']
        assert row['corpo'] == '' and row['ultimo_erro'] is None
