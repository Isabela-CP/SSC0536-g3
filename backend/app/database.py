"""Conexões SQL e unidade de trabalho compartilhada por serviços e auditoria."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import make_conninfo
from app.inventory_errors import InventoryError

_current = ContextVar('oto_sql_connection', default=None)


def persistent():
    mode = os.getenv('OTO_DATA_BACKEND', 'postgres')
    if mode not in ('postgres', 'memory'):
        raise RuntimeError('OTO_DATA_BACKEND deve ser postgres ou memory.')
    if mode=='memory' and os.getenv('OTO_ENV')=='production':
        raise RuntimeError('Mocks não são permitidos no ambiente de produção.')
    return mode == 'postgres'


class Database:
    def __init__(self, dsn):
        self.dsn = dsn

    @contextmanager
    def transaction(self):
        current = _current.get()
        if current is not None:
            with current.transaction():
                yield current
            return
        try:
            with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
                token = _current.set(connection)
                try:
                    with connection.transaction():
                        yield connection
                finally:
                    _current.reset(token)
        except psycopg.errors.UniqueViolation as error:
            field = 'email' if 'email' in (error.diag.constraint_name or '') else 'cnpj'
            raise InventoryError(409, 'EMAIL_ALREADY_EXISTS' if field == 'email' else 'CONFLICT',
                                 f'Já existe um registro com esse {field}.') from None
        except psycopg.IntegrityError:
            raise InventoryError(422, 'VALIDATION_ERROR', 'Dados incompatíveis com as restrições do banco.') from None
        except psycopg.OperationalError:
            raise InventoryError(503, 'DATABASE_UNAVAILABLE', 'Banco de dados indisponível.') from None


@lru_cache
def database():
    dsn = os.getenv('DATABASE_URL')
    if not dsn and all(os.getenv(key) for key in ('PGHOST','PGDATABASE','PGUSER','PGPASSWORD')):
        dsn = make_conninfo(host=os.environ['PGHOST'], port=os.getenv('PGPORT','5432'), dbname=os.environ['PGDATABASE'], user=os.environ['PGUSER'], password=os.environ['PGPASSWORD'])
    if not dsn:
        raise RuntimeError('Configure DATABASE_URL; para mocks explícitos use OTO_DATA_BACKEND=memory.')
    return Database(dsn)
