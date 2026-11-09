"""Adaptador relacional para o protocolo já usado pelo serviço de inventário."""
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from psycopg import sql
from psycopg.types.json import Jsonb
from app.inventory_models import flatten, SCHEMAS


def public(value):
    if isinstance(value, dict): return {key:public(child) for key,child in value.items()}
    if isinstance(value, list): return [public(child) for child in value]
    if isinstance(value, (datetime,date,time)): return value.isoformat()
    if isinstance(value, UUID): return str(value)
    if isinstance(value, Decimal): return float(value)
    return value


class PostgresInventoryRepository:
    def __init__(self, db): self.db = db
    def transaction(self): return self.db.transaction()

    def categories(self):
        with self.transaction() as conn:
            return conn.execute('SELECT id_categoria,nome_categoria,descricao FROM categorias_estabelecimento ORDER BY id_categoria').fetchall()

    def establishments(self):
        with self.transaction() as conn:
            rows = conn.execute('SELECT * FROM estabelecimentos ORDER BY id_estabelecimento').fetchall()
            return [self._item(conn,row) for row in rows]

    def establishment(self, establishment_id):
        try: UUID(str(establishment_id))
        except (ValueError,TypeError): return None
        with self.transaction() as conn:
            row = conn.execute('SELECT * FROM estabelecimentos WHERE id_estabelecimento=%s FOR UPDATE', (establishment_id,)).fetchone()
            return self._item(conn,row) if row else None

    def _item(self, conn, row):
        allowed = flatten(SCHEMAS['Estabelecimento'])['properties']
        item = {key:public(value) for key,value in row.items() if key in allowed}
        item.update(row['dados_complementares'])
        item['categoria'] = conn.execute('SELECT id_categoria,nome_categoria,descricao FROM categorias_estabelecimento WHERE id_categoria=%s',(row['id_categoria'],)).fetchone()
        hosting = conn.execute('SELECT * FROM meio_hospedagem WHERE id_estabelecimento=%s',(row['id_estabelecimento'],)).fetchone()
        fields = SCHEMAS['MeioHospedagem']['properties']
        item['meio_hospedagem'] = {key:public(value) for key,value in hosting.items() if key in fields and (value is not None or key!='tipo_hospedagem')} if hosting else None
        for key in ('infraestrutura','acessibilidade'):
            item[key] = hosting[key] if hosting else None
        documents = conn.execute('SELECT * FROM documentos_controle WHERE id_estabelecimento=%s ORDER BY id_documento',(row['id_estabelecimento'],)).fetchall()
        item['documentos'] = []
        for document in documents:
            entry = {key:public(document[key]) for key in ('id_documento','id_estabelecimento','tipo_documento','numero','data_emissao','data_vencimento','status')}
            from app.inventory_service import InventoryService
            entry['status'] = InventoryService.document_status(entry['data_vencimento'])
            if document['nome_arquivo']:
                entry['arquivo'] = {key:public(document[key]) for key in ('nome_arquivo','content_type','tamanho_bytes','enviado_em')}
            item['documentos'].append(entry)
        return item

    @staticmethod
    def _upsert(conn, table, payload, key):
        metadata = conn.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",(table,)).fetchall()
        columns = {row['column_name']:row['data_type'] for row in metadata}
        data = {name:Jsonb(value) if columns[name]=='jsonb' and value is not None else value for name,value in payload.items() if name in columns}
        names = list(data)
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}').format(
            sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,names)),sql.SQL(',').join(sql.Placeholder() for _ in names),sql.Identifier(key),
            sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(name),sql.Identifier(name)) for name in names if name != key))
        conn.execute(query,list(data.values()))
        return columns

    def save(self, establishment):
        with self.transaction() as conn:
            # Serializa leituras/alterações do agregado entre processos, não só threads.
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(establishment['id_estabelecimento'],))
            columns = {r['column_name'] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='estabelecimentos' AND table_schema='public'").fetchall()}
            excluded = {'categoria','meio_hospedagem','infraestrutura','acessibilidade','documentos'}
            payload = {key:value for key,value in establishment.items() if key in columns}
            payload['dados_complementares'] = {key:value for key,value in establishment.items() if key not in columns and key not in excluded}
            previous = conn.execute('SELECT status,inativado_em FROM estabelecimentos WHERE id_estabelecimento=%s FOR UPDATE',(establishment['id_estabelecimento'],)).fetchone()
            payload['inativado_em'] = (previous['inativado_em'] if previous and previous['status']=='INATIVO' else establishment['atualizado_em']) if establishment['status']=='INATIVO' else None
            self._upsert(conn,'estabelecimentos',payload,'id_estabelecimento')
            hosting = establishment.get('meio_hospedagem')
            if hosting is not None or establishment.get('infraestrutura') is not None or establishment.get('acessibilidade') is not None:
                self._upsert(conn,'meio_hospedagem',{'id_estabelecimento':establishment['id_estabelecimento'],**(hosting or {}),'infraestrutura':establishment.get('infraestrutura'),'acessibilidade':establishment.get('acessibilidade')},'id_estabelecimento')
            elif conn.execute('SELECT 1 FROM meio_hospedagem WHERE id_estabelecimento=%s',(establishment['id_estabelecimento'],)).fetchone():
                conn.execute('DELETE FROM meio_hospedagem WHERE id_estabelecimento=%s',(establishment['id_estabelecimento'],))
            for document in establishment.get('documentos',[]):
                self._upsert(conn,'documentos_controle',{key:value for key,value in document.items() if key!='arquivo'} | (document.get('arquivo') or {}),'id_documento')

    def next_document_id(self):
        with self.transaction() as conn:
            return conn.execute("SELECT nextval(pg_get_serial_sequence('documentos_controle','id_documento')) AS id").fetchone()['id']

    def file_reference(self, document_id):
        with self.transaction() as conn:
            row = conn.execute('SELECT caminho_storage FROM documentos_controle WHERE id_documento=%s',(document_id,)).fetchone()
            return row['caminho_storage'] if row else None

    def set_file_reference(self, document_id, key):
        with self.transaction() as conn:
            conn.execute('UPDATE documentos_controle SET caminho_storage=%s WHERE id_documento=%s',(key,document_id))

    def query(self, query, establishment_scope=None):
        import re
        from app.inventory import SUMMARY_FIELDS
        clauses,params = [],[]
        if establishment_scope is not None:
            clauses.append('id_estabelecimento=%s');params.append(establishment_scope)
        if query.busca:
            term=query.busca.casefold()
            escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            conditions=['lower(nome_fantasia) LIKE %s','lower(razao_social) LIKE %s','lower(cnpj) LIKE %s']
            params.extend(['%'+escaped+'%']*3)
            digits=re.sub(r'\D','',term) if re.fullmatch(r'[\d./-]+',term) else ''
            if digits:
                conditions.append("regexp_replace(cnpj,'[^0-9]','','g') LIKE %s");params.append('%'+digits+'%')
            clauses.append('('+' OR '.join(conditions)+')')
        for field in ('id_categoria','status','cadastur_status','aceita_pesquisas'):
            value=getattr(query,field)
            if value is not None:clauses.append(field+'=%s');params.append(value)
        where=sql.SQL(' WHERE '+' AND '.join(clauses)) if clauses else sql.SQL('')
        field=query.ordenar_por
        if field not in ('nome_fantasia','criado_em','atualizado_em') or query.ordem not in ('asc','desc'):raise ValueError('Ordenação inválida.')
        ordering=sql.SQL('lower(nome_fantasia) COLLATE "C"') if field=='nome_fantasia' else sql.Identifier(field)
        with self.transaction() as conn:
            total=conn.execute(sql.SQL('SELECT count(*) AS total FROM estabelecimentos')+where,params).fetchone()['total']
            statement=sql.SQL('SELECT {} FROM estabelecimentos').format(sql.SQL(',').join(map(sql.Identifier,SUMMARY_FIELDS)))+where+sql.SQL(' ORDER BY {} {},id_estabelecimento ASC LIMIT %s OFFSET %s').format(ordering,sql.SQL(query.ordem.upper()))
            rows=conn.execute(statement,[*params,query.page_size,(query.page-1)*query.page_size]).fetchall()
            return {'data':public(rows),'pagination':{'page':query.page,'page_size':query.page_size,'total':total,'total_pages':max(1,(total+query.page_size-1)//query.page_size)}}
