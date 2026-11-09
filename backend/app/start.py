"""Entrada do serviço hospedado: migrações, primeiro administrador e API."""
import os
import re

from pwdlib import PasswordHash
import uvicorn

from app.database import database, persistent
from app.migrate import apply_migrations


def bootstrap_admin(db):
    email = os.getenv('OTO_BOOTSTRAP_ADMIN_EMAIL', '').strip().lower()
    password = os.getenv('OTO_BOOTSTRAP_ADMIN_PASSWORD', '')
    with db.transaction() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(3700538)')
        if conn.execute('SELECT 1 FROM usuarios LIMIT 1').fetchone():
            return
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254 or not 12 <= len(password) <= 128:
            raise RuntimeError('Base vazia: configure e-mail e senha inicial de 12–128 caracteres nos secrets do serviço.')
        conn.execute("INSERT INTO usuarios(email,senha_hash,perfil,status,nome) VALUES (%s,%s,'ADMINISTRADOR','ATIVO',%s)",
                     (email, PasswordHash.recommended().hash(password), 'Administrador OTO'))


def validate_hosted_config():
    if not persistent() or os.getenv('OTO_ENV') != 'production':
        raise RuntimeError('O serviço hospedado exige PostgreSQL e OTO_ENV=production.')
    required = ('DATABASE_URL', 'OTO_SUPABASE_URL', 'OTO_SUPABASE_SERVICE_KEY',
                'OTO_STORAGE_BUCKET', 'OTO_PUBLIC_URL', 'OTO_CORS_ORIGINS',
                'OTO_BREVO_API_KEY', 'OTO_MAIL_FROM')
    if any(not os.getenv(key) for key in required):
        raise RuntimeError('Complete as variáveis obrigatórias descritas em docs/DEPLOY.md.')
    if os.getenv('OTO_STORAGE_PROVIDER') != 'supabase' or os.getenv('OTO_MAIL_PROVIDER') != 'brevo':
        raise RuntimeError('Use storage persistente Supabase e e-mail HTTPS Brevo no serviço hospedado.')
    if not os.environ['OTO_PUBLIC_URL'].startswith('https://'):
        raise RuntimeError('OTO_PUBLIC_URL deve usar HTTPS.')
    origins = [origin.strip() for origin in os.environ['OTO_CORS_ORIGINS'].split(',')]
    if any(not origin.startswith('https://') or '/' in origin[8:] for origin in origins):
        raise RuntimeError('Configure origens HTTPS exatas, sem caminho, em OTO_CORS_ORIGINS.')


if __name__ == '__main__':
    validate_hosted_config()
    db = database()
    apply_migrations(db)
    bootstrap_admin(db)
    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8000')), workers=1)
