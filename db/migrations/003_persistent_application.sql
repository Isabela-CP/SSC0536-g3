-- Complementos para a API real. Não substitui 001/002 já entregues.
-- Bearer opaco com hash e expiração no servidor substitui a premissa JWT de 002.
BEGIN;
ALTER TABLE estabelecimentos ALTER COLUMN cnpj DROP NOT NULL;
ALTER TABLE estabelecimentos ALTER COLUMN razao_social DROP NOT NULL;
CREATE UNIQUE INDEX uq_estabelecimentos_cnpj_normalizado
    ON estabelecimentos (regexp_replace(cnpj, '[^0-9]', '', 'g')) WHERE cnpj IS NOT NULL;
CREATE UNIQUE INDEX uq_usuarios_email_normalizado ON usuarios (lower(email));
ALTER TABLE estabelecimentos ADD COLUMN dados_complementares JSONB NOT NULL DEFAULT '{}';
ALTER TABLE meio_hospedagem ALTER COLUMN infraestrutura DROP NOT NULL;
ALTER TABLE meio_hospedagem ALTER COLUMN acessibilidade DROP NOT NULL;
ALTER TABLE meio_hospedagem ALTER COLUMN atendimento_idiomas DROP NOT NULL;
ALTER TABLE pesquisas_ocupacao ADD COLUMN titulo TEXT;
UPDATE pesquisas_ocupacao SET titulo = 'Ocupação ' || to_char(periodo_referencia,'MM/YYYY');
ALTER TABLE pesquisas_ocupacao ALTER COLUMN titulo SET NOT NULL;
ALTER TABLE pesquisas_ocupacao ALTER COLUMN titulo SET DEFAULT 'Pesquisa de ocupação';
CREATE TABLE pesquisa_destinatarios (
    id_pesquisa BIGINT NOT NULL REFERENCES pesquisas_ocupacao(id),
    id_estabelecimento UUID NOT NULL REFERENCES estabelecimentos(id_estabelecimento),
    PRIMARY KEY (id_pesquisa,id_estabelecimento)
);
INSERT INTO pesquisa_destinatarios SELECT id_pesquisa,id_estabelecimento FROM respostas_ocupacao ON CONFLICT DO NOTHING;
CREATE TABLE sessoes (
    token_hash TEXT PRIMARY KEY, id_usuario BIGINT NOT NULL REFERENCES usuarios(id),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), expira_em TIMESTAMPTZ NOT NULL,
    revogado_em TIMESTAMPTZ
);
CREATE INDEX idx_sessoes_usuario ON sessoes(id_usuario);
CREATE TABLE email_outbox (
    id BIGSERIAL PRIMARY KEY, destinatario TEXT NOT NULL, assunto TEXT NOT NULL,
    corpo TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), enviado_em TIMESTAMPTZ,
    tentativas INTEGER NOT NULL DEFAULT 0, ultimo_erro TEXT
);
-- Segredos de convite/recuperação ficam nesta fila apenas até o envio.
-- O dispatcher limpa o corpo depois de enviar; tabelas de tokens guardam apenas hash.
CREATE FUNCTION preservar_auditoria() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Auditoria é append-only'; END;
$$;
CREATE TRIGGER auditoria_append_only BEFORE UPDATE OR DELETE ON auditoria_logs
    FOR EACH ROW EXECUTE FUNCTION preservar_auditoria();
COMMIT;
