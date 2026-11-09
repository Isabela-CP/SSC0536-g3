"""Outbox transacional. O SMTP de desenvolvimento é capturado pelo Mailpit."""
from email.message import EmailMessage
import logging
import os
import smtplib
import time
from app.database import database

log = logging.getLogger(__name__)


def dispatch_one(db, smtp_factory=smtplib.SMTP):
    host = os.getenv('OTO_SMTP_HOST')
    if not host: return False
    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM email_outbox WHERE enviado_em IS NULL AND tentativas<10 ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row: return False
        message = EmailMessage()
        message['From'] = os.getenv('OTO_MAIL_FROM','no-reply@oto.example.test')
        message['To'] = row['destinatario']
        message['Subject'] = row['assunto']
        message.set_content(row['corpo'])
        try:
            port = int(os.getenv('OTO_SMTP_PORT','587'))
            with smtp_factory(host,port,timeout=10) as client:
                if os.getenv('OTO_SMTP_STARTTLS','false').lower()=='true': client.starttls()
                if os.getenv('OTO_SMTP_USER'): client.login(os.environ['OTO_SMTP_USER'],os.environ['OTO_SMTP_PASSWORD'])
                client.send_message(message)
            conn.execute("UPDATE email_outbox SET enviado_em=now(),corpo='',ultimo_erro=NULL,tentativas=tentativas+1 WHERE id=%s",(row['id'],))
        except (OSError,smtplib.SMTPException):
            # Não persistir mensagem/segredos eventualmente contidos na resposta SMTP.
            conn.execute("UPDATE email_outbox SET ultimo_erro='Falha no transporte SMTP',tentativas=tentativas+1 WHERE id=%s",(row['id'],))
            log.warning('Falha no envio da mensagem %s',row['id'])
        return True


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    while True:
        try: dispatched=dispatch_one(database())
        except Exception:
            log.warning('Dispatcher temporariamente indisponível')
            dispatched=False
        time.sleep(1 if dispatched else 5)
