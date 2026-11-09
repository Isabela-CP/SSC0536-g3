"""Smoke de uma stack Docker de desenvolvimento descartável; não usa bases externas.

OTO_STACK_URL configura o frontend (padrão localhost:8080). Faz escritas fictícias
identificadas e reinicia somente os serviços api/worker deste Compose.
"""
import json
import os
import subprocess
import time
import urllib.request
from uuid import uuid4

BASE = os.getenv('OTO_STACK_URL','http://localhost:8080').rstrip('/')


def request(path, body=None, token=None, method=None):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    payload=json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(BASE+'/api'+path,data=payload,headers=headers,method=method),timeout=20) as response:
        data=response.read()
        return json.loads(data) if 'json' in response.headers.get('Content-Type','') else data


def multipart(path, content, token, method='POST'):
    boundary='oto-'+uuid4().hex
    fields={'tipo_documento':'ALVARA','data_vencimento':'2030-01-01'} if method=='POST' else {}
    body=b''
    for name,value in fields.items():
        body+=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    body+=f'--{boundary}\r\nContent-Disposition: form-data; name="arquivo"; filename="smoke.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()+content+f'\r\n--{boundary}--\r\n'.encode()
    headers={'Authorization':'Bearer '+token,'Content-Type':'multipart/form-data; boundary='+boundary}
    with urllib.request.urlopen(urllib.request.Request(BASE+'/api'+path,data=body,headers=headers,method=method),timeout=20) as response:
        return json.loads(response.read())


def ready():
    for _ in range(40):
        try:
            if request('/health')['status']=='ok': return
        except Exception: pass
        time.sleep(1)
    raise RuntimeError('API não ficou saudável.')


if __name__=='__main__':
    ready()
    login=request('/auth/login',{'email':'marina.admin@example.test','senha':'admin-demo'})
    token=login['access_token']
    marker='Verificação Docker '+uuid4().hex[:8]
    # Usa CNPJ válido e exclusivo desta execução (todos os dígitos são calculados).
    prefix=str(int(uuid4().hex[:10],16))[-8:].zfill(8)+'0001'
    def digit(value,weights):
        remainder=sum(int(number)*weight for number,weight in zip(value,weights))%11
        return str(0 if remainder<2 else 11-remainder)
    cnpj=prefix+digit(prefix,[5,4,3,2,9,8,7,6,5,4,3,2])
    cnpj+=digit(cnpj,[6,5,4,3,2,9,8,7,6,5,4,3,2])
    item=request('/estabelecimentos',{'id_categoria':1,'nome_fantasia':marker,'razao_social':marker+' Ltda.','cnpj':cnpj,'endereco':'Endereço fictício de teste'},token)
    request('/estabelecimentos/'+item['id_estabelecimento'],{'meio_hospedagem':{'total_leitos':0},'infraestrutura':{'estacionamento':False}},token,method='PATCH')
    documents='/estabelecimentos/'+item['id_estabelecimento']+'/documentos'
    document=multipart(documents,b'%PDF-1.4 smoke original',token)
    file_path=documents+'/'+str(document['id_documento'])+'/arquivo'
    multipart(file_path,b'%PDF-1.4 smoke substituido',token,method='PUT')
    report=request('/relatorios',{'tipo':'OCUPACAO','formato':'PDF'},token)
    content=request('/relatorios/'+report['id_relatorio']+'/arquivo',token=token)
    assert content.startswith(b'%PDF-')
    subprocess.run(['docker','compose','restart','api','worker'],check=True)
    ready()
    # Reutiliza a sessão emitida antes do reinício: o token e os dados vivem no SQL.
    restored=request('/estabelecimentos/'+item['id_estabelecimento'],token=token)
    assert restored['nome_fantasia']==marker
    assert restored['meio_hospedagem']['total_leitos']==0
    assert restored['infraestrutura']['estacionamento'] is False
    assert request('/relatorios/'+report['id_relatorio']+'/arquivo',token=token)==content
    assert request(file_path,token=token)==b'%PDF-1.4 smoke substituido'
    events=request('/auditoria',token=token)['data']
    assert any(event['id_entidade']==item['id_estabelecimento'] for event in events)
    print('Stack validada: sessão, ficha, documento substituído, auditoria e PDF persistiram após reinício.')
