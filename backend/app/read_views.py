"""Consultas para dashboard e auditoria, sem dependência de rotas."""
from datetime import date, datetime, timezone
from app.inventory_errors import invalid_field


def dashboard_summary(repository, surveys, responses, today=None):
    today = today or date.today()
    categories = {row['id_categoria'] for row in repository.categories()
                  if row['nome_categoria'].casefold() == 'meios de hospedagem'}
    items = [row for row in repository.establishments() if row['id_categoria'] in categories]
    beds = [(row.get('meio_hospedagem') or {}).get('total_leitos') for row in items]
    alerts = []
    for row in items:
        if not row.get('possui_cadastur') or not row.get('vencimento_cadastur'):
            continue
        expiration = date.fromisoformat(row['vencimento_cadastur'])
        alerts.append({'id_estabelecimento': row['id_estabelecimento'],
                       'nome_fantasia': row['nome_fantasia'], 'data': expiration.isoformat(),
                       'dias_ate_vencimento': (expiration - today).days})
    alerts.sort(key=lambda row: (row['data'], row['id_estabelecimento']))
    return {'indicadores': {
        'total_empresas': len(items), 'total_leitos': sum(value for value in beds if value is not None),
        'leitos_nao_informados': sum(value is None for value in beds),
        'estabelecimentos_ativos': sum(row['status'] == 'ATIVO' for row in items),
        'pesquisas_abertas': sum(row['status'] == 'ABERTA' for row in surveys),
        'respostas_recebidas': len(responses),
    }, 'alertas_cadastur': alerts, 'referencia': today.isoformat()}


def instant(value, field):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise invalid_field(field, 'Informe data e hora com fuso horário.') from None


def audit_records(records, action=None, user_id=None, start=None, end=None):
    lower = instant(start, 'data_inicio') if start else None
    upper = instant(end, 'data_fim') if end else None
    if lower and upper and lower > upper:
        raise invalid_field('data_fim', 'A data final deve ser posterior ou igual à inicial.')
    result = []
    for row in records:
        if action and row['acao'] != action:
            continue
        if user_id is not None and row['id_usuario'] != user_id:
            continue
        created = instant(row['criado_em'], 'criado_em')
        if (lower and created < lower) or (upper and created > upper):
            continue
        result.append(row)
    return sorted(result, key=lambda row: (instant(row['criado_em'], 'criado_em'), row['id']), reverse=True)
