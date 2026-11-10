"""Outbox transacional. O SMTP de desenvolvimento é capturado pelo Mailpit."""
from email.message import EmailMessage
import logging
import os
import smtplib
from threading import Event
import httpx
from app.database import database

log = logging.getLogger(__name__)


def send_brevo(row, post=httpx.post):
    response = post('https://api.brevo.com/v3/smtp/email',
                    headers={'api-key': os.environ['OTO_BREVO_API_KEY'], 'Accept': 'application/json'},
                    json={'sender': {'email': os.environ['OTO_MAIL_FROM'], 'name': 'OTO Hospedagem'},
                          'to': [{'email': row['destinatario']}],
                          'subject': row['assunto'], 'textContent': row['corpo']}, timeout=15)
    response.raise_for_status()


def dispatch_one(db, smtp_factory=smtplib.SMTP, brevo_sender=send_brevo):
    provider = os.getenv('OTO_MAIL_PROVIDER', 'smtp')
    if provider not in ('smtp', 'brevo'):
        raise RuntimeError('OTO_MAIL_PROVIDER deve ser smtp ou brevo.')
    host = os.getenv('OTO_SMTP_HOST')
    if provider == 'smtp' and not host: return False
    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM email_outbox WHERE enviado_em IS NULL AND tentativas<10 ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row: return False
        message = EmailMessage()
        message['From'] = os.getenv('OTO_MAIL_FROM','no-reply@oto.example.test')
        message['To'] = row['destinatario']
        message['Subject'] = row['assunto']
        message.set_content(row['corpo'])
        try:
            if provider == 'brevo':
                brevo_sender(row)
            else:
                port = int(os.getenv('OTO_SMTP_PORT','587'))
                with smtp_factory(host,port,timeout=10) as client:
                    if os.getenv('OTO_SMTP_STARTTLS','false').lower()=='true': client.starttls()
                    if os.getenv('OTO_SMTP_USER'): client.login(os.environ['OTO_SMTP_USER'],os.environ['OTO_SMTP_PASSWORD'])
                    client.send_message(message)
            conn.execute("UPDATE email_outbox SET enviado_em=now(),corpo='',ultimo_erro=NULL,tentativas=tentativas+1 WHERE id=%s",(row['id'],))
        except (OSError, smtplib.SMTPException, httpx.HTTPError):
            # Não persistir mensagem/segredos eventualmente contidos na resposta SMTP.
            conn.execute("UPDATE email_outbox SET ultimo_erro='Falha no transporte de e-mail',tentativas=tentativas+1 WHERE id=%s",(row['id'],))
            log.warning('Falha no envio da mensagem %s',row['id'])
        return True


def run_dispatcher(stop):
    while not stop.is_set():
        try:
            dispatched = dispatch_one(database())
        except Exception:
            log.warning('Dispatcher temporariamente indisponível')
            dispatched = False
        stop.wait(1 if dispatched else 5)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_dispatcher(Event())
