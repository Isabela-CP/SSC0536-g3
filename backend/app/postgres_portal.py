"""Serviços operacionais SQL. DTOs públicos mantêm os nomes usados pelo frontend."""
from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from pwdlib import PasswordHash
from psycopg.types.json import Jsonb
from app import operations
from app.inventory_errors import InventoryError, invalid_field
from app.postgres_inventory import public

PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(24))


def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def now(): return datetime.now(timezone.utc)
def fail(status, code, message): raise InventoryError(status, code, message)
def require(user, *roles):
    if user['perfil'] not in roles: fail(403,'FORBIDDEN','Seu perfil não pode executar esta operação.')

def user_dto(row):
    return {'id_usuario':row['id'],'nome':row['nome'],'email':row['email'],'perfil':row['perfil'],'ativo':row['status']=='ATIVO',
            **({'id_estabelecimento':str(row['id_estabelecimento'])} if row['perfil']=='HOTEL' else {})}

def new_password(value):
    if not isinstance(value,str) or not 8 <= len(value) <= 128:
        raise invalid_field('senha','A senha deve ter entre 8 e 128 caracteres.')
    return PASSWORDS.hash(value)


class PostgresPortal:
    def __init__(self, db, inventory): self.db,self.inventory = db,inventory

    def audit(self, actor, action, entity, entity_id, before=None, after=None):
        with self.db.transaction() as conn:
            conn.execute('INSERT INTO auditoria_logs(id_usuario,acao,entidade_tipo,entidade_id,valor_anterior,valor_novo) VALUES (%s,%s,%s,%s,%s,%s)',
                         (actor['id_usuario'],action,entity,str(entity_id),Jsonb(before),Jsonb(after)))

    def current_user(self, authorization):
        scheme,_,token = (authorization or '').partition(' ')
        if scheme.lower()!='bearer' or not token: fail(401,'UNAUTHORIZED','É necessário autenticar-se.')
        with self.db.transaction() as conn:
            row = conn.execute("SELECT u.* FROM sessoes s JOIN usuarios u ON u.id=s.id_usuario WHERE s.token_hash=%s AND s.revogado_em IS NULL AND s.expira_em>now() AND u.status='ATIVO'",(digest(token),)).fetchone()
            if not row: fail(401,'UNAUTHORIZED','Sessão inválida ou expirada.')
            return user_dto(row)

    def login(self, payload):
        email,password = payload.get('email'),payload.get('senha')
        if not isinstance(email,str) or not isinstance(password,str) or not password or len(password)>128: fail(401,'INVALID_CREDENTIALS','E-mail ou senha inválidos.')
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM usuarios WHERE lower(email)=%s',(email.strip().casefold(),)).fetchone()
            encoded = row['senha_hash'] if row else DUMMY_HASH
            try: valid = PASSWORDS.verify(password,encoded)
            except Exception:
                # Hashes inválidos do legado não são senhas em texto aceitas.
                valid = False
            if not valid or not row or row['status']!='ATIVO': fail(401,'INVALID_CREDENTIALS','E-mail ou senha inválidos.')
            token = secrets.token_urlsafe(32)
            lifetime = int(os.getenv('OTO_SESSION_SECONDS','900'))
            if not 60 <= lifetime <= 86400: raise RuntimeError('OTO_SESSION_SECONDS deve estar entre 60 e 86400.')
            conn.execute('INSERT INTO sessoes(token_hash,id_usuario,expira_em) VALUES (%s,%s,%s)',(digest(token),row['id'],now()+timedelta(seconds=lifetime)))
            return {'access_token':token,'expires_in':lifetime,'token_type':'Bearer','usuario':user_dto(row)}

    def logout(self, authorization):
        with self.db.transaction() as conn:
            conn.execute('UPDATE sessoes SET revogado_em=now() WHERE token_hash=%s',(digest(authorization.partition(' ')[2]),))

    def update_profile(self, actor, payload):
        operations.fields(payload,{'nome','email'})
        if not payload: raise invalid_field('body','Altere pelo menos um campo.')
        with self.db.transaction() as conn:
            previous = conn.execute('SELECT * FROM usuarios WHERE id=%s FOR UPDATE',(actor['id_usuario'],)).fetchone()
            name = operations.text(payload['nome'],'nome') if 'nome' in payload else previous['nome']
            email = operations.email(payload['email']) if 'email' in payload else previous['email']
            if len(name)>200 or len(email)>254: raise invalid_field('body','Nome ou e-mail acima do limite.')
            row = conn.execute('UPDATE usuarios SET nome=%s,email=%s WHERE id=%s RETURNING *',(name,email,actor['id_usuario'])).fetchone()
            result = user_dto(row)
            self.audit(actor,'PERFIL_ATUALIZADO','USUARIO',row['id'],user_dto(previous),result)
            return result

    def users(self, actor):
        require(actor,'ADMINISTRADOR')
        with self.db.transaction() as conn:
            return {'data':[user_dto(row) | {'status':row['status']} for row in conn.execute('SELECT * FROM usuarios ORDER BY id').fetchall()]}

    def create_user(self, actor, payload):
        require(actor,'ADMINISTRADOR')
        operations.fields(payload,{'nome','email','perfil','id_estabelecimento'},('nome','email','perfil'))
        name,email = operations.text(payload['nome'],'nome'),operations.email(payload['email'])
        role = payload['perfil']
        if role not in ('ADMINISTRADOR','EDITOR','GESTOR','HOTEL'): raise invalid_field('perfil','Perfil inválido.')
        if len(name)>200 or len(email)>254: raise invalid_field('body','Nome ou e-mail acima do limite.')
        association = payload.get('id_estabelecimento')
        if role=='HOTEL':
            if not isinstance(association,str) or not self.inventory.establishment(association): raise invalid_field('id_estabelecimento','Selecione uma hospedagem existente.')
        elif association is not None: raise invalid_field('id_estabelecimento','Vínculo permitido somente para HOTEL.')
        with self.db.transaction() as conn:
            row = conn.execute("INSERT INTO usuarios(nome,email,perfil,id_estabelecimento,senha_hash) VALUES (%s,%s,%s,%s,%s) RETURNING *",(name,email,role,association,PASSWORDS.hash(secrets.token_urlsafe(32)))).fetchone()
            result = user_dto(row)
            self.audit(actor,'USUARIO_CRIADO','USUARIO',row['id'],after=result)
            return result

    @staticmethod
    def queue_email(conn, email, subject, body):
        conn.execute('INSERT INTO email_outbox(destinatario,assunto,corpo) VALUES (%s,%s,%s)',(email,subject,body))

    def invite(self, actor, payload):
        require(actor,'ADMINISTRADOR')
        operations.fields(payload,{'email'},('email',))
        email = operations.email(payload['email'])
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM usuarios WHERE lower(email)=%s FOR UPDATE',(email,)).fetchone()
            if not row: fail(404,'USER_NOT_FOUND','Conta não encontrada.')
            if row['status']!='PENDENTE': fail(409,'CONFLICT','A conta não está pendente de ativação.')
            conn.execute("UPDATE convites SET estado='CANCELADO' WHERE lower(email_destinatario)=%s AND estado='PENDENTE'",(email,))
            token = secrets.token_urlsafe(32)
            result = conn.execute('INSERT INTO convites(token_hash,email_destinatario,perfil,id_criador,id_estabelecimento,expira_em) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id,expira_em',(digest(token),email,row['perfil'],actor['id_usuario'],row['id_estabelecimento'],now()+timedelta(days=7))).fetchone()
            url = os.getenv('OTO_PUBLIC_URL','http://localhost:8080').rstrip('/')+f"/#/ativar-convite?id={result['id']}&token={token}"
            self.queue_email(conn,email,'Ative seu acesso ao OTO',f'Ative seu acesso pelo link: {url}\nVálido por sete dias.')
            self.audit(actor,'CONVITE_CRIADO','CONVITE',result['id'],after={'email':email})
            return {'id_convite':str(result['id']),'email':email,'status':'PENDENTE','expira_em':result['expira_em'].isoformat()}

    def activate(self, invitation_id, payload):
        operations.fields(payload,{'token','senha'},('token','senha'))
        token = operations.text(payload['token'],'token')
        password = new_password(payload['senha'])
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM convites WHERE id::text=%s AND token_hash=%s FOR UPDATE',(str(invitation_id),digest(token))).fetchone()
            if not row or row['expira_em']<=now(): fail(404,'INVITE_NOT_FOUND','Convite não encontrado ou expirado.')
            if row['estado']!='PENDENTE': fail(409,'INVITE_ALREADY_USED','Este convite não está mais disponível.')
            user = conn.execute("UPDATE usuarios SET senha_hash=%s,status='ATIVO' WHERE lower(email)=%s AND status='PENDENTE' RETURNING *",(password,row['email_destinatario'].lower())).fetchone()
            if not user: fail(409,'CONFLICT','Conta não está pendente.')
            conn.execute("UPDATE convites SET estado='ACEITO',aceito_em=now() WHERE id=%s",(row['id'],))
            result = user_dto(user)
            self.audit(result,'CONVITE_ACEITO','USUARIO',user['id'])
            return {'message':'Acesso ativado. Entre com seu e-mail e senha.','usuario':result}

    def recover(self, payload):
        operations.fields(payload,{'email'},('email',))
        email = operations.email(payload['email'])
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM usuarios WHERE lower(email)=%s AND status='ATIVO' FOR UPDATE",(email,)).fetchone()
            if row:
                conn.execute('UPDATE recuperacao_senha SET usado_em=now() WHERE id_usuario=%s AND usado_em IS NULL AND expira_em>now()',(row['id'],))
                token = secrets.token_urlsafe(32)
                conn.execute('INSERT INTO recuperacao_senha(id_usuario,token_hash,expira_em) VALUES (%s,%s,%s)',(row['id'],digest(token),now()+timedelta(minutes=30)))
                url = os.getenv('OTO_PUBLIC_URL','http://localhost:8080').rstrip('/')+f'/#/redefinir-senha?token={token}'
                self.queue_email(conn,email,'Recuperação de acesso OTO',f'Redefina sua senha pelo link: {url}\nVálido por 30 minutos.')
        return {'message':'Se o e-mail estiver cadastrado, as instruções de recuperação serão enviadas.'}

    def reset_password(self, payload):
        operations.fields(payload,{'token','senha'},('token','senha'))
        token = operations.text(payload['token'],'token')
        password = new_password(payload['senha'])
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM recuperacao_senha WHERE token_hash=%s AND usado_em IS NULL AND expira_em>now() FOR UPDATE',(digest(token),)).fetchone()
            if not row: fail(400,'INVALID_TOKEN','Link inválido ou expirado.')
            user = conn.execute('UPDATE usuarios SET senha_hash=%s WHERE id=%s RETURNING *',(password,row['id_usuario'])).fetchone()
            conn.execute('UPDATE recuperacao_senha SET usado_em=now() WHERE id_usuario=%s AND usado_em IS NULL AND expira_em>now()',(row['id_usuario'],))
            conn.execute('UPDATE sessoes SET revogado_em=now() WHERE id_usuario=%s',(row['id_usuario'],))
            self.audit(user_dto(user),'SENHA_REDEFINIDA','USUARIO',user['id'])
        return {'message':'Senha redefinida. Entre novamente.'}

    def change_password(self, actor, payload):
        operations.fields(payload,{'senha_atual','senha'},('senha_atual','senha'))
        password = new_password(payload['senha'])
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM usuarios WHERE id=%s FOR UPDATE',(actor['id_usuario'],)).fetchone()
            if not isinstance(payload['senha_atual'],str) or not PASSWORDS.verify(payload['senha_atual'],row['senha_hash']): fail(403,'INVALID_PASSWORD','Senha atual inválida.')
            conn.execute('UPDATE usuarios SET senha_hash=%s WHERE id=%s',(password,row['id']))
            conn.execute('UPDATE sessoes SET revogado_em=now() WHERE id_usuario=%s',(row['id'],))
            self.audit(actor,'SENHA_ALTERADA','USUARIO',row['id'])
        return {'message':'Senha alterada. Entre novamente.'}

    def user_status(self, actor, user_id, active):
        require(actor,'ADMINISTRADOR')
        with self.db.transaction() as conn:
            # Serializa alterações de administradores para preservar ao menos um ativo.
            conn.execute('SELECT pg_advisory_xact_lock(3700538)')
            row = conn.execute('SELECT * FROM usuarios WHERE id=%s FOR UPDATE',(user_id,)).fetchone()
            if not row: fail(404,'USER_NOT_FOUND','Conta não encontrada.')
            target = 'ATIVO' if active else 'INATIVO'
            if row['status']==target or row['status']=='PENDENTE': fail(409,'CONFLICT','Transição não permitida para o estado da conta.')
            if not active and row['id']==actor['id_usuario']: fail(409,'CONFLICT','Não é possível inativar a própria conta.')
            if not active and row['perfil']=='ADMINISTRADOR' and conn.execute("SELECT count(*) AS total FROM usuarios WHERE perfil='ADMINISTRADOR' AND status='ATIVO'").fetchone()['total']<=1: fail(409,'CONFLICT','Mantenha ao menos um administrador ativo.')
            conn.execute('UPDATE usuarios SET status=%s WHERE id=%s',(target,user_id))
            if not active: conn.execute('UPDATE sessoes SET revogado_em=now() WHERE id_usuario=%s',(user_id,))
            self.audit(actor,'USUARIO_REATIVADO' if active else 'USUARIO_INATIVADO','USUARIO',user_id,{'status':row['status']},{'status':target})
            return user_dto(row | {'status':target})

    @staticmethod
    def survey_dto(conn, row):
        return {'id_pesquisa':str(row['id']),'titulo':row['titulo'],'tipo':row['tipo'],
                'periodo_inicio':row['data_inicio'].isoformat() if row['data_inicio'] else row['periodo_referencia'].isoformat(),
                'periodo_fim':row['data_fim'].isoformat() if row['data_fim'] else row['periodo_referencia'].isoformat(),
                'status':row['estado'],'criada_por':row['id_criador'],
                'estabelecimentos':[str(item['id_estabelecimento']) for item in conn.execute('SELECT id_estabelecimento FROM pesquisa_destinatarios WHERE id_pesquisa=%s ORDER BY id_estabelecimento',(row['id'],)).fetchall()]}

    def surveys(self, actor):
        require(actor,'ADMINISTRADOR','GESTOR','EDITOR','HOTEL')
        with self.db.transaction() as conn:
            if actor['perfil']=='HOTEL':
                rows = conn.execute('SELECT p.* FROM pesquisas_ocupacao p JOIN pesquisa_destinatarios d ON d.id_pesquisa=p.id WHERE d.id_estabelecimento=%s ORDER BY p.id DESC',(actor['id_estabelecimento'],)).fetchall()
            else: rows = conn.execute('SELECT * FROM pesquisas_ocupacao ORDER BY id DESC').fetchall()
            return {'data':[self.survey_dto(conn,row) for row in rows]}

    def save_survey(self, actor, payload, survey_id=None):
        require(actor,'ADMINISTRADOR','EDITOR')
        with self.db.transaction() as conn:
            previous = None
            if survey_id is not None:
                previous = conn.execute('SELECT * FROM pesquisas_ocupacao WHERE id::text=%s FOR UPDATE',(str(survey_id),)).fetchone()
                if not previous: fail(404,'SURVEY_NOT_FOUND','Pesquisa não encontrada.')
                if previous['estado']!='ABERTA': fail(409,'SURVEY_CLOSED','Esta pesquisa está encerrada.')
                before = self.survey_dto(conn,previous)
                operations.fields(payload,{'titulo','tipo','periodo_inicio','periodo_fim','estabelecimentos'})
                if not payload: raise invalid_field('body','Altere pelo menos um campo.')
                data = operations.survey({key:payload.get(key,before[key]) for key in ('titulo','tipo','periodo_inicio','periodo_fim','estabelecimentos')})
            else:
                data = operations.survey(payload)
                before = None
            for establishment_id in data['estabelecimentos']:
                row = conn.execute('SELECT status,aceita_pesquisas FROM estabelecimentos WHERE id_estabelecimento::text=%s FOR SHARE',(establishment_id,)).fetchone()
                if not row or row['status']!='ATIVO' or not row['aceita_pesquisas']: raise invalid_field('estabelecimentos','Selecione hospedagens ativas que aceitam pesquisas.')
            if previous:
                answered = {str(row['id_estabelecimento']) for row in conn.execute("SELECT id_estabelecimento FROM respostas_ocupacao WHERE id_pesquisa=%s AND status='ENVIADA'",(previous['id'],)).fetchall()}
                if not answered.issubset(set(data['estabelecimentos'])): fail(409,'CONFLICT','Uma hospedagem com resposta não pode ser removida da pesquisa.')
                row = conn.execute('UPDATE pesquisas_ocupacao SET titulo=%s,tipo=%s,periodo_referencia=%s,data_inicio=%s,data_fim=%s WHERE id=%s RETURNING *',
                    (data['titulo'],data['tipo'],data['periodo_inicio'][:7]+'-01',data['periodo_inicio'],data['periodo_fim'],previous['id'])).fetchone()
                conn.execute('DELETE FROM pesquisa_destinatarios WHERE id_pesquisa=%s',(row['id'],))
            else:
                row = conn.execute("INSERT INTO pesquisas_ocupacao(titulo,tipo,periodo_referencia,data_inicio,data_fim,estado,id_criador,aberta_em) VALUES (%s,%s,%s,%s,%s,'ABERTA',%s,now()) RETURNING *",
                    (data['titulo'],data['tipo'],data['periodo_inicio'][:7]+'-01',data['periodo_inicio'],data['periodo_fim'],actor['id_usuario'])).fetchone()
            for establishment_id in data['estabelecimentos']:
                conn.execute('INSERT INTO pesquisa_destinatarios VALUES (%s,%s)',(row['id'],establishment_id))
            result = self.survey_dto(conn,row)
            self.audit(actor,'PESQUISA_ATUALIZADA' if previous else 'PESQUISA_CRIADA','PESQUISA_OCUPACAO',row['id'],before,result)
            return result

    def close_survey(self, actor, survey_id):
        require(actor,'ADMINISTRADOR','EDITOR')
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM pesquisas_ocupacao WHERE id::text=%s FOR UPDATE',(str(survey_id),)).fetchone()
            if not row: fail(404,'SURVEY_NOT_FOUND','Pesquisa não encontrada.')
            if row['estado']!='ABERTA': fail(409,'SURVEY_CLOSED','Esta pesquisa não está aberta.')
            before = self.survey_dto(conn,row)
            updated = conn.execute("UPDATE pesquisas_ocupacao SET estado='ENCERRADA',encerrada_em=now() WHERE id=%s RETURNING *",(row['id'],)).fetchone()
            result = self.survey_dto(conn,updated)
            self.audit(actor,'PESQUISA_ENCERRADA','PESQUISA_OCUPACAO',row['id'],before,result)
            return result

    def history(self, actor):
        require(actor,'ADMINISTRADOR','EDITOR','GESTOR','HOTEL')
        with self.db.transaction() as conn:
            query = "SELECT * FROM respostas_ocupacao WHERE status='ENVIADA'"
            params = ()
            if actor['perfil']=='HOTEL': query += ' AND id_estabelecimento=%s'; params=(actor['id_estabelecimento'],)
            rows = conn.execute(query+' ORDER BY enviada_em DESC,id DESC',params).fetchall()
            return {'data':[{'id_resposta':str(row['id']),'id_pesquisa':str(row['id_pesquisa']),'id_estabelecimento':str(row['id_estabelecimento']),'id_usuario':row['id_respondente'],'enviada_em':row['enviada_em'].isoformat(),'dados':{'taxa_ocupacao':float(row['taxa_ocupacao']) if row['taxa_ocupacao'] is not None else None}} for row in rows]}

    def pending(self, actor):
        require(actor,'HOTEL')
        answered = {row['id_pesquisa'] for row in self.history(actor)['data']}
        return {'data':[row for row in self.surveys(actor)['data'] if row['status']=='ABERTA' and row['id_pesquisa'] not in answered]}

    def answer(self, actor, survey_id, payload):
        require(actor,'HOTEL')
        operations.fields(payload,{'taxa_ocupacao'},('taxa_ocupacao',))
        rate = payload['taxa_ocupacao']
        if isinstance(rate,bool) or not isinstance(rate,(float,int)) or not 0<=rate<=100: raise invalid_field('taxa_ocupacao','Informe uma taxa entre 0 e 100%.')
        with self.db.transaction() as conn:
            survey = conn.execute('SELECT * FROM pesquisas_ocupacao WHERE id::text=%s FOR UPDATE',(str(survey_id),)).fetchone()
            if not survey: fail(404,'SURVEY_NOT_FOUND','Pesquisa não encontrada.')
            if not conn.execute('SELECT 1 FROM pesquisa_destinatarios WHERE id_pesquisa=%s AND id_estabelecimento=%s',(survey['id'],actor['id_estabelecimento'])).fetchone(): fail(403,'FORBIDDEN','Pesquisa não destinada à sua hospedagem.')
            if survey['estado']!='ABERTA': fail(409,'SURVEY_CLOSED','Esta pesquisa está encerrada.')
            previous = conn.execute('SELECT * FROM respostas_ocupacao WHERE id_pesquisa=%s AND id_estabelecimento=%s FOR UPDATE',(survey['id'],actor['id_estabelecimento'])).fetchone()
            if previous and previous['status']=='ENVIADA': fail(409,'RESPONSE_ALREADY_SENT','A resposta já foi enviada.')
            if previous:
                row = conn.execute("UPDATE respostas_ocupacao SET taxa_ocupacao=%s,status='ENVIADA',enviada_em=now(),id_respondente=%s WHERE id=%s RETURNING *",(rate,actor['id_usuario'],previous['id'])).fetchone()
            else:
                row = conn.execute("INSERT INTO respostas_ocupacao(id_pesquisa,id_estabelecimento,id_respondente,taxa_ocupacao,status,enviada_em) VALUES (%s,%s,%s,%s,'ENVIADA',now()) RETURNING *",(survey['id'],actor['id_estabelecimento'],actor['id_usuario'],rate)).fetchone()
            result = {'id_resposta':str(row['id']),'id_pesquisa':str(row['id_pesquisa']),'id_estabelecimento':str(row['id_estabelecimento']),'id_usuario':row['id_respondente'],'dados':payload,'enviada_em':row['enviada_em'].isoformat()}
            self.audit(actor,'RESPOSTA_OCUPACAO_ENVIADA','RESPOSTA_OCUPACAO',row['id'],after=result)
            return result

    def audit_log(self, actor, action=None, user_id=None, start=None, end=None):
        require(actor,'ADMINISTRADOR')
        from app.read_views import instant
        lower = instant(start,'data_inicio') if start else None
        upper = instant(end,'data_fim') if end else None
        if lower and upper and lower>upper: raise invalid_field('data_fim','Intervalo inválido.')
        clauses,params = [],[]
        for field,value in [('acao',action),('id_usuario',user_id)]:
            if value is not None:
                clauses.append(f'a.{field}=%s');params.append(value)
        if lower: clauses.append('a.criado_em>=%s');params.append(lower)
        if upper: clauses.append('a.criado_em<=%s');params.append(upper)
        with self.db.transaction() as conn:
            query = 'SELECT a.*,u.email FROM auditoria_logs a LEFT JOIN usuarios u ON u.id=a.id_usuario'
            if clauses: query+=' WHERE '+' AND '.join(clauses)
            rows = conn.execute(query+' ORDER BY a.criado_em DESC,a.id DESC',params).fetchall()
            return {'data':[{'id':str(row['id']),'id_usuario':row['id_usuario'],'usuario':row['email'] or 'Sistema','acao':row['acao'],'entidade':row['entidade_tipo'],'id_entidade':row['entidade_id'],'antes':row['valor_anterior'],'depois':row['valor_novo'],'criado_em':row['criado_em'].isoformat()} for row in rows]}

    def dashboard(self, actor):
        require(actor,'ADMINISTRADOR','EDITOR','GESTOR')
        from app.read_views import dashboard_summary
        return dashboard_summary(self.inventory,self.surveys(actor)['data'],self.history(actor)['data'])

    def report(self, actor, report_id):
        require(actor,'ADMINISTRADOR','GESTOR')
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM relatorios WHERE id::text=%s',(str(report_id),)).fetchone()
            if not row: fail(404,'REPORT_NOT_FOUND','Relatório não encontrado.')
            return {'id_relatorio':str(row['id']),'tipo':'OCUPACAO','formato':row['formato'],'status':row['status'],'criado_em':row['criado_em'].isoformat(),'arquivo':{'nome_arquivo':row['arquivo_nome'],'tamanho_bytes':row['arquivo_tamanho_bytes']} if row['arquivo_nome'] else None}

    def generate_report(self, actor, payload):
        require(actor,'ADMINISTRADOR','GESTOR')
        operations.fields(payload,{'tipo','formato','id_pesquisa'},('tipo','formato'))
        if payload['tipo']!='OCUPACAO' or payload['formato'] not in ('PDF','CSV'): raise invalid_field('formato','Informe tipo OCUPACAO e formato PDF ou CSV.')
        from app.document_storage import report_storage
        from app.reporting import build_report
        from io import BytesIO
        surveys = {row['id_pesquisa']:row for row in self.surveys(actor)['data']}
        selected = payload.get('id_pesquisa')
        if selected is not None and str(selected) not in surveys: fail(404,'SURVEY_NOT_FOUND','Pesquisa não encontrada.')
        rows = [['Pesquisa','Hospedagem','Início','Fim','Ocupação (%)','Respondida em']]
        for response in self.history(actor)['data']:
            if selected is not None and response['id_pesquisa']!=str(selected): continue
            survey = surveys[response['id_pesquisa']]
            item = self.inventory.establishment(response['id_estabelecimento'])
            rows.append([survey['titulo'],item['nome_fantasia'],survey['periodo_inicio'],survey['periodo_fim'],response['dados']['taxa_ocupacao'],response['enviada_em']])
        content,mime = build_report(payload['formato'],rows)
        storage = report_storage()
        name = 'relatorio.'+payload['formato'].lower()
        stored = storage.save(BytesIO(content),name,mime.split(';')[0])
        try:
            with self.db.transaction() as conn:
                row = conn.execute("INSERT INTO relatorios(formato,parametros,status,id_solicitante,iniciado_em,concluido_em,arquivo_nome,arquivo_caminho_interno,arquivo_tamanho_bytes) VALUES (%s,%s,'CONCLUIDO',%s,now(),now(),%s,%s,%s) RETURNING id",(payload['formato'],Jsonb(payload),actor['id_usuario'],name,stored.key,len(content))).fetchone()
                self.audit(actor,'RELATORIO_GERADO','RELATORIO',row['id'],after={'formato':payload['formato'],'status':'CONCLUIDO'})
                return self.report(actor,row['id'])
        except Exception:
            storage.delete(stored.key)
            raise

    def download_report(self, actor, report_id):
        from fastapi.responses import StreamingResponse
        from starlette.background import BackgroundTask
        from app.document_storage import report_storage
        self.report(actor,report_id)
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM relatorios WHERE id::text=%s',(str(report_id),)).fetchone()
            if not row['arquivo_caminho_interno']: fail(404,'NOT_FOUND','Arquivo não encontrado.')
            try: stream = report_storage().open(row['arquivo_caminho_interno'])
            except (ValueError,FileNotFoundError): fail(404,'NOT_FOUND','Arquivo não encontrado.')
            return StreamingResponse(iter(lambda:stream.read(65536),b''),media_type='application/pdf' if row['formato']=='PDF' else 'text/csv',headers={'Content-Disposition':f'attachment; filename="{row["arquivo_nome"]}"'},background=BackgroundTask(stream.close))
