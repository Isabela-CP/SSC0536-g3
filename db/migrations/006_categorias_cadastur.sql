-- Preserve categorias existentes e reserve os IDs baixos usados no seed local.
SELECT setval(
    'categorias_estabelecimento_id_categoria_seq',
    GREATEST(100,
             (SELECT last_value FROM categorias_estabelecimento_id_categoria_seq),
             COALESCE((SELECT max(id_categoria) FROM categorias_estabelecimento), 0))
);

INSERT INTO categorias_estabelecimento (nome_categoria)
VALUES ('HOTEL'), ('POUSADA'), ('RESORT'), ('HOTEL FAZENDA'),
       ('HOSTEL'), ('FLAT'), ('ACAMPAMENTO TURÍSTICO')
ON CONFLICT (nome_categoria) DO NOTHING;

-- O enum antigo distinguia obrigatoriedade, não a validade do documento.
ALTER TYPE cadastur_status RENAME TO cadastur_status_legacy;
CREATE TYPE cadastur_status AS ENUM (
    'REGULAR', 'PROXIMO_VENCIMENTO', 'EM_ALERTA', 'VENCIDO', 'SEM_VALIDADE'
);
ALTER TABLE estabelecimentos ALTER COLUMN cadastur_status DROP DEFAULT;
ALTER TABLE estabelecimentos ALTER COLUMN cadastur_status TYPE cadastur_status
USING (CASE
    WHEN NOT possui_cadastur OR vencimento_cadastur IS NULL THEN 'SEM_VALIDADE'
    WHEN vencimento_cadastur < CAST(now() AT TIME ZONE 'America/Sao_Paulo' AS DATE) THEN 'VENCIDO'
    WHEN vencimento_cadastur <= CAST(now() AT TIME ZONE 'America/Sao_Paulo' AS DATE) + 30 THEN 'EM_ALERTA'
    WHEN vencimento_cadastur <= CAST(now() AT TIME ZONE 'America/Sao_Paulo' AS DATE) + 90 THEN 'PROXIMO_VENCIMENTO'
    ELSE 'REGULAR'
END)::cadastur_status;
ALTER TABLE estabelecimentos ALTER COLUMN cadastur_status SET DEFAULT 'SEM_VALIDADE';
DROP TYPE cadastur_status_legacy;
