"""Runner transacional versionado: python -m app.migrate [--seed]."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import psycopg
from app.database import database

ROOT = Path(__file__).resolve().parents[2]


def apply_migrations(db):
    with psycopg.connect(db.dsn, autocommit=True) as conn:
        conn.execute('SELECT pg_advisory_lock(3700536)')
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
            for file in sorted((ROOT/'db/migrations').glob('*.sql')):
                content = file.read_text()
                checksum = hashlib.sha256(content.encode()).hexdigest()
                previous = conn.execute('SELECT checksum FROM schema_migrations WHERE name=%s',(file.name,)).fetchone()
                if previous:
                    if previous[0]!=checksum: raise RuntimeError(f'Migration já aplicada foi modificada: {file.name}')
                    continue
                with conn.transaction():
                    conn.execute(re.sub(r'^(BEGIN|COMMIT);\s*$', '', content, flags=re.MULTILINE))
                    conn.execute('INSERT INTO schema_migrations(name,checksum) VALUES (%s,%s)',(file.name,checksum))
        finally: conn.execute('SELECT pg_advisory_unlock(3700536)')


def seed_development(db):
    from pwdlib import PasswordHash
    password = PasswordHash.recommended()
    with db.transaction() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS application_seeds (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
        conn.execute('SELECT pg_advisory_xact_lock(3700537)')
        if conn.execute("SELECT 1 FROM application_seeds WHERE name='001_dev_seed'").fetchone(): return
        content = (ROOT/'db/seeds/001_dev_seed.sql').read_text()
        conn.execute(re.sub(r'^(BEGIN|COMMIT);\s*$', '', content, flags=re.MULTILINE))
        for user in conn.execute("SELECT id,perfil FROM usuarios WHERE senha_hash LIKE 'DEV_PLACEHOLDER_HASH_%'").fetchall():
            secret = {'ADMINISTRADOR':'admin-demo','GESTOR':'gestor-demo','EDITOR':'editor-demo','HOTEL':'hotel-demo'}[user['perfil']]
            conn.execute('UPDATE usuarios SET senha_hash=%s WHERE id=%s',(password.hash(secret),user['id']))
        conn.execute("INSERT INTO pesquisa_destinatarios SELECT id_pesquisa,id_estabelecimento FROM respostas_ocupacao ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO application_seeds(name) VALUES ('001_dev_seed')")


def configure_application_role(db):
    from psycopg import sql
    name = os.getenv('OTO_APP_USER')
    if not name: return
    password = os.environ['OTO_APP_PASSWORD']
    if not password: raise RuntimeError('OTO_APP_PASSWORD obrigatório.')
    with db.transaction() as conn:
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(name),sql.Literal(password)))
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(name)))
        conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(name)))
        conn.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(name)))
        for table in ('auditoria_logs','schema_migrations','application_seeds'):
            conn.execute(sql.SQL('REVOKE UPDATE,DELETE,TRUNCATE ON {} FROM {}').format(sql.Identifier(table),sql.Identifier(name)))
        conn.execute(sql.SQL('REVOKE INSERT ON schema_migrations,application_seeds FROM {}').format(sql.Identifier(name)))


if __name__=='__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--seed',action='store_true');args=parser.parse_args()
    db=database();apply_migrations(db)
    if args.seed:
        if os.getenv('OTO_ENV','development')!='development': raise RuntimeError('Seed permitido apenas em desenvolvimento.')
        seed_development(db)
    configure_application_role(db)
