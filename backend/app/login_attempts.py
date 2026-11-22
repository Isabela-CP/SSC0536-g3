"""Projeções do mesmo limite de login para PostgreSQL e testes em memória."""
from datetime import datetime, timedelta, timezone
from threading import Lock
from hashlib import sha256

LIMIT = 5
WINDOW = timedelta(minutes=15)


def keys(identifier, peer):
    return [f"conta:{sha256(identifier.encode()).hexdigest()}", f"ip:{peer}"]


class MemoryAttempts:
    def __init__(self):
        self.entries = {}
        self.lock = Lock()

    def check(self, identifier, peer, authenticate):
        now = datetime.now(timezone.utc)
        account_keys = keys(identifier, peer)
        with self.lock:
            self.entries = {key: value for key, value in self.entries.items() if value[1] > now}
            if any(self.entries.get(key, (0, None))[0] >= LIMIT for key in account_keys):
                return None, True
            result = authenticate()
            if result:
                self.entries.pop(account_keys[0], None)
                return result, False
            for key in account_keys:
                count, expiry = self.entries.get(key, (0, now + WINDOW))
                self.entries[key] = (count + 1, expiry)
            return None, any(self.entries[key][0] >= LIMIT for key in account_keys)


def lock_attempts(conn, account_keys):
    for key in account_keys:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", (key,))
    conn.execute("DELETE FROM login_tentativas WHERE expira_em <= now()")
    return conn.execute(
        "SELECT 1 FROM login_tentativas WHERE chave = ANY(%s) AND falhas >= %s",
        (account_keys, LIMIT),
    ).fetchone() is not None


def record_failure(conn, account_keys):
    blocked = False
    for key in account_keys:
        row = conn.execute("""
            INSERT INTO login_tentativas (chave, falhas, expira_em)
            VALUES (%s, 1, now() + %s)
            ON CONFLICT (chave) DO UPDATE SET falhas = login_tentativas.falhas + 1
            RETURNING falhas
        """, (key, WINDOW)).fetchone()
        blocked = blocked or row['falhas'] >= LIMIT
    return blocked


def credentials(payload):
    """Identificador explícito. Os formatos legados de e-mail continuam válidos."""
    import re
    email, cnpj, password = payload.get("email"), payload.get("cnpj"), payload.get("senha")
    if "cnpj" in payload:
        value = cnpj.strip() if isinstance(cnpj, str) else ""
        valid = "email" not in payload and re.fullmatch(r"(?:[0-9]{14}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})", value)
        return "cnpj", re.sub(r"[^0-9]", "", value) if valid else "", password
    value = email.strip().casefold() if isinstance(email, str) else ""
    return "email", value if len(value) <= 254 else "", password


def account_key(field, identifier, company_cnpj=None):
    if field == "cnpj" or company_cnpj:
        return f"cnpj:{company_cnpj or identifier}"
    return f"email:{identifier}"
