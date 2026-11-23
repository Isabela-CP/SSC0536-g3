ALTER TABLE usuarios DROP CONSTRAINT uq_usuarios_email;
DROP INDEX uq_usuarios_email_normalizado;

CREATE UNIQUE INDEX uq_usuarios_email_normalizado
    ON usuarios (lower(email))
    WHERE excluido_em IS NULL;
