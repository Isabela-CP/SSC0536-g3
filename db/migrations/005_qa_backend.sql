CREATE TABLE login_tentativas (
    chave text PRIMARY KEY,
    falhas integer NOT NULL,
    expira_em timestamptz NOT NULL
);
ALTER TABLE login_tentativas ENABLE ROW LEVEL SECURITY;

ALTER TABLE email_outbox
    ADD COLUMN proxima_tentativa_em timestamptz NOT NULL DEFAULT now();

CREATE INDEX idx_outbox_pendente
    ON email_outbox (proxima_tentativa_em, id)
    WHERE enviado_em IS NULL AND tentativas < 10;

ALTER TYPE formato_relatorio ADD VALUE IF NOT EXISTS 'XLSX';
