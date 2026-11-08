from datetime import date
import pytest
from app.read_views import dashboard_summary


def test_dashboard_uses_mutable_repository_and_only_hospitality(write_env):
    env = write_env
    item = env.items[0]
    item['status'] = 'INATIVO'
    item['vencimento_cadastur'] = '2026-11-01'
    env.repository.save(item)
    result = dashboard_summary(env.repository, [], [], date(2026, 11, 8))
    ids = {r['id_categoria'] for r in env.repository.categories() if r['nome_categoria'] == 'Meios de hospedagem'}
    items = [r for r in env.repository.establishments() if r['id_categoria'] in ids]
    assert result['indicadores']['total_empresas'] == len(items)
    assert result['indicadores']['total_leitos'] == sum((r.get('meio_hospedagem') or {}).get('total_leitos') or 0 for r in items)
    assert next(r for r in result['alertas_cadastur'] if r['id_estabelecimento'] == item['id_estabelecimento'])['dias_ate_vencimento'] == -7
    response = env.client.get('/dashboard')
    assert response.status_code == 200
    assert response.json()['indicadores']['estabelecimentos_ativos'] == sum(r['status'] == 'ATIVO' for r in items)
    assert env.client.get('/dashboard', headers=env.headers('HOTEL')).status_code == 403
    for role in ('EDITOR', 'GESTOR'):
        assert env.client.get('/dashboard', headers=env.headers(role)).status_code == 200


def test_audit_filters_compare_instants_and_preserve_payload(write_env):
    env = write_env
    env.audit.extend([
        {'id': 'a', 'acao': 'UPDATE', 'id_usuario': 1, 'criado_em': '2026-11-08T09:00:00-03:00', 'antes': {'flag': False}, 'depois': {'flag': None}},
        {'id': 'b', 'acao': 'CREATE', 'id_usuario': 2, 'criado_em': '2026-11-08T12:01:00Z', 'antes': None, 'depois': {'total': 0}},
    ])
    result = env.client.get('/auditoria', params={'acao': 'UPDATE', 'id_usuario': 1, 'data_inicio': '2026-11-08T12:00:00Z', 'data_fim': '2026-11-08T12:00:00Z'})
    assert result.status_code == 200
    assert result.json()['data'] == [env.audit[0]]
    for role in ('EDITOR', 'GESTOR', 'HOTEL'):
        assert env.client.get('/auditoria', headers=env.headers(role)).status_code == 403


@pytest.mark.parametrize('params', [{'data_inicio': 'errado'}, {'data_fim': '2026-11-08'}, {'data_inicio': '2026-11-09T00:00:00Z', 'data_fim': '2026-11-08T00:00:00Z'}])
def test_audit_rejects_invalid_ranges(write_env, params):
    assert write_env.client.get('/auditoria', params=params).status_code == 422


def test_search_accepts_full_cnpj_without_punctuation(write_env):
    item = write_env.items[0]
    digits = ''.join(char for char in item['cnpj'] if char.isdigit())
    response = write_env.client.get('/estabelecimentos', params={'busca': digits})
    assert response.status_code == 200
    assert [row['id_estabelecimento'] for row in response.json()['data']] == [item['id_estabelecimento']]


def test_dashboard_and_audit_require_bearer(write_env):
    for path in ('/dashboard', '/auditoria'):
        assert write_env.client.get(path, headers={'Authorization': ''}).status_code == 401
